"""Neo4j graph database handler – CRUD, analytics queries, GDS projections."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from neo4j import AsyncGraphDatabase

import config

logger = logging.getLogger(__name__)


class Neo4jHandler:
    def __init__(self):
        self._driver = AsyncGraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        )

    async def close(self):
        await self._driver.close()

    async def verify(self) -> bool:
        try:
            async with self._driver.session() as s:
                await s.run("RETURN 1")
            return True
        except Exception as exc:
            logger.error("Neo4j verification failed: %s", exc)
            return False

    # ── Storage ──────────────────────────────────────────────────

    async def store_investigation(
        self,
        phone: str,
        email: str | None,
        api_results: list[dict],
        entities: dict[str, list[dict]],
        darkweb: dict | None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        async with self._driver.session() as s:
            await s.execute_write(
                self._tx_store, phone, email, api_results, entities, darkweb, now
            )

    @staticmethod
    async def _tx_store(tx, phone, email, api_results, entities, darkweb, now):
        await tx.run(
            """
            MERGE (p:Phone {number: $phone})
            ON CREATE SET p.first_seen = $now
            SET p.last_seen = $now
            """,
            phone=phone, now=now,
        )

        if email:
            await tx.run(
                """
                MERGE (e:Email {address: $email})
                MERGE (p:Phone {number: $phone})
                MERGE (p)-[:HAS_EMAIL]->(e)
                """,
                phone=phone, email=email,
            )

        for ent in entities.get("emails", []):
            await tx.run(
                """
                MERGE (e:Email {address: $addr})
                MERGE (p:Phone {number: $phone})
                MERGE (p)-[r:HAS_EMAIL]->(e)
                SET r.confidence = $conf, r.sources = $sources
                """,
                phone=phone, addr=ent["value"],
                conf=ent["confidence"], sources=ent["sources"],
            )

        for ent in entities.get("usernames", []):
            await tx.run(
                """
                MERGE (u:Username {name: $name})
                MERGE (p:Phone {number: $phone})
                MERGE (p)-[r:HAS_USERNAME]->(u)
                SET r.confidence = $conf, r.sources = $sources
                """,
                phone=phone, name=ent["value"],
                conf=ent["confidence"], sources=ent["sources"],
            )

        for ent in entities.get("profiles", []):
            await tx.run(
                """
                MERGE (pr:Profile {url: $url})
                ON CREATE SET pr.site = $site
                MERGE (p:Phone {number: $phone})
                MERGE (p)-[:HAS_PROFILE]->(pr)
                """,
                phone=phone, url=ent["value"], site=ent.get("site", ""),
            )

        for ent in entities.get("names", []):
            await tx.run(
                """
                MERGE (n:Name {value: $name})
                MERGE (p:Phone {number: $phone})
                MERGE (p)-[:HAS_NAME]->(n)
                """,
                phone=phone, name=ent["value"],
            )

        for ent in entities.get("phones", []):
            other = ent.get("value") or ""
            if not other or other == phone:
                continue
            await tx.run(
                """
                MATCH (p:Phone {number: $phone})
                MERGE (p2:Phone {number: $other})
                ON CREATE SET p2.first_seen = $now
                SET p2.last_seen = $now
                MERGE (p)-[:RELATED_PHONE]->(p2)
                """,
                phone=phone, other=other, now=now,
            )

        # Carrier info from numverify
        for r in api_results:
            if r.get("source") == "numverify" and r.get("success"):
                d = r["data"]
                if d.get("carrier"):
                    await tx.run(
                        """
                        MERGE (c:Carrier {name: $carrier})
                        MERGE (p:Phone {number: $phone})
                        MERGE (p)-[:HAS_CARRIER]->(c)
                        SET p.line_type = $lt, p.country = $country
                        """,
                        phone=phone, carrier=d["carrier"],
                        lt=d.get("line_type", ""), country=d.get("country_name", ""),
                    )

        if darkweb and darkweb.get("success"):
            dw = darkweb.get("data", {})
            for result in dw.get("results", []):
                onion = result.get("onion_url") or result.get("url", "")
                if not onion:
                    continue
                await tx.run(
                    """
                    MERGE (d:DarkWebSite {url: $url})
                    ON CREATE SET d.title = $title, d.first_seen = $now
                    SET d.last_seen = $now, d.keyword_score = $ks
                    MERGE (p:Phone {number: $phone})
                    MERGE (p)-[r:MENTIONED_IN]->(d)
                    ON CREATE SET r.first_seen = $now, r.mention_count = 1
                    ON MATCH SET r.last_seen = $now,
                                 r.mention_count = coalesce(r.mention_count, 0) + 1
                    """,
                    phone=phone, url=onion, title=result.get("title", ""),
                    now=now, ks=result.get("keyword_score", 0),
                )

            for cm in dw.get("cross_matches", []):
                await tx.run(
                    """
                    MERGE (x:CrossMatch {url: $url})
                    SET x.matched_entities = $ents, x.count = $count
                    MERGE (p:Phone {number: $phone})
                    MERGE (p)-[:CROSS_REFERENCED]->(x)
                    """,
                    phone=phone, url=cm.get("url", ""),
                    ents=cm.get("matched_entities", []), count=cm.get("count", 0),
                )

            await tx.run(
                """
                MATCH (p:Phone {number: $phone})
                SET p.risk_score = $rs, p.risk_level = $rl,
                    p.has_darkweb_mention = $has_dw
                """,
                phone=phone,
                rs=dw.get("risk_score", 0),
                rl=dw.get("risk_level", "MINIMAL"),
                has_dw=len(dw.get("results", [])) > 0,
            )

    # ── Analytics ────────────────────────────────────────────────

    async def get_connections(self, phone: str) -> list[dict]:
        query = """
        MATCH (p:Phone {number: $phone})-[*1..2]-(connected:Phone)
        WHERE connected.number <> $phone
        RETURN DISTINCT connected.number AS phone,
               connected.risk_score AS risk_score,
               connected.risk_level AS risk_level
        """
        async with self._driver.session() as s:
            result = await s.run(query, phone=phone)
            return [dict(r) async for r in result]

    async def get_clusters(self) -> list[dict]:
        query = """
        CALL gds.graph.project.cypher(
            'osint_graph',
            'MATCH (n) WHERE n:Phone OR n:Email OR n:Username RETURN id(n) AS id',
            'MATCH (a)-[r]->(b) RETURN id(a) AS source, id(b) AS target'
        ) YIELD graphName
        WITH graphName
        CALL gds.louvain.stream(graphName)
        YIELD nodeId, communityId
        WITH gds.util.asNode(nodeId) AS node, communityId
        WHERE node:Phone
        RETURN communityId,
               collect(node.number) AS phones,
               count(*) AS size
        ORDER BY size DESC
        """
        try:
            async with self._driver.session() as s:
                result = await s.run(query)
                clusters = [dict(r) async for r in result]
            await self._drop_projection("osint_graph")
            return clusters
        except Exception as exc:
            logger.warning("Cluster detection failed: %s", exc)
            return []

    async def get_centrality(self, limit: int = 20) -> list[dict]:
        query = """
        CALL gds.graph.project.cypher(
            'centrality_graph',
            'MATCH (n) WHERE n:Phone OR n:Email OR n:Username OR n:DarkWebSite RETURN id(n) AS id',
            'MATCH (a)-[r]->(b) RETURN id(a) AS source, id(b) AS target'
        ) YIELD graphName
        WITH graphName
        CALL gds.betweenness.stream(graphName)
        YIELD nodeId, score
        WITH gds.util.asNode(nodeId) AS node, score
        WHERE node:Phone
        RETURN node.number AS phone, score
        ORDER BY score DESC
        LIMIT $limit
        """
        try:
            async with self._driver.session() as s:
                result = await s.run(query, limit=limit)
                items = [dict(r) async for r in result]
            await self._drop_projection("centrality_graph")
            return items
        except Exception as exc:
            logger.warning("Centrality analysis failed: %s", exc)
            return []

    async def get_high_risk(self) -> list[dict]:
        query = """
        MATCH (p:Phone)-[r:MENTIONED_IN]->(d:DarkWebSite)
        WITH p, count(d) AS mentions, sum(d.keyword_score) AS total_ks
        WHERE mentions >= 2
        RETURN p.number AS phone, p.risk_score AS risk_score,
               p.risk_level AS risk_level, mentions, total_ks
        ORDER BY total_ks DESC
        """
        async with self._driver.session() as s:
            result = await s.run(query)
            return [dict(r) async for r in result]

    async def get_network(self, phone: str) -> dict[str, list]:
        query = """
        MATCH path = (p:Phone {number: $phone})-[*1..2]-(connected)
        UNWIND relationships(path) AS rel
        WITH startNode(rel) AS src, endNode(rel) AS tgt, type(rel) AS rtype
        RETURN DISTINCT
            labels(src)[0] AS src_label,
            coalesce(src.number, src.address, src.name, src.url, src.value) AS src_id,
            labels(tgt)[0] AS tgt_label,
            coalesce(tgt.number, tgt.address, tgt.name, tgt.url, tgt.value) AS tgt_id,
            rtype
        """
        async with self._driver.session() as s:
            result = await s.run(query, phone=phone)
            records = [dict(r) async for r in result]

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        for r in records:
            for prefix in ("src", "tgt"):
                nid = r[f"{prefix}_id"]
                if nid and nid not in nodes:
                    nodes[nid] = {"id": nid, "label": r[f"{prefix}_label"]}
            edges.append({
                "source": r["src_id"],
                "target": r["tgt_id"],
                "type": r["rtype"],
            })
        return {"nodes": list(nodes.values()), "edges": edges}

    async def get_timeline(self, phone: str) -> list[dict]:
        query = """
        MATCH (p:Phone {number: $phone})-[r:MENTIONED_IN]->(d:DarkWebSite)
        RETURN d.url AS url, d.title AS title,
               r.first_seen AS first_seen, r.last_seen AS last_seen,
               r.mention_count AS mention_count, d.keyword_score AS keyword_score
        ORDER BY r.first_seen
        """
        async with self._driver.session() as s:
            result = await s.run(query, phone=phone)
            return [dict(r) async for r in result]

    async def get_movement(self, phone: str) -> list[dict]:
        query = """
        MATCH (p:Phone {number: $phone})-[r:MENTIONED_IN]->(d:DarkWebSite)
        WHERE d.title IS NOT NULL
        RETURN d.title AS site_title, d.url AS url,
               r.first_seen AS first_seen, r.last_seen AS last_seen
        ORDER BY r.first_seen
        """
        async with self._driver.session() as s:
            result = await s.run(query, phone=phone)
            return [dict(r) async for r in result]

    # ── GNN Support ──────────────────────────────────────────────

    async def get_subgraph_for_gnn(self, phone: str) -> dict[str, Any]:
        """Extract 2-hop subgraph around a phone for GNN feature extraction."""
        query = """
        MATCH (p:Phone {number: $phone})-[*1..2]-(neighbor)
        WITH p, collect(DISTINCT neighbor) AS neighbors
        WITH neighbors + [p] AS all_nodes
        UNWIND all_nodes AS n
        OPTIONAL MATCH (n)-[mi:MENTIONED_IN]->()
        WITH n, count(DISTINCT mi) AS mention_count
        OPTIONAL MATCH (n)-[:HAS_EMAIL]->(e:Email)
        WITH n, mention_count, count(DISTINCT e) AS email_count
        OPTIONAL MATCH (n)-[:HAS_USERNAME]->(u:Username)
        WITH n, mention_count, email_count, count(DISTINCT u) AS username_count
        OPTIONAL MATCH (n)-[cr:CROSS_REFERENCED]->()
        WITH n, mention_count, email_count, username_count, count(DISTINCT cr) AS cross_count
        RETURN
            id(n) AS node_id,
            labels(n) AS labels,
            coalesce(n.number, n.address, n.name, n.url, n.value, toString(id(n))) AS node_key,
            coalesce(n.has_darkweb_mention, false) AS has_darkweb_mention,
            coalesce(n.risk_score, 0.0) AS keyword_score,
            email_count AS num_emails,
            username_count AS num_usernames,
            coalesce(n.line_type, 'unknown') AS carrier_type,
            mention_count,
            cross_count AS cross_entity_count,
            coalesce(n.risk_level, 'MINIMAL') AS risk_level
        """
        edge_query = """
        MATCH (p:Phone {number: $phone})-[*1..2]-(neighbor)
        WITH p, collect(DISTINCT neighbor) AS neighbors
        WITH neighbors + [p] AS all_nodes
        UNWIND all_nodes AS a
        MATCH (a)-[r]-(b)
        WHERE b IN all_nodes
        RETURN DISTINCT id(a) AS source, id(b) AS target, type(r) AS rel_type
        """
        async with self._driver.session() as s:
            node_result = await s.run(query, phone=phone)
            nodes = [dict(r) async for r in node_result]

            edge_result = await s.run(edge_query, phone=phone)
            edges = [dict(r) async for r in edge_result]

        return {"nodes": nodes, "edges": edges}

    async def get_all_phones_for_training(self) -> list[dict]:
        """Get all phone nodes with labels for GNN training."""
        query = """
        MATCH (p:Phone)
        RETURN p.number AS phone,
               coalesce(p.risk_level, 'MINIMAL') AS risk_level,
               coalesce(p.risk_score, 0.0) AS risk_score
        """
        async with self._driver.session() as s:
            result = await s.run(query)
            return [dict(r) async for r in result]

    # ── Helpers ──────────────────────────────────────────────────

    async def _drop_projection(self, name: str):
        try:
            async with self._driver.session() as s:
                await s.run(f"CALL gds.graph.drop('{name}', false)")
        except Exception:
            pass
