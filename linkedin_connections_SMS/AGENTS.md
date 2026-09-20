# LinkedIn Outreach Agent — Agent Operating Procedure

Automated LinkedIn DM outreach via `browser-use` (Chrome DevTools Protocol at `127.0.0.1:9222`). This file is the operating procedure for AI agents working in this repo.

## Documentation Discipline (MANDATORY RULE — READ FIRST)

> **ALWAYS update ALL docs after EACH section of work — no exceptions.**
> After finishing **every** section (harvest, send, verify, fix, investigation, progress check), update the relevant docs **before moving on**:
>
> 1. **`AGENTS.md`** (this file) — update **Workflow Notes** with any newly-verified gotcha or LinkedIn UI change (dated `Verified YYYY-MM-DD`).
> 2. **`docs/CONTINUE.md`** — refresh **Handoff State** and **What To Do Next** after every session-ending change.
> 3. **`data/Complete.md`** — append-only ledger; the dispatcher appends each SENT/FAILED/UNKNOWN automatically. Never edit or delete past entries.
> 4. **`README.md`** — mirror any change that affects commands, config, or structure.
> 5. **`data/message.py`** — if the outreach wording changed, note it in `docs/CONTINUE.md`.
> 6. **`data/progress.txt`** — refreshed automatically by `status`/`progress`/`send`; after any batch, run `python agent.py status` so the saved progress matches reality.
> 7. **`.agents/skills/linkedin-outreach-agent/SKILL.md` + `references/`** — keep in sync with behavior changes.
>
> If you hit a blocker or an unverified change, leave a `TODO(agent):` note in the relevant doc and log it in `docs/CONTINUE.md`. **Docs must never be stale at session end.**

## Trigger

When the user says "run the guide", "message top 10", "message next 25", "start outreach", "do 25 connections", etc.:

```powershell
python agent.py next              # harvest a batch + send + status (the one-shot)
python agent.py next --top 25     # explicit batch size
python agent.py next --pause 30   # review window between harvest and send
```

Then present the summary and update the docs (mandatory rule above).

**No START_IDX bookkeeping** — `send` reads the ledger and skips everyone already messaged, so "do the next 25" on any later day is just `python agent.py next` again.

## The One Interface

Everything goes through `python agent.py <command>` — never call module internals directly:

| Command | Purpose |
|---|---|
| `next` | harvest → send → status (add `--top`, `--limit`, `--pause`) |
| `harvest` | fill `data/contacts.json` (`--search-only`, `--start-page`, `--max-pages`) |
| `send` | message pending contacts (`--limit`, `--start-idx`) |
| `status` | quota + funnel report; refreshes `data/progress.txt` |
| `progress` | fetch total connections from LinkedIn |
| `preflight` | Chrome/CDP + quota + files diagnostics |
| `message` | preview the outreach message + where to edit it |
| `selftest` | run the test suite (no browser needed) |

## Repo Layout

| Path | What it is |
|---|---|
| `agent.py` | THE entry point (argparse CLI) |
| `outreach/` | Engine package: `config` (all paths/settings), `browser` (browser-use seam), `names`, `ledger`, `messaging`, `progress`, `harvest`, `dispatch`, `report` |
| `data/` | **Everything the user owns**: `.env` (config), `message.py` (the message wording), `Complete.md` (ledger, tracked), `contacts.json`, `progress.txt`, `total_connections.txt` (generated) |
| `tests/` | 38-test unittest suite — run `python agent.py selftest` |
| `docs/` | `linkedin_outreach_guide.md`, `CONTINUE.md` |
| `.agents/skills/linkedin-outreach-agent/` | Skill runbook + references (same CLI) |

**Design rules:** engine code only touches paths defined in `outreach/config.py`; tests cross module seams (no browser); all file writes inside `data/` are validated to stay there.

## Configuration

`data/.env` (gitignored, optional — every setting has a default). Session env vars override the file. Keys: `LINKEDIN_CONNECTIONS_URL`, `TOP_N`, `DAILY_LIMIT`, `PACING`, `PACING_JITTER`, `MAX_ATTEMPTS`, `THREAD_CHECK`, `THREAD_CHECK_STRICT`, `START_IDX`, `SEARCH_MAX_PAGES`, `MAX_PAGES`, `START_PAGE`, `BU_TIMEOUT`, `PORTFOLIO_URL`. See README for the reference table.

## Changing the Outreach Message

