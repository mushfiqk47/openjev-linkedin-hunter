# LinkedIn Outreach Agent

Automated LinkedIn direct-message (DM) outreach for job hunting and lead generation. The agent harvests your 1st-degree connections, dispatches a personalized message to each one, verifies delivery, and logs every attempt — all driven through your own Chrome via DevTools Protocol. No external APIs, no third-party services, no dependencies beyond Python and the `browser-use` CLI.

**One entry point for everything:** `python agent.py <command>`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [The Commands](#the-commands)
3. [How It Works](#how-it-works)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Configuration](#configuration)
7. [The Outreach Message](#the-outreach-message)
8. [Safety Guardrails](#safety-guardrails)
9. [Data Files](#data-files)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)
12. [Documentation Map](#documentation-map)

---

## Quick Start

```powershell
# 0. One-time: enable Chrome remote debugging (see Prerequisites), then verify:
python agent.py preflight

# 1. Check your daily quota, pending contacts, and funnel progress:
python agent.py status

# 2. (Optional) Fetch your total connection count (needs Chrome+CDP):
python agent.py progress

# 3. THE ONE-SHOT: harvest the next batch and message it:
python agent.py next                    # = harvest 25 + send + status
python agent.py next --top 50           # bigger batch
python agent.py next --pause 30         # 30s review window before sending

# 4. Or run the steps individually:
python agent.py harvest                 # fill data/contacts.json (auto-skips messaged)
python agent.py send                    # message all pending (safe defaults)
```

**To message the next batch on a later day:** just run `python agent.py next` again. The dispatcher reads the ledger and automatically skips anyone already messaged, and refuses to exceed today's cap. No bookkeeping needed.

---

## The Commands

| Command | What it does |
|---|---|
| `python agent.py next` | One-shot: **harvest → send → status** (add `--pause SEC` for a review window) |
| `python agent.py harvest` | Fill `data/contacts.json` with unsent contacts (`--top N`, `--search-only`, `--start-page`, `--max-pages`) |
| `python agent.py send` | Message all pending contacts — enforces daily limit + jittered pacing (`--limit N` to override, `--start-idx N` to resume) |
| `python agent.py status` | Quota + funnel report; refreshes `data/progress.txt` |
| `python agent.py progress` | Fetch the total connection count from LinkedIn and save the funnel numbers |
| `python agent.py preflight` | Chrome/CDP + quota + files diagnostics |
| `python agent.py message` | Preview the outreach message + where to edit it |
| `python agent.py selftest` | Run the test suite (38 tests, no browser needed) |

Every command accepts `--help`.

---

## How It Works

```
You (Chrome, logged into LinkedIn, remote debugging on 127.0.0.1:9222)
        │
        ▼
preflight ──► verifies Chrome/CDP + quota + files
        │
        ▼
harvest ──► connections page top-up + paginated 1st-degree People Search
        │            ▼
        │      data/contacts.json (deduped vs ledger, headlines captured)
        ▼
send ──► for each pending contact:
        │    1. open compose (direct URL or profile → Message button)
        │    2. open the thread and count existing messages → if any, log SKIPPED and stop
        │    3. focus editor, inject text via CDP (base64-safe)
        │    4. dispatch input/change events → enable Send
        │    5. click Send, verify editor empty + thread grew + text in tail
        │    6. append "- Name (ts) - SENT/FAILED/UNKNOWN/SKIPPED - url" to the ledger
        ▼
status/progress ──► quota + total/messaged/remaining funnel (progress.txt)
```

**Key mechanism:** LinkedIn's compose overlay opens reliably via its direct URL (`/messaging/compose/?recipient=...`), which the harvester extracts from "Send a message" links — no fragile synthetic clicks on cards.

---

## Project Structure

```
Linkdin sms agent/
├── agent.py                     ← THE entry point: python agent.py <command>
├── outreach/                    ← the engine (importable package)
│   ├── config.py                ← every path + setting (single source of truth)
│   ├── evaluator.py             ← SemIf contact relevance & archetype classifier
│   ├── browser.py               ← browser-use execution seam (timeout-protected)
│   ├── names.py                 ← name/URL normalization + dedup keys
│   ├── ledger.py                ← Complete.md: parse, query, append
│   ├── messaging.py             ← message rendering from data/message.py
│   ├── progress.py              ← total/messaged/remaining funnel tracking
│   ├── harvest.py               ← contact harvesting (2 strategies)
│   ├── dispatch.py              ← sending, delivery verification, retry
│   └── report.py                ← status + preflight diagnostics
├── data/                        ← EVERYTHING you own and edit
│   ├── .env                     ← configuration (gitignored)
│   ├── message.py               ← THE OUTREACH MESSAGE (edit wording here)
│   ├── Complete.md              ← append-only ledger (tracked in git)
│   ├── contacts.json            ← harvested contacts (generated)
│   ├── progress.txt             ← funnel snapshot (generated)
│   └── total_connections.txt    ← LinkedIn connection total (generated)
├── tests/
│   └── test_outreach.py         ← 55-test suite (runs without a browser)
├── docs/
│   ├── linkedin_outreach_guide.md   ← step-by-step guide (manual + automated)
│   └── CONTINUE.md                  ← session handoff notes
├── AGENTS.md                    ← operating procedure for AI agents
├── README.md                    ← this file
├── LICENSE                      ← MIT
└── .agents/skills/linkedin-outreach-agent/   ← agent skill wrapper
    ├── SKILL.md                 ← skill runbook (uses the same CLI)
    └── references/              ← selectors, troubleshooting, harvest strategies
```

**Design rule:** engine code never touches a path that isn't defined in `outreach/config.py`, and everything user-editable lives in `data/`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.9+** | The engine uses only the standard library. |
| **`browser-use` CLI** | Must be on your PATH. The preflight command verifies it. |
| **Google Chrome** | The same Chrome instance you're logged into LinkedIn with. |
| **Chrome remote debugging** | In that Chrome, open `chrome://inspect/#remote-debugging`, tick **"Allow remote debugging for this browser instance"**. If a prompt appears, click **Allow** once. |
| **LinkedIn session** | Logged in, in that Chrome window. |

---

## Configuration

Everything is configured in **`data/.env`** — edit it once, every command reads it on start:

```env
LINKEDIN_CONNECTIONS_URL=https://www.linkedin.com/mynetwork/invite-connect/connections/
TOP_N=25
DAILY_LIMIT=15
PACING=6
PACING_JITTER=2.5
MAX_ATTEMPTS=2
START_IDX=0
MAX_PAGES=10
START_PAGE=1
SEARCH_MAX_PAGES=50
BU_TIMEOUT=180
PORTFOLIO_URL=https://mushfiqkabiruix.vercel.app/
```

**Rules:** one `KEY=value` per line; `#` starts a comment; no quotes. A value exported in your terminal overrides the file (e.g. `$env:DAILY_LIMIT="50"`). The file is optional — every setting has a built-in default.

### Reference table

| Var | Default | Used by | Meaning |
|---|---|---|---|
| `LINKEDIN_CONNECTIONS_URL` | connections page | harvest | Page scraped for "Send a message" links |
| `TOP_N` | `25` | harvest | How many unsent contacts to save |
| `DAILY_LIMIT` | `15` | send, status, preflight | Max messages per calendar day (SENT + UNKNOWN count) |
| `PACING` | `6` | send | Minimum seconds between sends |
| `PACING_JITTER` | `2.5` | send | Delay randomized up to `PACING × PACING_JITTER` (anti-fingerprint) |
| `MAX_ATTEMPTS` | `2` | send | Attempts per contact for definite FAILEDs (UNKNOWN never retried) |
| `THREAD_CHECK` | `1` | send | Live pre-check: open the contact's thread and skip if it already has messages |
| `THREAD_CHECK_STRICT` | `0` | send | `1` = also skip when the thread check is inconclusive (timeout/unmounted) |
| `START_IDX` | `0` | send | Resume offset into the pending list |
| `SEARCH_MAX_PAGES` | `50` | harvest | Search sweep bound |
| `MAX_PAGES` / `START_PAGE` | `10` / `1` | harvest `--search-only` | Search page bounds |
| `BU_TIMEOUT` | `180` | all browser calls | Seconds before a hung browser-use call is killed |
| `PORTFOLIO_URL` | portfolio site | message | Work link embedded in every message |

---

## The Outreach Message

The message lives in **`data/message.py`** — edit that file to change what gets sent (never touch the engine). Preview any time with `python agent.py message`. Placeholders:

| Placeholder | Replaced with |
|---|---|
| `{name}` | The full clean name, e.g. "Md. Rakibul Islam" — nothing else, no first-name guessing |
| `{portfolio}` | `PORTFOLIO_URL` from `.env` |
| `{headline}` | The contact's LinkedIn headline, captured during harvest (may be empty) |

A personalized `{headline}` opener example is included as a comment in the file — personalized openers typically get far more replies.

---

## Safety Guardrails

1. **Daily cap** — `DAILY_LIMIT` (default 15/day) stops sending once today's ledger count reaches it (SENT + UNKNOWN both count — UNKNOWN may have delivered, so it must consume budget).
2. **Jittered pacing** — a random delay between `PACING` and `PACING × PACING_JITTER` seconds (default 6–15s) between sends. Fixed intervals are a bot fingerprint.
3. **Dual-key deduplication** — contacts are matched against the ledger by **profile URL slug first, name second**. Two people who share a name are never confused (when URLs are known); names are normalized (NFKC, RTL marks stripped, degree badges removed) for legacy entries. FAILED contacts stay retryable.
4. **Live thread pre-check (source of truth)** — before sending, the agent opens the contact's conversation and counts existing messages. If the thread already has any, the contact is logged `SKIPPED` and nothing is sent — so a duplicate is caught even when the local ledger is missing, stale, or was rebuilt. Toggle with `THREAD_CHECK=0`; `THREAD_CHECK_STRICT=1` also skips inconclusive checks. `SKIPPED` contacts are never retried and consume no daily quota.
5. **Delivery verification + no-duplicate guarantee** — a send is logged `SENT` only if the editor cleared AND the thread grew AND the message text appears in the thread tail. Unconfirmable outcomes are logged `UNKNOWN` and are **never retried** — the same person can never receive the message twice by mistake. Definite failures (`FAILED`) are retried up to `MAX_ATTEMPTS`.
6. **Append-only ledger** — `data/Complete.md` entries are never edited or deleted.
7. **Hang protection** — browser-use calls are killed after `BU_TIMEOUT`; one contact's crash never stops the batch.

---

## Data Files

### `data/contacts.json` (generated)

```json
[
  {
    "name": "Sanzida Akter",
    "compose_url": "https://www.linkedin.com/in/sanzida-akter-49476340b/en/",
    "profile_url": "https://www.linkedin.com/in/sanzida-akter-49476340b/en/",
    "headline": "UI/UX Designer"
  }
]
```

### `data/Complete.md` (append-only ledger)

```
- Name (YYYY-MM-DD HH:MM:SS) - SENT - https://www.linkedin.com/in/profile-url/
- Name (YYYY-MM-DD HH:MM:SS) - FAILED
- Name (YYYY-MM-DD HH:MM:SS) - UNKNOWN
- Name (YYYY-MM-DD HH:MM:SS) - SKIPPED        ← live thread already had messages
- Name (YYYY-MM-DD HH:MM:SS)                  ← legacy format, counts as SENT
```

**Never delete or edit past lines.** The ledger is the source of truth for dedup and daily limits.

### `data/progress.txt` + `data/total_connections.txt` (generated)

The outreach funnel, saved so you (or an AI session) always know where things stand — e.g. `400 total / 226 messaged / 174 remaining`. `status` refreshes it every run; `progress` additionally fetches the live connection total.

---

## Testing

```powershell
python agent.py selftest                 # or: python -m unittest discover tests
```

48 tests, all browser-free: name normalization, ledger parsing (against the real ledger), same-name dedup disambiguation, the full SENT/FAILED/UNKNOWN/SKIPPED classification matrix, the live thread pre-check decision + parsing, message templating, and every browser-use template executed end-to-end in a child process with a mocked browser (plus `node --check` syntax validation of all embedded JS when node is available).

---

## Troubleshooting

Run the preflight first — it checks Chrome/CDP, quota, and required files:

```powershell
python agent.py preflight
```

| Symptom | Fix |
|---|---|
| `browser-use` can't connect / port 9222 refused | Chrome must run with remote debugging enabled (`chrome://inspect/#remote-debugging`, tick the box, **Allow**) |
| Only ~9 contacts harvested from the connections page | Expected — the harvester automatically falls back to paginated 1st-degree People Search |
| Send button stays disabled | The editor needs native `input`/`change` events after text injection (built in); check the 1.5s processing delay |
| `DAILY_LIMIT_REACHED` | You've hit the daily cap — stop for today, or explicitly raise `DAILY_LIMIT` (only if you accept the risk) |
| Same person messaged twice | Should be impossible — `UNKNOWN` never auto-retries; if you see it, check the ledger for manual edits |
| A contact is `UNKNOWN` but never got the message | Only a manual send is safe; auto-retry is disabled by design |

Full runbook: `.agents/skills/linkedin-outreach-agent/references/troubleshooting.md`

---

## Documentation Map

| Doc | Purpose |
|---|---|
| `AGENTS.md` | Operating procedure + verified workflow notes for AI agents |
| `docs/linkedin_outreach_guide.md` | Step-by-step guide (manual + automated) |
| `docs/CONTINUE.md` | Session handoff state — paste into the next session to resume |
| `.agents/skills/linkedin-outreach-agent/SKILL.md` | Agent skill runbook (uses the same CLI) |
| `.agents/skills/linkedin-outreach-agent/references/` | DOM selectors, troubleshooting, harvest strategies |

---

> **Use responsibly.** Automated messaging can get LinkedIn accounts restricted. Keep `DAILY_LIMIT` at a safe level, respect pacing, and only override limits when you accept the risk.
