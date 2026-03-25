"""Maigret handler – username OSINT across 2000+ sites."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import re
import tempfile
from pathlib import Path
from typing import Any

from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class MaigretHandler(BaseHandler):
    name = "maigret"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not shutil.which("maigret"):
            return {"error": "maigret CLI not found in PATH"}

        clean = re.sub(r"[^\w]", "", phone)
        usernames = [clean]
        if email:
            usernames.append(email.split("@")[0])

        all_hits: list[dict] = []
        for username in usernames:
            hits = await self._run_maigret(username)
            all_hits.extend(hits)

        return {"usernames_checked": usernames, "profiles": all_hits}

    async def _run_maigret(self, username: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / "report.json"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "maigret", username,
                    "--json", "simple",
                    "-o", str(out_json),
                    "--timeout", "15",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=180)

                if out_json.exists():
                    data = json.loads(out_json.read_text())
                    profiles = []
                    items = data if isinstance(data, list) else data.get("results", data.get(username, []))
                    for item in items if isinstance(items, list) else []:
                        profiles.append({
                            "site": item.get("sitename", item.get("site", "")),
                            "url": item.get("url", ""),
                            "username": username,
                        })
                    return profiles
                return []
            except asyncio.TimeoutError:
                logger.warning("Maigret timed out for %s", username)
                return []
