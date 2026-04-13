#!/usr/bin/env python3
"""Copy investigation JSON files to `{phone}_{slug}_alone.json` and set history labels for isolated demos."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.web.phone_paths import normalize_phone_key  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_RESULTS_DIR = ROOT / "data" / "results"


def _slug_from_stem(stem: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return s or "case"


def _label_from_slug(slug: str) -> str:
    return slug.replace("_", " ").strip().title() + " — isolated graph"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "For each investigation JSON, write data/results/{phone}_{slug}_alone.json "
            "with the same payload plus history_label (and optional display_name) so the "
            "web UI opens an isolated entity graph and History shows a clear title."
        )
    )
    p.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more investigation JSON files (pipeline output shape).",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Output directory (default: {DEFAULT_RESULTS_DIR})",
    )
    p.add_argument(
        "--slug",
        type=str,
        default="",
        help="Slug for output filename (single input only). Default: derived from input basename.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing *_alone.json files.",
    )
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    out_dir: Path = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = [p.resolve() for p in args.inputs]
    if args.slug.strip() and len(inputs) != 1:
        logger.error("--slug may only be used with exactly one INPUT file.")
        sys.exit(2)

    for path in inputs:
        if not path.is_file():
            logger.error("Not a file: %s", path)
            sys.exit(1)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Invalid JSON %s: %s", path, e)
            sys.exit(1)

        raw_phone = data.get("phone")
        if not raw_phone:
            logger.error("%s: missing top-level 'phone' field", path)
            sys.exit(1)
        phone_norm = normalize_phone_key(str(raw_phone))

        slug = args.slug.strip().lower().replace(" ", "_") if args.slug.strip() else _slug_from_stem(path.stem)
        slug = re.sub(r"[^a-z0-9_]+", "_", slug).strip("_") or "case"

        out_name = f"{phone_norm}_{slug}_alone.json"
        dest = out_dir / out_name

        if dest.exists() and not args.force:
            logger.warning("Skip %s (exists). Use --force to overwrite.", dest)
            continue

        data = dict(data)
        label = _label_from_slug(slug)
        data["history_label"] = label
        data["display_name"] = label

        dest.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        logger.info("Wrote %s (from %s, hub phone=%s)", dest.name, path.name, phone_norm)


if __name__ == "__main__":
    main()
