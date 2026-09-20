# LinkedIn Outreach Troubleshooting & Runbook

This guide contains diagnostic steps and remediations for common operational issues encountered during automated LinkedIn outreach.

---

## 1. Chrome Remote Debugging Not Connected / Port 9222

### Symptoms:
- `browser-use` fails with connection refused or cannot attach to `127.0.0.1:9222`.
- Script hangs or outputs empty results.

### Remediation:
1. Ensure Google Chrome is running.
2. In the Chrome window, navigate to `chrome://inspect/#remote-debugging`.
3. Check the box **"Allow remote debugging for this browser instance"**.
4. If a modal appears at the top asking *"Allow remote debugging?"*, click **"Allow"**.
5. Run the preflight check script:
   ```powershell
   python agent.py preflight
   ```

---

## 2. Invisible RTL Marks & Duplicate Prevention

### Symptoms:
- A contact is messaged more than once because LinkedIn inserts invisible Right-to-Left formatting marks (e.g. `\u200e`, `\u200f`) into profile names.
- Exact string equality fails (e.g., `"Rahul"` vs `"Rahul\u200e"`).
- Two different people share the same name and one of them gets skipped.

### Remediation:
All of this is handled centrally in `outreach/ledger.py` + `outreach/names.py` (single source of truth):

1. **Primary dedup key = profile URL slug** (`/in/<slug>`). Two people can share a name, never a slug. New ledger lines record the profile URL: `- Name (ts) - SENT - https://...`.
2. **Secondary key = normalized name** (for legacy ledger entries that have no URL):

```python
import unicodedata

def normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).replace("\u200e", "").replace("\u200f", "").strip()
```

3. Same-name disambiguation: if any SENT entry under that name carries a URL and none matches the contact's slug, it is a **different person** and will NOT be skipped. Legacy no-URL entries stay name-matched (conservative).

---

## 3. Connections Page Scroll Freeze (Virtualized List Stoppage)

### Symptoms:
- Navigating to `https://www.linkedin.com/mynetwork/invite-connect/connections/` only yields the first ~9 cards.
- Scrolling `main` element clamps (`scrollHeight` ≈ `clientHeight`) and does not load more cards.

### Remediation:
Use the **1st-Degree People Search Harvesting Strategy**:
- Navigate to `https://www.linkedin.com/search/results/people/?network=["F"]&page=<PAGE_NUM>`
- This search surface renders paginated 1st-degree connections (10 per page) with full pagination support (`&page=1`, `&page=2`, etc.).
- Use `python agent.py harvest --search-only`.

---

## 4. Send Button Disabled or Blocked

### Symptoms:
- Editor receives text, but `Send` button remains in `disabled: true` state.

### Remediation:
1. LinkedIn's form validation requires native input events.
2. Ensure both `input` and `change` events with `{ bubbles: true }` are dispatched immediately after CDP `Input.insertText`:
   ```javascript
   const el = document.querySelector('.msg-form__contenteditable');
   if (el) {
       el.dispatchEvent(new Event('input', { bubbles: true }));
       el.dispatchEvent(new Event('change', { bubbles: true }));
   }
   ```
3. Allow a 1.5s delay for frontend state stores to process the event.

---

## 5. Daily Safety Quota Exceeded

### Standard Policy:
- Default cap: **15 messages per calendar day** (set via `DAILY_LIMIT` in `data/.env`).
- `python agent.py send` parses the ledger (`data/Complete.md`) and counts **SENT + UNKNOWN** entries with today's date (UNKNOWN may have delivered, so it must consume budget — never overspend the cap). FAILED attempts do NOT consume budget; they are retried.
- Never bypass the daily cap unless the user explicitly requests an override (raise `DAILY_LIMIT` in `.env` or `$env:DAILY_LIMIT`).

---

## 6. Send Result Statuses (and what each means)

| Status | Meaning | Auto-retry? |
|---|---|---|
| `SENT` | Verified delivered: editor cleared + thread count grew + message text in thread tail | n/a (done forever) |
| `FAILED` | Definitely not sent (composer never opened, Send disabled/missing, text stuck in editor) | Yes — up to `MAX_ATTEMPTS` per run, and again on later runs |
| `UNKNOWN` | Possibly delivered (timeout after the send click, thread grew but state unconfirmed) | **Never** — protects against double-messaging |
| `SKIPPED` | The live LinkedIn thread already had messages, so nothing was sent | **Never** — done forever; consumes no daily quota |

If a contact is stuck as UNKNOWN but you are certain they never received the message, the only safe fix is a manual send.

---

## 7. Configuration via `.env`

