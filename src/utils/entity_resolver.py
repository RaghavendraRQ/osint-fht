"""Entity resolution – deduplication, normalization, confidence scoring."""

from __future__ import annotations

import re
from typing import Any


class EntityResolver:
    """Extracts and normalizes entities from API results into canonical sets."""

    def resolve(self, api_results: list[dict[str, Any]]) -> dict[str, list[dict]]:
        phones: dict[str, dict] = {}
        emails: dict[str, dict] = {}
        usernames: dict[str, dict] = {}
        profiles: dict[str, dict] = {}
        domains: dict[str, dict] = {}
        names: dict[str, dict] = {}

        for result in api_results:
            if not result.get("success"):
                continue
            source = result.get("source", "unknown")
            data = result.get("data", {})

            self._extract_phones(data, source, phones)
            self._extract_emails(data, source, emails)
            self._extract_usernames(data, source, usernames)
            self._extract_profiles(data, source, profiles)
            self._extract_domains(data, source, domains)
            self._extract_names(data, source, names)

        return {
            "phones": self._to_list_with_confidence(phones),
            "emails": self._to_list_with_confidence(emails),
            "usernames": self._to_list_with_confidence(usernames),
            "profiles": self._to_list_with_confidence(profiles),
            "domains": self._to_list_with_confidence(domains),
            "names": self._to_list_with_confidence(names),
        }

    def _extract_phones(self, data: dict, source: str, acc: dict):
        for key in ("number", "phone", "international_format", "local_format"):
            val = data.get(key)
            if val:
                norm = self._normalize_phone(str(val))
                self._upsert(acc, norm, source)

        for ph in data.get("phones", []):
            if isinstance(ph, dict):
                num = ph.get("e164Format") or ph.get("number") or ph.get("phone")
                if num:
                    self._upsert(acc, self._normalize_phone(str(num)), source)
            elif isinstance(ph, str):
                self._upsert(acc, self._normalize_phone(ph), source)

    def _extract_emails(self, data: dict, source: str, acc: dict):
        for key in ("email",):
            val = data.get(key)
            if isinstance(val, str) and "@" in val:
                self._upsert(acc, val.lower().strip(), source)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        addr = item.get("email") or item.get("value") or item.get("id")
                        if addr and "@" in str(addr):
                            self._upsert(acc, str(addr).lower().strip(), source)

        for em in data.get("emails", []):
            addr = em.get("email") or em.get("value") if isinstance(em, dict) else em
            if addr and "@" in str(addr):
                self._upsert(acc, str(addr).lower().strip(), source)

    def _extract_usernames(self, data: dict, source: str, acc: dict):
        for p in data.get("profiles", []):
            if isinstance(p, dict):
                un = p.get("username")
                if un:
                    self._upsert(acc, un.lower(), source)

    def _extract_profiles(self, data: dict, source: str, acc: dict):
        for p in data.get("profiles", []):
            if isinstance(p, dict):
                url = p.get("url")
                if url:
                    self._upsert(acc, url, source, extra={"site": p.get("site", "")})

    def _extract_domains(self, data: dict, source: str, acc: dict):
        di = data.get("domain_info")
        if isinstance(di, dict) and di.get("domain"):
            self._upsert(acc, di["domain"], source)
        for em in data.get("emails", []):
            addr = em.get("email") or em.get("value") if isinstance(em, dict) else em
            if addr and "@" in str(addr):
                domain = str(addr).split("@")[1].lower()
                self._upsert(acc, domain, source)

    def _extract_names(self, data: dict, source: str, acc: dict):
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            self._upsert(acc, name.strip(), source)
        elif isinstance(name, dict):
            full = f"{name.get('first', '')} {name.get('last', '')}".strip()
            if full:
                self._upsert(acc, full, source)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return re.sub(r"[^\d+]", "", phone)

    @staticmethod
    def _upsert(acc: dict, key: str, source: str, extra: dict | None = None):
        if not key:
            return
        if key not in acc:
            acc[key] = {"value": key, "sources": set(), "extra": extra or {}}
        acc[key]["sources"].add(source)

    @staticmethod
    def _to_list_with_confidence(acc: dict) -> list[dict]:
        items = []
        for key, entry in acc.items():
            sources = list(entry["sources"])
            items.append({
                "value": entry["value"],
                "sources": sources,
                "confidence": min(len(sources) / 3.0, 1.0),
                **entry.get("extra", {}),
            })
        items.sort(key=lambda x: x["confidence"], reverse=True)
        return items
