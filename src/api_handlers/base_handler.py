"""Abstract base class for all OSINT API handlers.

Provides shared HTTP session, rate limiting, retry logic, and a
standard result envelope.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

import config

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Every handler inherits from this and implements ``_query``."""

    name: str = "base"

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._last_request_ts: float = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < config.RATE_LIMIT_DELAY:
            await asyncio.sleep(config.RATE_LIMIT_DELAY - elapsed)
        self._last_request_ts = time.monotonic()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch(self, url: str, **kwargs) -> dict | str:
        await self._rate_limit()
        session = await self._get_session()
        async with session.get(url, **kwargs) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                return await resp.json()
            return await resp.text()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _post(self, url: str, **kwargs) -> dict | str:
        await self._rate_limit()
        session = await self._get_session()
        async with session.post(url, **kwargs) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                return await resp.json()
            return await resp.text()

    @abstractmethod
    async def _query(self, phone: str, email: str | None = None) -> dict[str, Any]:
        ...

    async def search(self, phone: str, email: str | None = None) -> dict[str, Any]:
        """Public entry point – wraps ``_query`` with error handling."""
        try:
            data = await self._query(phone, email)
            return {
                "source": self.name,
                "success": True,
                "data": data,
            }
        except Exception as exc:
            logger.exception("Handler %s failed", self.name)
            return {
                "source": self.name,
                "success": False,
                "error": str(exc),
            }
