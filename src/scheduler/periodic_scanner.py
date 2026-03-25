"""Periodic re-scanning of previously investigated phone numbers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config

logger = logging.getLogger(__name__)


class PeriodicScanner:
    """APScheduler-based periodic rescanner."""

    def __init__(self, osint_manager):
        self.osint_manager = osint_manager
        self.scheduler = AsyncIOScheduler()

    def start(self):
        if not config.SCHEDULER_ENABLED:
            logger.info("Periodic scanner is disabled")
            return

        self.scheduler.add_job(
            self._scan_all,
            "interval",
            hours=config.SCHEDULER_INTERVAL_HOURS,
            id="periodic_rescan",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            "Periodic scanner started – interval: %dh", config.SCHEDULER_INTERVAL_HOURS
        )

    async def _scan_all(self):
        phones = self._load_investigated_phones()
        logger.info("Periodic scan: %d phones to re-scan", len(phones))

        for phone in phones:
            try:
                result = await self.osint_manager.investigate(
                    phone, include_darkweb=True
                )
                logger.info(
                    "Re-scanned %s – risk: %s",
                    phone,
                    result.get("summary", {}).get("risk_level", "UNKNOWN"),
                )
            except Exception as exc:
                logger.error("Periodic scan failed for %s: %s", phone, exc)

    @staticmethod
    def _load_investigated_phones() -> list[str]:
        phones = []
        for path in config.RESULTS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                phone = data.get("phone")
                if phone:
                    phones.append(phone)
            except Exception:
                continue
        return phones

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
