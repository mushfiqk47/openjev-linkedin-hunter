# Continue LinkedIn Outreach — Next Session Prompt

Paste this into your next agent session to resume exactly where we left off.

---

## Latest Change (2026-09-21)

- **Live thread pre-check (duplicate guard at the source of truth).** Before every send, `outreach/dispatch.py` now runs `check_existing_thread()` — it opens the contact's conversation (compose URL, or profile → Message) via the new `THREAD_CHECK_JS` template and counts existing messages. If the thread already has messages, the contact is logged **`SKIPPED`** and nothing is inserted/sent. This catches what the ledger cannot (cleared history, messages sent from another device, manually-started conversations).
- **New status `SKIPPED`** lives in `ledger.DONE_STATUSES` (`SENT`, `UNKNOWN`, `SKIPPED`) → never retried, and it consumes **no** daily quota. `python agent.py status` now prints a Skipped count.
- **New config keys** in `data/.env`: `THREAD_CHECK` (default `1`) and `THREAD_CHECK_STRICT` (default `0`; `1` also skips inconclusive checks).
- **Connections page "see all"**: `CONNECTIONS_LINKS_JS` scrolls 4× to lazy-load more cards before scraping (People Search fallback unchanged).
- **Tests: 48 now** (was 38) — added thread-check decision/parse/template coverage and SKIPPED dedup. Run `python agent.py selftest`.

---

## Handoff State (as of 2026-09-21, after the first live batch)

- **240 outreach entries logged total** — **237 unique contacts messaged**, 2 FAILED (retryable: Faysal Al Nur, Sabrina Sultana — picked up again automatically once re-harvested), 0 UNKNOWN, **2 SKIPPED** (threads already had messages).
- **Daily usage 2026-09-21: 13 SENT / 15** — 2 sends left today; stop when the budget hits 0 (LinkedIn restricts burst patterns).
- **Pending in contacts.json: 0** — the harvested 15 are all logged; a fresh `harvest` (`python agent.py next`) refills it.
- **Total connections: unknown yet** — run `python agent.py progress` with Chrome+CDP on to fetch and save it (`data/total_connections.txt`), after which `data/progress.txt` shows the full `total / messaged / remaining` funnel.
- **Runtime**: `browser-use` 0.1.13 via `uv tool install browser-use`; Chrome launched with `--user-data-dir=linkedin_hunter/.chrome_profile --remote-debugging-port=9222` (the default profile is rejected for remote debugging).

### Codebase restructured 2026-08-16 (v2.0)

- **ONE entry point now**: `python agent.py <command>` — commands: `next` (harvest+send+status one-shot), `harvest`, `send`, `status`, `progress`, `preflight`, `message`, `selftest`. All old script paths are GONE.
- **Engine package**: `outreach/` (config, browser, names, ledger, messaging, progress, harvest, dispatch, report). Paths live only in `outreach/config.py`.
- **All user data in `data/`**: `.env` (config), `message.py` (the outreach message — edit wording here), `Complete.md` (ledger, git-tracked with full history), `contacts.json`, `progress.txt`, `total_connections.txt`.
- **Docs**: `AGENTS.md` at repo root; this file and `linkedin_outreach_guide.md` in `docs/`; skill runbook uses the same CLI.
- **Tests**: `python agent.py selftest` — 48 tests, browser-free (templates execute in a child process with mocked js()/cdp()).
- Engine behavior unchanged from the 2026-08-16 overhaul: URL-slug dedup, SENT/FAILED/UNKNOWN statuses, jittered pacing, retry-safe guarantees, BU_TIMEOUT hang protection.

### Batch history (condensed)

- **2026-08-15**: batches 1–4 (~48 contacts, incl. the RTL-mark duplicate "Rahul" that triggered the normalization engine)
- **2026-08-16 13:33–14:57**: batches 5–9 (~177 contacts, 2 FAILED) — sent with `$env:DAILY_LIMIT` raised; see the account-safety note below
- Full per-batch name lists live in git history of this file

---

## What To Do Next

1. Preflight (Chrome remote debugging must be on):
   ```powershell
   python agent.py preflight
   ```
2. Fetch + save the total connection count:
   ```powershell
   python agent.py progress
   ```
3. On a fresh day (or with an explicitly raised limit), run the one-shot:
   ```powershell
   python agent.py next --top 25
   ```
4. Check results any time:
   ```powershell
   python agent.py status
   ```

> ⚠️ **Account-safety recommendation:** 2026-08-16 saw 173 messages in ~90 minutes. Jittered pacing helps, but keep real daily volumes modest (the 15/day default exists for a reason) — LinkedIn restricts accounts for burst patterns.

---

## Prerequisites Before Running

- Chrome running with remote debugging at `127.0.0.1:9222` (`chrome://inspect/#remote-debugging`, "Allow remote debugging" ticked)
- If Chrome shows "Allow remote debugging?" — click Allow once
- Logged into LinkedIn in that Chrome session

---

## Context Files

| File | What it is |
|------|-----------|
| `AGENTS.md` (root) | Agent guide: CLI commands, repo layout, all verified gotchas, MANDATORY doc-update rule |
| `README.md` (root) | Product guide: commands, config, guardrails, data files |
| `data/Complete.md` | Append-only log of all messaged connections (225 entries, 222 unique) |
| `data/.env` | **Configuration**: limits, pacing + jitter, attempts, harvest sizes, portfolio URL |
| `data/message.py` | **The outreach message** — edit wording here; preview with `python agent.py message` |
| `data/contacts.json` | Generated contact list (names, URLs, headlines) |
| `data/progress.txt` / `data/total_connections.txt` | Saved funnel numbers |
| `outreach/` | The engine package (see `AGENTS.md` for the module map) |
| `tests/test_outreach.py` | The selftest suite (`python agent.py selftest`) |
| `docs/linkedin_outreach_guide.md` | Step-by-step guide (manual + automated) |

---

## Known Gotchas (Verified 2026-08-16)

- PowerShell has no heredocs → browser scripts pipe to `browser-use` via `subprocess.run(input=...)` in `outreach/browser.py`
- Connections page caps at ~9 cards → `harvest` automatically falls back to paginated 1st-degree People Search
- Profile pages expose `<a href="/messaging/compose/?profileUrn=...">Message</a>` which directly launches the compose view
- Names carry invisible RTL marks and degree badges (`• 1st`) → normalized in `outreach/names.py`
- **browser-use scripts run as Python**: quote dict keys (`{"found": False}`), and avoid `\n`-style escapes inside JS strings (use `String.fromCharCode`) — escapes are consumed twice
- Dispatch verifies editor-empty + thread-grew + message-in-tail before logging `SENT`
