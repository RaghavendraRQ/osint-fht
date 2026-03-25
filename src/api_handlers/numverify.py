"""NumVerify API handler – phone validation, carrier, country, line type."""

from __future__ import annotations

import logging
from typing import Any

import config
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

API_URL = "http://apilayer.net/api/validate"


class NumVerifyHandler(BaseHandler):
    name = "numverify"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not config.NUMVERIFY_API_KEY:
            return {"error": "NUMVERIFY_API_KEY not configured"}

        clean_phone = phone.replace("+", "").replace("-", "").replace(" ", "")
        params = {
            "access_key": config.NUMVERIFY_API_KEY,
            "number": clean_phone,
            "format": 1,
        }

        data = await self._fetch(API_URL, params=params)
        if isinstance(data, dict) and data.get("valid") is False and "error" in data:
            return {"valid": False, "raw": data}

        return {
            "valid": data.get("valid", False),
            "number": data.get("number"),
            "local_format": data.get("local_format"),
            "international_format": data.get("international_format"),
            "country_prefix": data.get("country_prefix"),
            "country_code": data.get("country_code"),
            "country_name": data.get("country_name"),
            "location": data.get("location"),
            "carrier": data.get("carrier"),
            "line_type": data.get("line_type"),
        }
