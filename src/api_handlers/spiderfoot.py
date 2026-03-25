"""SpiderFoot handler – automated scanning via self-hosted SpiderFoot API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import config
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class SpiderFootHandler(BaseHandler):
    name = "spiderfoot"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not config.SPIDERFOOT_API_URL:
            return {"error": "SPIDERFOOT_API_URL not configured"}

        base = config.SPIDERFOOT_API_URL.rstrip("/")
        scan_target = email if email else phone

        scan_data = {
            "scanname": f"osint-{phone}",
            "scantarget": scan_target,
            "usecase": "all",
            "modulelist": "",
        }

        resp = await self._post(f"{base}/api/scan/start", data=scan_data)
        if isinstance(resp, str):
            return {"error": f"unexpected response: {resp[:200]}"}

        scan_id = resp.get("scanid") or resp.get("scan_id")
        if not scan_id:
            return {"error": "no scan_id in response", "raw": resp}

        for _ in range(60):
            await asyncio.sleep(5)
            status = await self._fetch(f"{base}/api/scan/{scan_id}/status")
            if isinstance(status, dict) and status.get("status") in ("FINISHED", "ABORTED", "ERROR-FAILED"):
                break

        results = await self._fetch(f"{base}/api/scan/{scan_id}/data")
        if not isinstance(results, list):
            return {"scan_id": scan_id, "raw": results}

        entities: dict[str, list] = {
            "emails": [],
            "usernames": [],
            "domains": [],
            "ips": [],
            "phones": [],
            "other": [],
        }

        type_map = {
            "EMAILADDR": "emails",
            "USERNAME": "usernames",
            "INTERNET_NAME": "domains",
            "IP_ADDRESS": "ips",
            "PHONE_NUMBER": "phones",
        }

        for item in results:
            etype = item.get("type", "")
            bucket = type_map.get(etype, "other")
            entities[bucket].append({
                "type": etype,
                "data": item.get("data"),
                "module": item.get("module"),
            })

        return {"scan_id": scan_id, "entities": entities, "total": len(results)}
