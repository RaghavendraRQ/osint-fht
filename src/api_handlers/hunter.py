"""Hunter.io handler – email intelligence, domain search, email finder."""

from __future__ import annotations

import logging
from typing import Any

import config
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class HunterHandler(BaseHandler):
    name = "hunter"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not config.HUNTER_API_KEY:
            return {"error": "HUNTER_API_KEY not configured"}

        results: dict[str, Any] = {"emails": [], "domain_info": None}

        if email and "@" in email:
            domain = email.split("@")[1]
            data = await self._fetch(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": config.HUNTER_API_KEY},
            )
            if isinstance(data, dict):
                ds = data.get("data", {})
                results["domain_info"] = {
                    "domain": ds.get("domain"),
                    "organization": ds.get("organization"),
                    "disposable": ds.get("disposable"),
                    "webmail": ds.get("webmail"),
                }
                for em in ds.get("emails", []):
                    results["emails"].append({
                        "email": em.get("value"),
                        "type": em.get("type"),
                        "confidence": em.get("confidence"),
                        "first_name": em.get("first_name"),
                        "last_name": em.get("last_name"),
                    })

            verify = await self._fetch(
                "https://api.hunter.io/v2/email-verifier",
                params={"email": email, "api_key": config.HUNTER_API_KEY},
            )
            if isinstance(verify, dict):
                vd = verify.get("data", {})
                results["email_verification"] = {
                    "status": vd.get("status"),
                    "score": vd.get("score"),
                    "disposable": vd.get("disposable"),
                    "webmail": vd.get("webmail"),
                }

        return results
