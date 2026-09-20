from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from outreach.config import LEDGER_FILE, REGISTRY_FILE
from outreach.ledger import append_ledger, parse_ledger
from outreach.names import clean_display_name, norm_name, profile_slug

DONE_STATUSES = frozenset({"SENT", "UNKNOWN", "SKIPPED"})

class ConnectionsRegistry:

    def __init__(self, path: str = REGISTRY_FILE, ledger_path: str = LEDGER_FILE):
        self.path = Path(path)
        self.ledger_path = Path(ledger_path)
        self.connections: dict[str, dict] = {}
        self.name_to_slug: dict[str, str] = {}
        self.last_sync: str = ""
        self.load()

    def _make_key(self, contact: dict | str) -> str:

        if isinstance(contact, str):
            slug = profile_slug(contact)
            return slug if slug else norm_name(contact)
        url = contact.get("profile_url") or contact.get("compose_url") or contact.get("url") or ""
        slug = profile_slug(url)
        if slug:
            return slug
        return norm_name(contact.get("name", ""))

    def load(self) -> None:

        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.connections = data.get("connections", {})
                self.last_sync = data.get("last_sync", "")
                self._rebuild_indices()
                return
            except Exception as e:
                print(f"[WARN] Error reading {self.path} ({e}); rebuilding from ledger...")

        self._migrate_from_ledger()
        self.save()

    def _rebuild_indices(self) -> None:

        self.name_to_slug = {}
        for key, record in self.connections.items():
            name = record.get("name", "")
            if name:
                self.name_to_slug[norm_name(name)] = key

    def _migrate_from_ledger(self) -> None:

        print(f"[*] Bootstrapping connection registry from {self.ledger_path}...")
        entries = parse_ledger(ledger_file=str(self.ledger_path))
        migrated = 0
        for e in entries:
            url = e.get("url", "")
            slug = profile_slug(url) if url else ""
            n_name = e.get("norm", "")
            key = slug if slug else n_name
            if not key:
                continue

            status = e.get("status", "SENT")
            self.connections[key] = {
                "name": e.get("name", ""),
                "slug": slug,
                "profile_url": url,
                "headline": "",
                "status": status,
                "sent_at": f"{e.get('date', '')} 12:00:00" if e.get("date") else "",
                "in_network": True,
                "migrated_from_ledger": True,
            }
            if n_name:
                self.name_to_slug[n_name] = key
            migrated += 1
        print(f"  [✓] Migrated {migrated} historical entries into registry.")

    def save(self) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)
        total_messaged = sum(1 for c in self.connections.values() if c.get("status") in ("SENT", "UNKNOWN"))
        payload = {
            "version": 2,
            "last_sync": self.last_sync or datetime.datetime.now().isoformat(),
            "total_tracked": len(self.connections),
            "messaged_count": total_messaged,
            "connections": self.connections,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_done(self, contact: dict | str) -> bool:

        key = self._make_key(contact)
        if key in self.connections:
            return self.connections[key].get("status") in DONE_STATUSES

        name = contact if isinstance(contact, str) else contact.get("name", "")
        n_name = norm_name(name)
        if n_name in self.name_to_slug:
            mapped_key = self.name_to_slug[n_name]
            return self.connections.get(mapped_key, {}).get("status") in DONE_STATUSES
        return False

    def get_record(self, contact: dict | str) -> dict | None:
        key = self._make_key(contact)
        if key in self.connections:
            return self.connections[key]
        name = contact if isinstance(contact, str) else contact.get("name", "")
        n_name = norm_name(name)
        if n_name in self.name_to_slug:
            return self.connections.get(self.name_to_slug[n_name])
        return None

    def sync_contact(self, name: str, profile_url: str, headline: str = "", compose_url: str = "") -> tuple[dict, bool]:

        slug = profile_slug(profile_url or compose_url)
        clean_name = clean_display_name(name)
        n_name = norm_name(name)
        key = slug if slug else n_name

        if key in self.connections:
            rec = self.connections[key]
            rec["in_network"] = True
            if headline and not rec.get("headline"):
                rec["headline"] = clean_display_name(headline)
            if profile_url and not rec.get("profile_url"):
                rec["profile_url"] = profile_url
            return rec, False

        if n_name in self.name_to_slug:
            existing_key = self.name_to_slug[n_name]
            rec = self.connections[existing_key]
            rec["in_network"] = True
            if slug and not rec.get("slug"):
                rec["slug"] = slug

                self.connections[slug] = rec
                del self.connections[existing_key]
                self.name_to_slug[n_name] = slug
            return rec, False

        new_record = {
            "name": clean_name,
            "slug": slug,
            "profile_url": profile_url or compose_url,
            "compose_url": compose_url or profile_url,
            "headline": clean_display_name(headline),
            "status": "UNSENT",
            "in_network": True,
            "discovered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.connections[key] = new_record
        if n_name:
            self.name_to_slug[n_name] = key
        return new_record, True

    def record_sent(self, contact: dict, archetype: str = "general", relevance: int | None = None,
                    detail: str = "") -> None:

        key = self._make_key(contact)
        clean_name = clean_display_name(contact.get("name", ""))
        url = contact.get("profile_url") or contact.get("compose_url") or ""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if key not in self.connections:
            self.sync_contact(clean_name, url)

        rec = self.connections[self._make_key(contact)]
        rec["status"] = "SENT"
        rec["sent_at"] = ts
        rec["archetype"] = archetype
        if relevance is not None:
            rec["relevance"] = relevance
        rec["detail"] = detail
        rec["in_network"] = True

        self.save()
        append_ledger(clean_name, "SENT", url=url, ledger_file=str(self.ledger_path))

    def record_skipped(self, contact: dict, reason: str, archetype: str = "",
                       relevance: int | None = None) -> None:

        key = self._make_key(contact)
        clean_name = clean_display_name(contact.get("name", ""))
        url = contact.get("profile_url") or contact.get("compose_url") or ""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if key not in self.connections:
            self.sync_contact(clean_name, url)

        rec = self.connections[self._make_key(contact)]
        rec["status"] = "SKIPPED"
        rec["skip_reason"] = reason
        rec["skipped_at"] = ts
        if archetype:
            rec["archetype"] = archetype
        if relevance is not None:
            rec["relevance"] = relevance
        rec["in_network"] = True

        self.save()
        append_ledger(clean_name, "SKIPPED", url=url, ledger_file=str(self.ledger_path))

    def record_failed(self, contact: dict, error: str) -> None:

        key = self._make_key(contact)
        clean_name = clean_display_name(contact.get("name", ""))
        url = contact.get("profile_url") or contact.get("compose_url") or ""

        if key in self.connections:
            self.connections[key]["status"] = "FAILED"
            self.connections[key]["last_error"] = error
            self.save()
        append_ledger(clean_name, "FAILED", url=url, ledger_file=str(self.ledger_path))

    def mark_removed(self, slug_or_name: str) -> None:

        key = profile_slug(slug_or_name) or norm_name(slug_or_name)
        if key in self.connections:
            self.connections[key]["in_network"] = False
            self.save()

    def count_sent_today(self, today: str | None = None) -> int:

        today = today or datetime.date.today().strftime("%Y-%m-%d")
        count = 0
        for rec in self.connections.values():
            if rec.get("status") in ("SENT", "UNKNOWN"):
                sent_at = rec.get("sent_at", "")
                if sent_at and sent_at.startswith(today):
                    count += 1
        return count

    def get_unsent_pool(self) -> list[dict]:

        return [
            rec for rec in self.connections.values()
            if rec.get("status") == "UNSENT" and rec.get("in_network", True)
        ]

    def get_stats(self) -> dict:
        total = len(self.connections)
        sent = sum(1 for c in self.connections.values() if c.get("status") == "SENT")
        skipped = sum(1 for c in self.connections.values() if c.get("status") == "SKIPPED")
        unsent = sum(1 for c in self.connections.values() if c.get("status") == "UNSENT")
        active = sum(1 for c in self.connections.values() if c.get("in_network", True))
        return {
            "total_tracked": total,
            "sent": sent,
            "skipped": skipped,
            "unsent": unsent,
            "active_in_network": active,
            "sent_today": self.count_sent_today(),
        }

_registry_instance: ConnectionsRegistry | None = None

def get_registry() -> ConnectionsRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ConnectionsRegistry()
    return _registry_instance
