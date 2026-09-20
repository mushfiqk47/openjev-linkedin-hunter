---
name: linkedin-outreach-agent
description: >-
  Automates end-to-end LinkedIn direct message outreach via Chrome DevTools Protocol (CDP).
  Use this skill whenever the user asks to run outreach, message top or next connections,
  harvest LinkedIn contacts, inspect daily message quotas, or troubleshoot LinkedIn automation scripts.
---

# LinkedIn Outreach Agent Skill

An automated runbook and toolkit for reliable LinkedIn direct message outreach using `browser-use` connected via Chrome DevTools Protocol (`127.0.0.1:9222`).

**Everything goes through one CLI** (run from the repo root):

```
python agent.py <command>
```

---

## ⚡ Quick Start: 1-Click Operations

> **Configure first:** all run-time settings live in **`data/.env`**; the message wording lives in **`data/message.py`** (placeholders `{name}` (full name), `{portfolio}`, `{headline}`). Edit those files — never the engine.

### 1. Run the Whole Outreach Flow (harvest + send + report)
```powershell
python agent.py next                  # harvest 25, send, report
python agent.py next --top 50         # bigger batch
python agent.py next --pause 30       # 30s review window before sending
```

### 2. Check Status, Quota & Progress
Sent counts, remaining daily allowance (15/day safety limit), pending contacts, and the total/messaged/remaining funnel (saves `data/progress.txt`):
```powershell
python agent.py status
```

### 3. Fetch Total Connections & Save Progress
Reads the LinkedIn connection total via Chrome (e.g. `400 total / 226 messaged / 174 remaining`):
```powershell
python agent.py progress
```

### 4. Harvest New Connections Only
```powershell
python agent.py harvest                       # connections page + paginated search
python agent.py harvest --search-only         # People Search sweep directly
python agent.py harvest --top 50 --max-pages 20
```

### 5. Dispatch Messages Only
Verified delivery, automatic ledger dedup (name + profile URL), failure retry, jittered pacing, daily-limit guardrails:
```powershell
python agent.py send                          # safe defaults
python agent.py send --limit 50               # explicit limit override
```

### 6. Run Pre-Flight Diagnostics
Chrome/CDP endpoint, quota, and required files:
```powershell
python agent.py preflight
```

### 7. Preview the Outreach Message
```powershell
python agent.py message
```

### 8. Run the Test Suite (no browser needed)
```powershell
python agent.py selftest
```

---

## 🛠 Architecture & Core Components

| Component | Path | Description |
|-----------|------|-------------|
| **CLI entry point** | `agent.py` | argparse subcommands: next, harvest, send, status, progress, preflight, message, selftest |
| **Config** | `outreach/config.py` | Every path + setting (single source of truth) |
| **Browser seam** | `outreach/browser.py` | browser-use subprocess execution, timeout-protected |
| **Name/dedup keys** | `outreach/names.py` | NFKC + RTL-mark normalization, profile slugs |
| **Ledger** | `outreach/ledger.py` | `data/Complete.md` parsing, dedup queries, appends |
| **Message** | `outreach/messaging.py` | Renders `data/message.py` with placeholders |
| **Progress** | `outreach/progress.py` | total/messaged/remaining funnel (`data/progress.txt`) |
| **Harvester** | `outreach/harvest.py` | Connections page + paginated 1st-degree search |
| **Dispatcher** | `outreach/dispatch.py` | Compose discovery, live thread pre-check (skip if already messaged), CDP typing, verified send, retry |
| **Reports** | `outreach/report.py` | status + preflight diagnostics |
| **Tests** | `tests/test_outreach.py` | 48 browser-free tests (templates execute in a child process) |

---

## 📖 Deep References

- [DOM Selectors & CDP Interaction Guide](./references/selectors_and_dom.md)
- [Troubleshooting & Gotchas Runbook](./references/troubleshooting.md)
- [Connection Harvesting Strategies](./references/connection_harvesting_strategies.md)

---

## 🔒 Safety & Rate-Limiting Policy

1. **Daily Safety Limit**: Capped at **15 messages/day** by default (`DAILY_LIMIT`) — SENT + UNKNOWN both consume budget.
2. **Jittered Pacing**: Delay randomized between `PACING` and `PACING × PACING_JITTER` seconds (default 6–15s) — fixed intervals are a bot fingerprint.
3. **Dual-Key Deduplication**: profile URL slug first, normalized name second — same-name different-person contacts are not skipped when URLs are known. FAILED stays retryable; SENT, UNKNOWN and SKIPPED never re-send.
4. **Live Thread Pre-Check**: before sending, the agent opens the contact's conversation and counts existing messages. If the thread already has messages it logs `SKIPPED` and sends nothing — a duplicate guard at the source of truth. `THREAD_CHECK=0` disables it; `THREAD_CHECK_STRICT=1` also skips inconclusive checks. SKIPPED costs no quota.
5. **Delivery Verification + No-Duplicate Guarantee**: `SENT` requires editor empty AND thread count grew AND message text in the thread tail. Unconfirmable outcomes are `UNKNOWN` and never auto-retried. Definite failures retry up to `MAX_ATTEMPTS`.
6. **Hang Protection**: browser-use calls die at `BU_TIMEOUT` (180s); one contact's failure never stops the batch.

---

## 📝 Mandatory Documentation Discipline

After completing any outreach batch or debugging session, always update:
1. **`data/Complete.md`**: logged automatically by the dispatcher — never edit past lines.
2. **`docs/CONTINUE.md`**: refresh the handoff state, remaining budget, and next steps.
3. **`AGENTS.md`** (repo root): update workflow notes with any newly observed LinkedIn UI changes.
4. **`data/progress.txt`**: run `python agent.py status` after each batch so the saved funnel matches reality.
