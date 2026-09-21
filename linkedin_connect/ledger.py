from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROJECT_ROOT

REGISTRY_FILE = DATA_DIR / "connect_registry.json"
LEDGER_FILE = DATA_DIR / "Connects.md"
LOCAL_RESTRICTED_FILE = DATA_DIR / "restricted.txt"
OUTREACH_RESTRICTED_FILE = PROJECT_ROOT / "linkedin_outreach" / "data" / "restricted.txt"
OUTREACH_REGISTRY_FILE = PROJECT_ROOT / "linkedin_outreach" / "data" / "connections_registry.json"

def profile_slug(url_or_slug: str) -> str:
    if not url_or_slug:
        return ""
    clean = url_or_slug.strip().rstrip("/")
    if "/in/" in clean:
        parts = clean.split("/in/")[-1].split("?")[0].split("/")
        return parts[0].strip().lower()
    if "/" not in clean and "?" not in clean:
        return clean.strip().lower()
    return ""

def norm_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", " ", n)
    return " ".join(n.split())

class ConnectLedger:
    def __init__(self):
        self.registry_path = REGISTRY_FILE
        self.ledger_path = LEDGER_FILE
        self.records: dict[str, dict[str, Any]] = {}
        self.outreach_slugs: set[str] = set()
        self.restricted_names: set[str] = set()
        self.restricted_slugs: set[str] = set()

        self._load_registry()
        self._load_outreach_connections()
        self._load_restricted_list()

    def _load_registry(self):
        if self.registry_path.is_file():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            except Exception:
                self.records = {}
        else:
            self.records = {}

    def _save_registry(self):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        tmp.replace(self.registry_path)

    def _load_outreach_connections(self):
        if OUTREACH_REGISTRY_FILE.is_file():
            try:
                with open(OUTREACH_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conns = data.get("connections", {})
                    for slug, rec in conns.items():
                        self.outreach_slugs.add(slug.lower())
                        href = rec.get("profile_url") or rec.get("urn") or ""
                        s = profile_slug(href)
                        if s:
                            self.outreach_slugs.add(s)
            except Exception:
                pass

    def _load_restricted_list(self):
        files_to_check = [OUTREACH_RESTRICTED_FILE, LOCAL_RESTRICTED_FILE]
        for p in files_to_check:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            raw = line.strip()
                            if not raw or raw.startswith("#"):
                                continue
                            s = profile_slug(raw)
                            if s:
                                self.restricted_slugs.add(s)
                            if " " in raw:
                                self.restricted_names.add(norm_name(raw))
                            else:
                                self.restricted_slugs.add(raw.lower())
                except Exception:
                    pass

    def is_restricted(self, name: str, profile_url: str) -> bool:
        s = profile_slug(profile_url)
        if s and s in self.restricted_slugs:
            return True
        n = norm_name(name)
        if n and n in self.restricted_names:
            return True
        return False

    def is_already_connected_or_messaged(self, profile_url: str) -> bool:
        s = profile_slug(profile_url)
        return bool(s and s in self.outreach_slugs)

    def is_handled(self, profile_url: str) -> bool:
        s = profile_slug(profile_url)
        if not s:
            return False
        if s in self.records:
            status = self.records[s].get("status")
            return status in ("SENT", "PENDING", "RESTRICTED")
        return False

    def get_today_sent_count(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        count = 0
        for r in self.records.values():
            if r.get("status") == "SENT":
                sent_at = r.get("sent_at", "")
                if sent_at.startswith(today):
                    count += 1
        return count

    def record_sent(self, name: str, profile_url: str, headline: str,
                    archetype: str, score: int, reason: str = ""):
        s = profile_slug(profile_url) or norm_name(name)
        now_iso = datetime.now(timezone.utc).isoformat()
        now_disp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.records[s] = {
            "name": name,
            "profile_url": profile_url,
            "headline": headline,
            "archetype": archetype,
            "score": score,
            "status": "SENT",
            "sent_at": now_iso,
            "reason": reason,
        }
        self._save_registry()

        line = f"- [{now_disp}] **{name}** ({archetype}, Score: {score}%) - SENT - [Profile]({profile_url}) - _{reason}_\n"
        self._append_ledger(line)

    def record_skipped(self, name: str, profile_url: str, headline: str,
                       archetype: str, score: int, reason: str = ""):
        s = profile_slug(profile_url) or norm_name(name)
        now_iso = datetime.now(timezone.utc).isoformat()

        self.records[s] = {
            "name": name,
            "profile_url": profile_url,
            "headline": headline,
            "archetype": archetype,
            "score": score,
            "status": "SKIPPED",
            "skipped_at": now_iso,
            "reason": reason,
        }
        self._save_registry()

    def record_restricted(self, name: str, profile_url: str, headline: str):
        s = profile_slug(profile_url) or norm_name(name)
        now_iso = datetime.now(timezone.utc).isoformat()
        now_disp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.records[s] = {
            "name": name,
            "profile_url": profile_url,
            "headline": headline,
            "archetype": "restricted_account",
            "score": 0,
            "status": "RESTRICTED",
            "restricted_at": now_iso,
            "reason": "Matched blacklist entries in restricted.txt",
        }
        self._save_registry()

        line = f"- [{now_disp}] **{name}** - RESTRICTED - [Profile]({profile_url})\n"
        self._append_ledger(line)

    def _append_ledger(self, line: str):
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.is_file():
            header = "# Targeted LinkedIn Connection Requests Audit Ledger\n\n"
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                f.write(header)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(line)

_instance: ConnectLedger | None = None

def get_ledger() -> ConnectLedger:
    global _instance
    if _instance is None:
        _instance = ConnectLedger()
    return _instance
