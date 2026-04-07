#!/usr/bin/env python3
"""Load investigation JSON files from data/results and persist them via Neo4jHandler."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.utils.neo4j_handler import Neo4jHandler  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed Neo4j from investigation JSON files (same shape as live pipeline output)."
    )
    p.add_argument(
        "--dir",
        type=Path,
        default=config.RESULTS_DIR,
        help="Directory containing *.json investigation files (default: data/results)",
    )
    p.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated basenames to load only, e.g. 12127556183.json,14435559201.json",
    )
    return p.parse_args()


def _files_to_load(results_dir: Path, only: str) -> list[Path]:
    if only.strip():
        names = {n.strip() for n in only.split(",") if n.strip()}
        paths = [results_dir / n for n in names]
        missing = [p for p in paths if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing files: {missing}")
        return sorted(paths)
    return sorted(results_dir.glob("*.json"))


async def _seed(paths: list[Path]) -> None:
    handler = Neo4jHandler()
    try:
        ok = await handler.verify()
        if not ok:
            logger.error("Neo4j is not reachable at %s", config.NEO4J_URI)
            sys.exit(1)
        for path in paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.error("Failed to read %s: %s", path, e)
                raise
            phone = raw.get("phone")
            if not phone:
                logger.error("Skipping %s: missing required field 'phone'", path)
                raise ValueError(f"{path}: missing phone")
            entities = raw.get("entities")
            api_results = raw.get("api_results")
            if entities is None or api_results is None:
                logger.error("Skipping %s: missing 'entities' or 'api_results'", path)
                raise ValueError(f"{path}: missing entities or api_results")
            email = raw.get("email") or None
            darkweb = raw.get("darkweb")
            await handler.store_investigation(
                phone, email, api_results, entities, darkweb
            )
            logger.info("Seeded investigation for phone %s from %s", phone, path.name)
    finally:
        await handler.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    results_dir = args.dir.resolve()
    if not results_dir.is_dir():
        logger.error("Not a directory: %s", results_dir)
        sys.exit(1)
    try:
        paths = _files_to_load(results_dir, args.only)
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    if not paths:
        logger.warning("No JSON files found in %s", results_dir)
        sys.exit(0)
    asyncio.run(_seed(paths))
    logger.info("Done (%d file(s)).", len(paths))


if __name__ == "__main__":
    main()
