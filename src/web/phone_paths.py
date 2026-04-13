"""Helpers for results URLs, canonical Neo4j phone keys, and isolated graph mode."""

from __future__ import annotations

import re


def normalize_phone_key(s: str) -> str:
    return s.replace("+", "").replace("-", "").replace(" ", "")


def stem_ends_with_alone(stem: str) -> bool:
    return stem.endswith("_alone")


def canonical_phone_for_graph(data: dict, url_stem: str) -> str:
    """Neo4j stores Phone.number from JSON `phone`; URL stem may be `{digits}_epstein_alone`."""
    raw = data.get("phone")
    if raw is not None and str(raw).strip():
        return normalize_phone_key(str(raw))
    m = re.match(r"^(\d+)", url_stem)
    if m:
        return m.group(1)
    return normalize_phone_key(url_stem)


def display_title_for_results(data: dict, url_path_phone: str) -> str:
    return (data.get("display_name") or data.get("history_label") or url_path_phone).strip() or url_path_phone
