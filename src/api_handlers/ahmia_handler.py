"""Ahmia dark web search + Tor .onion scraping + weighted risk scoring."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

import aiohttp
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup

import config
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

AHMIA_SEARCH_URL = "https://ahmia.fi/search/?q={query}"


class AhmiaHandler(BaseHandler):
    name = "ahmia"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        search_terms = [phone]
        clean = re.sub(r"[^\w]", "", phone)
        if clean != phone:
            search_terms.append(clean)
        if email:
            search_terms.append(email)

        all_results: list[dict] = []
        for term in search_terms:
            results = await self._search_ahmia(term)
            all_results.extend(results)

        all_results = self._deduplicate(all_results)

        for result in all_results:
            if result.get("onion_url"):
                content = await self._scrape_onion(result["onion_url"])
                if content:
                    result["full_content"] = content[:5000]

        scored = self._score_results(all_results, search_terms)
        cross = self._cross_entity_match(all_results, search_terms)

        total_score = self._compute_risk_score(scored, cross)

        return {
            "search_terms": search_terms,
            "results": scored,
            "cross_matches": cross,
            "risk_score": total_score,
            "risk_level": config.get_risk_level(total_score),
            "total_mentions": len(scored),
        }

    async def _search_ahmia(self, query: str) -> list[dict]:
        url = AHMIA_SEARCH_URL.format(query=quote_plus(query))
        try:
            html = await self._fetch(url)
            if not isinstance(html, str):
                return []
            soup = BeautifulSoup(html, "lxml")
            results = []
            for item in soup.select("li.result"):
                link = item.select_one("a")
                snippet_el = item.select_one("p")
                if link:
                    href = link.get("href", "")
                    onion = self._extract_onion(href)
                    results.append({
                        "title": link.get_text(strip=True),
                        "url": href,
                        "onion_url": onion,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        "query": query,
                    })
            return results
        except Exception as exc:
            logger.warning("Ahmia search failed for '%s': %s", query, exc)
            return []

    def _extract_onion(self, url: str) -> str | None:
        match = re.search(r"(https?://[a-z2-7]{56}\.onion[^\s\"']*)", url, re.I)
        return match.group(1) if match else None

    async def _scrape_onion(self, onion_url: str) -> str | None:
        try:
            connector = ProxyConnector.from_url(config.TOR_SOCKS_URL)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(onion_url) as resp:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "lxml")
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    return soup.get_text(separator=" ", strip=True)
        except Exception as exc:
            logger.debug("Onion scrape failed for %s: %s", onion_url, exc)
            return None

    def _score_results(self, results: list[dict], search_terms: list[str]) -> list[dict]:
        for r in results:
            text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('full_content', '')}".lower()
            keyword_score = 0.0
            matched_keywords: list[dict] = []

            for tier_name, tier in config.KEYWORD_TIERS.items():
                for term in tier["terms"]:
                    count = text.count(term.lower())
                    if count > 0:
                        keyword_score += tier["weight"] * count
                        matched_keywords.append({
                            "term": term,
                            "tier": tier_name,
                            "weight": tier["weight"],
                            "count": count,
                        })

            r["keyword_score"] = round(keyword_score, 3)
            r["matched_keywords"] = matched_keywords
        return results

    def _cross_entity_match(self, results: list[dict], search_terms: list[str]) -> list[dict]:
        matches = []
        for r in results:
            text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('full_content', '')}".lower()
            found_terms = [t for t in search_terms if t.lower() in text]
            if len(found_terms) >= 2:
                matches.append({
                    "url": r.get("url"),
                    "matched_entities": found_terms,
                    "count": len(found_terms),
                })
        return matches

    def _compute_risk_score(self, results: list[dict], cross_matches: list[dict]) -> float:
        w = config.RISK_WEIGHTS
        mention_score = min(len(results) * 0.06, w["darkweb_mentions"])
        cross_score = min(len(cross_matches) * 0.125, w["cross_entity"])
        kw_total = sum(r.get("keyword_score", 0) for r in results)
        kw_score = min(kw_total * 0.03, w["keyword_severity"])
        high_risk = sum(1 for r in results if r.get("keyword_score", 0) > 2.0)
        hr_score = min(high_risk * 0.05, w["high_risk_density"])
        return round(mention_score + cross_score + kw_score + hr_score, 4)

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique = []
        for r in results:
            key = r.get("url", "") or r.get("onion_url", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(r)
        return unique
