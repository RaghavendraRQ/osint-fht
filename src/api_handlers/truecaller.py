"""TrueCaller handler – caller ID, registered name, alternate numbers."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

from .base_handler import BaseHandler
import config

logger = logging.getLogger(__name__)


class TrueCallerHandler(BaseHandler):
    name = "truecaller"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not config.TRUECALLER_API_KEY:
            return {"error": "TRUECALLER_API_KEY not configured"}

        if not shutil.which("truecallerpy"):
            return {"error": "truecallerpy CLI not found in PATH"}

        try:
            proc = await asyncio.create_subprocess_exec(
                "truecallerpy", "-s", phone, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode().strip()
            if not output:
                return {"error": stderr.decode().strip() or "empty response"}

            data = json.loads(output)
            if isinstance(data, list) and data:
                data = data[0]

            return {
                "name": data.get("name", ""),
                "phones": data.get("phones", []),
                "addresses": data.get("addresses", []),
                "email": data.get("internetAddresses", []),
                "raw": data,
            }
        except asyncio.TimeoutError:
            return {"error": "truecallerpy timed out"}
        except json.JSONDecodeError:
            return {"error": "failed to parse truecallerpy output"}
