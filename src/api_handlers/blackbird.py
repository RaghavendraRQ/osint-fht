"""Blackbird handler – username and email search across platforms."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import re
from typing import Any

from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class BlackbirdHandler(BaseHandler):
    name = "blackbird"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not shutil.which("blackbird"):
            return {"error": "blackbird CLI not found in PATH"}

        clean = re.sub(r"[^\w]", "", phone)
        targets: list[tuple[str, str]] = [("username", clean)]
        if email:
            targets.append(("email", email))
            targets.append(("username", email.split("@")[0]))

        all_hits: list[dict] = []
        for search_type, value in targets:
            hits = await self._run_blackbird(search_type, value)
            all_hits.extend(hits)

        return {"profiles": all_hits}

    async def _run_blackbird(self, search_type: str, value: str) -> list[dict]:
        flag = "--username" if search_type == "username" else "--email"
        try:
            proc = await asyncio.create_subprocess_exec(
                "blackbird", flag, value,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            lines = stdout.decode().strip().splitlines()

            profiles = []
            for line in lines:
                line = line.strip()
                if "http" in line:
                    parts = line.rsplit("http", 1)
                    url = "http" + parts[1].strip() if len(parts) == 2 else line
                    profiles.append({
                        "url": url.strip(),
                        "search_type": search_type,
                        "value": value,
                    })
            return profiles
        except asyncio.TimeoutError:
            logger.warning("Blackbird timed out for %s=%s", search_type, value)
            return []
