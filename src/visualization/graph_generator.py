"""Build NetworkX graph data for Plotly interactive visualization."""

from __future__ import annotations

import networkx as nx
from typing import Any


COLOR_MAP = {
    "Phone": "#ef4444",
    "Email": "#3b82f6",
    "Username": "#10b981",
    "Profile": "#8b5cf6",
    "DarkWebSite": "#f59e0b",
    "CrossMatch": "#ec4899",
    "Carrier": "#6366f1",
    "Name": "#14b8a6",
}


class GraphGenerator:
    """Converts Neo4j network data into a format Plotly can render."""

    @staticmethod
    def build_network_from_entities(
        phone: str,
        email: str | None,
        entities: dict[str, list],
        darkweb: dict | None,
    ) -> dict[str, list]:
        """Build a network dict from JSON entities when Neo4j is unavailable."""
        nodes: list[dict] = []
        edges: list[dict] = []
        seen: set[str] = set()

        def add_node(nid: str, label: str):
            if nid and nid not in seen:
                seen.add(nid)
                nodes.append({"id": nid, "label": label})

        add_node(phone, "Phone")

        if email:
            add_node(email, "Email")
            edges.append({"source": phone, "target": email, "type": "HAS_EMAIL"})

        for ent in entities.get("emails", []):
            val = ent.get("value", "")
            add_node(val, "Email")
            edges.append({"source": phone, "target": val, "type": "HAS_EMAIL"})

        for ent in entities.get("usernames", []):
            val = ent.get("value", "")
            add_node(val, "Username")
            edges.append({"source": phone, "target": val, "type": "HAS_USERNAME"})

        for ent in entities.get("profiles", []):
            site = ent.get("site") or ent.get("value", "")[:40]
            url = ent.get("value", "")
            add_node(site, "Profile")
            un = ent.get("username") or ent.get("value", "").split("/")[-1]
            if un in seen:
                edges.append({"source": un, "target": site, "type": "HAS_PROFILE"})
            else:
                edges.append({"source": phone, "target": site, "type": "HAS_PROFILE"})

        for ent in entities.get("domains", []):
            val = ent.get("value", "")
            add_node(val, "Domain")
            edges.append({"source": phone, "target": val, "type": "HAS_DOMAIN"})

        for ent in entities.get("names", []):
            val = ent.get("value", "")
            add_node(val, "Name")
            edges.append({"source": phone, "target": val, "type": "HAS_NAME"})

        for ent in entities.get("phones", []):
            val = ent.get("value", "")
            if val != phone:
                add_node(val, "Phone")
                edges.append({"source": phone, "target": val, "type": "RELATED_PHONE"})

        if darkweb and darkweb.get("success"):
            dw = darkweb.get("data", {})
            for r in dw.get("results", []):
                title = r.get("title", "")[:50] or r.get("url", "")[:50]
                if title:
                    add_node(title, "DarkWebSite")
                    edges.append({"source": phone, "target": title, "type": "MENTIONED_IN"})

            for cm in dw.get("cross_matches", []):
                url = cm.get("url", "")[:50]
                if url:
                    add_node(url, "CrossMatch")
                    edges.append({"source": phone, "target": url, "type": "CROSS_REFERENCED"})

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def build_plotly_data(network: dict[str, list]) -> dict[str, Any]:
        nodes = network.get("nodes", [])
        edges = network.get("edges", [])

        if not nodes:
            return {"node_trace": {}, "edge_trace": {}, "annotations": []}

        G = nx.Graph()
        for n in nodes:
            G.add_node(n["id"], label=n.get("label", "Unknown"))
        for e in edges:
            G.add_edge(e["source"], e["target"], rel=e.get("type", ""))

        pos = nx.spring_layout(G, seed=42, k=2.0)

        edge_x, edge_y = [], []
        for src, tgt in G.edges():
            x0, y0 = pos[src]
            x1, y1 = pos[tgt]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = {
            "x": edge_x,
            "y": edge_y,
            "mode": "lines",
            "line": {"width": 0.8, "color": "#94a3b8"},
            "hoverinfo": "none",
        }

        node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
        for nid in G.nodes():
            x, y = pos[nid]
            node_x.append(x)
            node_y.append(y)
            label = G.nodes[nid].get("label", "Unknown")
            node_text.append(f"{label}: {nid}")
            node_color.append(COLOR_MAP.get(label, "#64748b"))
            degree = G.degree(nid)
            node_size.append(max(10, min(30, 8 + degree * 4)))

        node_trace = {
            "x": node_x,
            "y": node_y,
            "mode": "markers+text",
            "text": node_text,
            "textposition": "top center",
            "textfont": {"size": 8},
            "marker": {
                "size": node_size,
                "color": node_color,
                "line": {"width": 1, "color": "#1e293b"},
            },
            "hoverinfo": "text",
        }

        return {
            "node_trace": node_trace,
            "edge_trace": edge_trace,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