All run-time settings are read from **`data/.env`** (loaded by `load_env()` in `outreach/config.py` on every command start). Keys: `LINKEDIN_CONNECTIONS_URL`, `TOP_N`, `DAILY_LIMIT`, `PACING`, `PACING_JITTER`, `MAX_ATTEMPTS`, `THREAD_CHECK`, `THREAD_CHECK_STRICT`, `START_IDX`, `SEARCH_MAX_PAGES`, `MAX_PAGES`, `START_PAGE`, `BU_TIMEOUT`, `PORTFOLIO_URL`. Rules: `KEY=value` per line, `#` comments, no quotes. A real environment variable overrides the `.env` value.

---

## 8. browser-use Script Crashes or Returns Nothing (NameError / SyntaxError)

### Symptoms:
- A send/harvest run logs every contact `FAILED` with "no RESULT from browser-use".
- `fetch_total_connections()` always returns `None`.

### Root causes (verified 2026-08-16):
1. **browser-use scripts are exec'd as Python.** Dict literals must use quoted keys: `{"found": False}` — NOT `{found: False}` (a JS object-literal style that Python reads as a name lookup → NameError).
2. **Backslash escapes are consumed twice.** The template string is parsed by Python twice (once in the host script, once when browser-use execs it), so `\n`/`\r`/`\d` inside embedded JS regexes arrive corrupted. Build separators and character classes without escapes: `String.fromCharCode(10)`, `[0-9]` instead of `\d`.

### Remediation:
These rules are already applied in all shipped templates (`SEND_JS`, `SEARCH_SWEEP_JS`, `COUNT_JS`, `CONNECTIONS_LINKS_JS`). Preserve them when editing templates, and keep the regression habit: mock-execute templates locally before a live run.

---

## 9. Contacts Logged `SKIPPED` (Live Thread Already Had Messages)

### Symptoms:
- A run logs contacts as `SKIPPED` with `conversation already has N message(s)`.
- Contacts you expected to message are never sent to.

### Why this is (usually) correct:
The live thread pre-check (`THREAD_CHECK_JS`) opened the contact's conversation and found existing messages — so messaging them again would be a duplicate. This catches cases the local ledger cannot: history lost/cleared, messages sent from another device, or a conversation started manually.

### Remediation:
1. **To message them anyway** (only if you are sure the thread is unrelated): set `THREAD_CHECK=0` in `data/.env` for that run. The ledger still dedups.
2. **Check inconclusive**: if the log shows `thread check inconclusive ...`, the message list/composer never mounted or browser-use timed out. Set `THREAD_CHECK_STRICT=1` to skip those safely instead of sending; leave it `0` to send and rely on the ledger.
3. `SKIPPED` is recorded in `data/Complete.md` and treated as done — those contacts are never retried. Remove the line manually only if you are certain it was a false positive.

---

## 11. `browser-use` Missing or Chrome Refuses Remote Debugging (Verified 2026-09-21)

### Symptoms:
- `[FAIL] 'browser-use' CLI not found on PATH` in the preflight.
- `browser-use --doctor` shows `chrome running` but `daemon alive` FAIL and `active browser connections — 0`.
- Chrome exits/logs `DevTools remote debugging requires a non-default data directory`.
- Port 9222 is held by another browser (e.g. Brave) that answers CDP paths with HTTP 404.

### Remediation:
1. Install the CLI:
   ```bash
   uv tool install browser-use      # installs browser-use to ~/.local/bin
   browser-use --version
   ```
2. Free port 9222 (only one browser can hold it) and launch Chrome with an **explicit profile**:
   ```bash
   google-chrome --user-data-dir="$PWD/linkedin_hunter/.chrome_profile" \
     --remote-debugging-port=9222 --remote-allow-origins='*' --no-first-run
   ```
   Chrome 153+ rejects `--remote-debugging-port` with the default profile. The `linkedin_hunter/.chrome_profile` data dir is a Chrome profile that is usually already logged into LinkedIn.
3. Confirm health: `browser-use --doctor` should show `chrome running`, `daemon alive`, and ≥1 connection. The daemon auto-starts on the first script.
4. Confirm login: navigate to `https://www.linkedin.com/feed/` — logged in stays on `/feed/`; expired redirects to `/login`.

---

## 10. Batch Freezes Mid-Run

### Symptoms:
- A send/harvest run hangs on one contact indefinitely.

### Remediation:
Every `browser-use` call now runs with a timeout (`BU_TIMEOUT`, default 180s). On timeout the call returns an error string instead of hanging: a send becomes `UNKNOWN` (if it timed out after the Send click — never retried) or `FAILED` (before the click — retried), and the batch continues. If timeouts repeat, run the preflight check: Chrome remote debugging is probably off or the daemon died.