Edit **`data/message.py`**. Placeholders: `{name}` (full clean name — nothing else), `{portfolio}`, `{headline}` (headline captured during harvest). Preview with `python agent.py message`. Never edit engine code for wording.

## Workflow Notes (Verified 2026-08-16)

- Chrome must run with remote debugging at `127.0.0.1:9222` (`chrome://inspect/#remote-debugging`, tick the box; click **Allow** on the prompt once).
- **PowerShell has no heredocs** — browser scripts are piped to the `browser-use` CLI via `subprocess.run(input=...)` inside `outreach/browser.py`.
- **browser-use scripts run as Python**: dict literals need quoted keys (`{"found": False}`), and backslash escapes inside embedded JS get consumed twice — build separators with `String.fromCharCode(...)`, use `[0-9]` not `\d`. Both verified the hard way; the test suite (`selftest`) executes every template in a child process to catch regressions.
- **Connections page caps at ~9 cards** — the harvester tops up there, then paginates 1st-degree People Search (`network=["F"]&page=N`) up to `SEARCH_MAX_PAGES`, stopping after 3 consecutive empty pages.
- **Dual Compose Discovery**: profile pages expose `<a href="/messaging/compose/?profileUrn=...">Message</a>`; `dispatch` navigates there or uses direct compose URLs, then polls for `.msg-form__contenteditable`.
- **Send flow**: focus editor → `cdp("Input.insertText", base64)` → dispatch `input`/`change` events → click `Send` → verify editor empty AND thread count grew (before vs after) AND message text in thread tail.
- **Statuses**: `SENT` (verified) / `FAILED` (definitely not sent — retried up to `MAX_ATTEMPTS`, retryable across runs) / `UNKNOWN` (possibly delivered — NEVER retried; duplicate protection) / `SKIPPED` (the live thread already had messages — never retried, consumes no daily quota).
- **Dedup**: profile URL slug first, name second; same-name different-URL contacts are NOT skipped. Legacy no-URL ledger entries stay name-matched.
- **Live thread pre-check (Verified 2026-09-21)**: before every send, `dispatch.check_existing_thread()` opens the contact's conversation (compose URL, or profile → Message button) and counts existing messages via `THREAD_CHECK_JS`. If the thread already has messages the contact is logged `SKIPPED` and no text is inserted — a duplicate guard at the source of truth, not just the ledger. Toggle with `THREAD_CHECK=0`; `THREAD_CHECK_STRICT=1` also skips when the check is inconclusive (timeout / composer never mounted). `SKIPPED` is in `ledger.DONE_STATUSES` so those contacts are never retried.
- **Connections-page "see all" (Verified 2026-09-21)**: `CONNECTIONS_LINKS_JS` now scrolls the connections page 4× to lazy-load more cards before scraping; the People Search fallback still covers whatever stays hidden.
- **Runtime setup (Verified 2026-09-21)**: `browser-use` must be installed (`uv tool install browser-use`, currently 0.1.13). Chrome 153+ **refuses `--remote-debugging-port` with the default profile** — launch with an explicit data dir, e.g. `google-chrome --user-data-dir="$PWD/linkedin_hunter/.chrome_profile" --remote-debugging-port=9222 --remote-allow-origins='*'` (that profile is already LinkedIn-authenticated). Confirm with `browser-use --doctor` showing `chrome running` + `daemon alive` + ≥1 connection.
- **browser-use 0.1.13 (Verified 2026-09-21)**: piped scripts still expose the `js()` / `cdp()` / `print()` helpers the templates use, and the daemon auto-starts. The first call may print a one-time `Chrome is asking "Allow remote debugging?"` notice.
- **Login check (Verified 2026-09-21)**: navigate to `https://www.linkedin.com/feed/`; a logged-in session stays on `/feed/` (Bengali title `ফিড | LinkedIn`), an expired one redirects to `/login`.
- **Thread pre-check in the wild (Verified 2026-09-21)**: a 15-contact batch logged 13 `SENT` and 2 `SKIPPED` (threads already had 1 and 12 messages) — the live duplicate guard works against the real DOM.
- **Pacing & quota**: delay randomized `PACING..PACING×PACING_JITTER`; daily limit counts SENT + UNKNOWN; hung browser calls die at `BU_TIMEOUT`.
- **Name normalization** (dedup only): NFKC + invisible RTL marks (`\u200e`/`\u200f`) + degree badges (`• 1st`) stripped. The greeting uses the full name — no first-name or title handling. All in `outreach/names.py`.
