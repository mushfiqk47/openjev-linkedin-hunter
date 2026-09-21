from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path
from typing import Callable

from outreach.config import RESTRICTED_FILE
from outreach.names import clean_display_name, norm_name, profile_slug

_restricted_cache: dict[str, any] | None = None
_cache_mtime: float = 0.0

def extract_slug_or_id(val: str) -> str:
    if not val:
        return ""
    slug = profile_slug(val)
    if slug:
        return slug
    unquoted = urllib.parse.unquote(val)
    m = re.search(r'(?:recipient|profileUrn)=([^&#]+)', unquoted)
    if m:
        return m.group(1).split(':')[-1].strip('/').lower()
    return ""

def load_restricted_list(file_path: str | None = None, force_reload: bool = False) -> dict[str, set[str]]:
    global _restricted_cache, _cache_mtime

    path = file_path or RESTRICTED_FILE
    if not os.path.exists(path):
        return {"names": set(), "slugs": set(), "raw": []}

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0

    if not force_reload and _restricted_cache is not None and mtime == _cache_mtime:
        return _restricted_cache

    names: set[str] = set()
    slugs: set[str] = set()
    raw_list: list[str] = []

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue

                raw_list.append(raw)

                # Check if it's a URL or slug
                slug = extract_slug_or_id(raw)
                if slug:
                    slugs.add(slug)

                # If no spaces and looks like a raw slug (e.g. "johndoe", "john-doe-123")
                if " " not in raw and "/" not in raw and slug:
                    slugs.add(slug)
                elif " " not in raw and "/" not in raw and len(raw) > 2:
                    slugs.add(raw.lower())

                # Normalized display name
                clean = clean_display_name(raw)
                normalized = norm_name(clean)
                if normalized:
                    names.add(normalized)
    except Exception as e:
        print(f"[WARN] Could not read restricted accounts file at {path}: {e}")

    result = {"names": names, "slugs": slugs, "raw": raw_list}
    _restricted_cache = result
    _cache_mtime = mtime
    return result

def is_restricted(
    contact_or_name: dict | str,
    restricted_data: dict[str, set[str]] | None = None,
    file_path: str | None = None,
) -> tuple[bool, str]:
    data = restricted_data if restricted_data is not None else load_restricted_list(file_path=file_path)
    names = data.get("names", set())
    slugs = data.get("slugs", set())

    if not names and not slugs:
        return False, ""

    if isinstance(contact_or_name, dict):
        if contact_or_name.get("status") == "RESTRICTED":
            return True, "already categorized as RESTRICTED"

        name = contact_or_name.get("name", "")
        n_name = norm_name(name)
        if n_name and n_name in names:
            return True, f"matched restricted name '{name}'"

        url = contact_or_name.get("profile_url") or contact_or_name.get("compose_url") or ""
        slug = extract_slug_or_id(url) or contact_or_name.get("slug", "")
        if slug and slug in slugs:
            return True, f"matched restricted profile slug '{slug}'"

        return False, ""

    # String identifier: either name or URL/slug
    val = str(contact_or_name).strip()
    slug = extract_slug_or_id(val)
    if slug and slug in slugs:
        return True, f"matched restricted profile slug '{slug}'"

    n_name = norm_name(val)
    if n_name and n_name in names:
        return True, f"matched restricted name '{val}'"

    if val.lower() in slugs:
        return True, f"matched restricted slug '{val}'"

    return False, ""

def apply_restricted_scan(
    registry,
    restricted_data: dict[str, set[str]] | None = None,
    on_event: Callable[[str, str], None] | None = None,
    file_path: str | None = None,
) -> int:
    log = on_event or (lambda msg, lvl="info": None)
    data = restricted_data if restricted_data is not None else load_restricted_list(file_path=file_path)
    if not data.get("names") and not data.get("slugs"):
        return 0

    restricted_count = 0
    for key, record in list(registry.connections.items()):
        if record.get("status") == "RESTRICTED":
            continue

        restricted, reason = is_restricted(record, restricted_data=data)
        if restricted:
            name = record.get("name", key)
            registry.record_restricted(record, reason=reason)
            restricted_count += 1
            log(f"Restricted connection detected: {name} ({reason}) — status updated to RESTRICTED", "warning")

    return restricted_count
