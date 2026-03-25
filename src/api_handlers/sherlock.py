"""Sherlock handler – username presence detection across 300+ sites."""

from __future__ import annotations

import asyncio
import logging
import shutil
import re
from typing import Any

from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class SherlockHandler(BaseHandler):
    name = "sherlock"

    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        if not shutil.which("sherlock"):
            return {"error": "sherlock CLI not found in PATH"}

        clean = re.sub(r"[^\w]", "", phone)
        usernames = [clean]
        if email:
            usernames.append(email.split("@")[0])

        all_hits: list[dict] = []
        for username in usernames:
            hits = await self._run_sherlock(username)
            all_hits.extend(hits)

        return {"usernames_checked": usernames, "profiles": all_hits}

    async def _run_sherlock(self, username: str) -> list[dict]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "sherlock", username, "--print-found", "--timeout", "15",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            lines = stdout.decode().strip().splitlines()

            profiles = []
            for line in lines:
                line = line.strip()
                if line.startswith("http"):
                    profiles.append({"url": line, "username": username})
                elif ": http" in line:
                    parts = line.split(": ", 1)
                    profiles.append({
                        "site": parts[0].strip("[+] ").strip(),
                        "url": parts[1].strip(),
                        "username": username,
                    })
            return profiles
        except asyncio.TimeoutError:
            logger.warning("Sherlock timed out for %s", username)
            return []
