"""Central orchestrator – runs all OSINT handlers concurrently and aggregates results."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import config
from src.api_handlers import (
    AhmiaHandler,
    BlackbirdHandler,
    HunterHandler,
    MaigretHandler,
    NumVerifyHandler,
    SherlockHandler,
    SpiderFootHandler,
    TrueCallerHandler,
)
from src.utils.entity_resolver import EntityResolver
from src.utils.neo4j_handler import Neo4jHandler
from src.utils.phone_validator import PhoneValidator

logger = logging.getLogger(__name__)


class OSINTManager:
    """Runs the full OSINT pipeline: validate → query → resolve → darkweb → graph → score."""

    def __init__(self, neo4j: Neo4jHandler | None = None):
        self.neo4j = neo4j
        self.resolver = EntityResolver()
        self.validator = PhoneValidator()

        self._surface_handlers = [
            NumVerifyHandler(),
            TrueCallerHandler(),
            HunterHandler(),
            SherlockHandler(),
            MaigretHandler(),
            BlackbirdHandler(),
            SpiderFootHandler(),
        ]
        self._darkweb_handler = AhmiaHandler()

    async def investigate(
        self,
        phone: str,
        email: str | None = None,
        include_darkweb: bool = True,
    ) -> dict[str, Any]:
        """Full synchronous investigation – returns complete results dict."""
        validation = self.validator.validate(phone)
        if not validation["valid"]:
            return {"error": "Invalid phone number", "validation": validation}

        surface_tasks = [h.search(phone, email) for h in self._surface_handlers]
        surface_results = await asyncio.gather(*surface_tasks, return_exceptions=True)

        api_results = []
        for r in surface_results:
            if isinstance(r, Exception):
                api_results.append({"source": "unknown", "success": False, "error": str(r)})
            else:
                api_results.append(r)

        entities = self.resolver.resolve(api_results)

        darkweb_results = None
        if include_darkweb:
            darkweb_results = await self._darkweb_handler.search(phone, email)

        if self.neo4j:
            await self.neo4j.store_investigation(phone, email, api_results, entities, darkweb_results)

        result = {
            "phone": phone,
            "email": email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation": validation,
            "api_results": api_results,
            "entities": entities,
            "darkweb": darkweb_results,
            "summary": self._build_summary(api_results, darkweb_results),
        }

        self._save_results(phone, result)
        return result

    async def investigate_stream(
        self,
        phone: str,
        email: str | None = None,
        include_darkweb: bool = True,
    ) -> AsyncGenerator[str, None]:
        """SSE streaming investigation – yields JSON events as each step completes."""
        validation = self.validator.validate(phone)
        yield self._event("validation", validation)

        if not validation["valid"]:
            yield self._event("error", {"message": "Invalid phone number"})
            return

        all_results: list[dict] = []
        for handler in self._surface_handlers:
            try:
                result = await handler.search(phone, email)
                all_results.append(result)
                yield self._event("api_result", result)
            except Exception as exc:
                err = {"source": handler.name, "success": False, "error": str(exc)}
                all_results.append(err)
                yield self._event("api_result", err)

        entities = self.resolver.resolve(all_results)
        yield self._event("entities", entities)

        darkweb_results = None
        if include_darkweb:
            yield self._event("status", {"message": "Starting dark web search..."})
            darkweb_results = await self._darkweb_handler.search(phone, email)
            yield self._event("darkweb", darkweb_results)

        if self.neo4j:
            await self.neo4j.store_investigation(phone, email, all_results, entities, darkweb_results)
            yield self._event("status", {"message": "Stored in Neo4j graph"})

        summary = self._build_summary(all_results, darkweb_results)
        yield self._event("summary", summary)

        full_result = {
            "phone": phone,
            "email": email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation": validation,
            "api_results": all_results,
            "entities": entities,
            "darkweb": darkweb_results,
            "summary": summary,
        }
        self._save_results(phone, full_result)
        yield self._event("complete", {"message": "Investigation complete"})

    def _build_summary(self, api_results: list[dict], darkweb: dict | None) -> dict:
        success = sum(1 for r in api_results if r.get("success"))
        failed = len(api_results) - success
        risk_score = 0.0
        risk_level = "MINIMAL"

        if darkweb and darkweb.get("success") and darkweb.get("data"):
            dw = darkweb["data"]
            risk_score = dw.get("risk_score", 0.0)
            risk_level = dw.get("risk_level", "MINIMAL")

        return {
            "apis_succeeded": success,
            "apis_failed": failed,
            "total_apis": len(api_results),
            "risk_score": risk_score,
            "risk_level": risk_level,
        }

    def _save_results(self, phone: str, result: dict):
        clean = phone.replace("+", "").replace("-", "").replace(" ", "")
        path = config.RESULTS_DIR / f"{clean}.json"
        try:
            path.write_text(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            logger.error("Failed to save results for %s: %s", phone, exc)

    @staticmethod
    def _event(event_type: str, data: Any) -> str:
        return json.dumps({"event": event_type, "data": data}, default=str)

    async def close(self):
        for h in self._surface_handlers:
            await h.close()
        await self._darkweb_handler.close()
