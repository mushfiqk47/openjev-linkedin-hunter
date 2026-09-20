# LinkedIn Outreach Guide: Messaging Your Top Connections

This guide outlines a simple, repeatable process for reaching out to your LinkedIn connections. Whether you are performing this task manually or building an automation script, follow these steps in order.

## Prerequisites

- Read `AGENTS.md` at the repo root first — it contains the **complete profile**: the CLI commands, repo layout, and all verified workflow notes (Chrome remote debugging at `127.0.0.1:9222`, PowerShell limitations, LinkedIn compose-URL approach, send/verify flow, pacing).
- **Enable Chrome remote debugging**: open `chrome://inspect/#remote-debugging` in the Chrome window you want to automate and tick "Allow remote debugging for this browser instance" (if Chrome prompts, click Allow once).
- Make sure you are logged into your LinkedIn account.
- Have `data/Complete.md` ready to log the names of the people you contact (append-only; the agent appends each line automatically: name + timestamp + status + profile URL).

## Automated Run (Recommended)

Everything goes through one CLI at the repo root. The message itself lives in **`data/message.py`** — edit wording there, never in the engine.

```powershell
# 0. (Optional, once per session) fetch your total connection count:
python agent.py progress

# 1. THE ONE-SHOT: harvest the next batch, send to it, report status:
python agent.py next

# Or run the steps individually:
python agent.py harvest                 # fill data/contacts.json (TOP_N, default 25)
python agent.py send                    # message pending contacts (jittered pacing)
python agent.py status                  # refresh the saved progress (total / messaged / remaining)
```

Env vars (all optional; edit `data/.env` to set them permanently): `LINKEDIN_CONNECTIONS_URL` (connections page URL, default `https://www.linkedin.com/mynetwork/invite-connect/connections/`), `TOP_N` (fetch count, default 25), `DAILY_LIMIT` (max messages per day — the daily "SMS" limit, default 15; SENT + UNKNOWN count toward it), `PACING` + `PACING_JITTER` (delay randomized between `PACING` and `PACING × PACING_JITTER` seconds, default 6–15s), `MAX_ATTEMPTS` (retries per definite failure, default 2), `THREAD_CHECK` (live pre-check that opens the thread and skips contacts who already have messages, default 1), `THREAD_CHECK_STRICT` (1 = also skip inconclusive checks, default 0), `START_IDX` (resume offset into the pending list, default 0), `SEARCH_MAX_PAGES` (search sweep bound for `harvest`, default 50), `MAX_PAGES` / `START_PAGE` (bounds for `harvest --search-only`, default 10 / 1), `BU_TIMEOUT` (kill hung browser calls, default 180s), `PORTFOLIO_URL` (work link in the message, default `https://mushfiqkabiruix.vercel.app/`).

No setup needed between batches: `python agent.py send` reads the ledger and automatically skips anyone logged SENT, UNKNOWN or SKIPPED, and refuses to send once today's limit is reached. It also opens each contact's thread first and logs `SKIPPED` if a conversation already exists (so a duplicate is caught even if the ledger missed it). FAILED contacts stay retryable and get picked up again automatically. To message the next batch on any later day, just run `python agent.py next` again.

## Step-by-Step Instructions (Manual)

### 1. Navigate to your Connections

Open your web browser and go to your LinkedIn connections page:

[https://www.linkedin.com/mynetwork/invite-connect/connections/](https://www.linkedin.com/mynetwork/invite-connect/connections/)

### 2. Process Each Connection

Repeat the following sequence for each connection in the list (top 10 by default; adjust per AGENTS.md):

#### A. Open the Message Window

Locate the connection's card and click the **"Message"** button. This will open the direct messaging box (often at the bottom right of the screen).

#### B. Prepare and Send the Message

The message lives in **`data/message.py`** (that is the single place to change the wording — preview with `python agent.py message`). Copy the rendered template, taking care to replace `[Connection's name]` with the actual full name of the person you are messaging — or use the available placeholders (`{name}`, `{portfolio}`, `{headline}`) when sending through the agent:

```text
Hi, [Connection's name]

I hope all is well with you. I wanted to let you know I'm currently searching for a job or any project-based work. If you ever have something I could help with or know of any leads, it would genuinely mean a lot to me right now.
To see my work: https://mushfiqkabiruix.vercel.app/

Thank you for taking the time to read this!
```

Paste the tailored message into the text box and hit **Send**.

#### C. Close the Message Window

After confirming the message has been sent, close the active message box by clicking the **"X"** (close) button located in the top-right corner of the message window.

#### D. Record the Connection

Append the name of the user you just messaged to `data/Complete.md`. When done manually, use the full format so every command can parse it:

```markdown
- John Doe (2026-08-15 10:38:00) - SENT - https://www.linkedin.com/in/john-doe/
```

Statuses: `SENT` (verified delivered), `FAILED` (definitely not sent — retryable), `UNKNOWN` (possibly delivered — never retry, to avoid duplicates), `SKIPPED` (live thread already had messages — never retry, no quota spent).

### 3. Repeat

Continue this exact process (Steps A through D) for the next connection in the list until you have successfully messaged and recorded all connections.

## Automation Notes (Verified 2026-08-16)

- The connections-page Message overlay does **not** open via CDP coordinate clicks or synthetic DOM clicks. Working approach: extract each connection's `/messaging/compose/?recipient=...` href (the same link the Message button points to) and navigate directly to it — the composer is pre-filled.
- Send flow: focus `.msg-form__contenteditable` → `Input.insertText` (base64-decoded) → dispatch `input`/`change` events → find button with innerText `Send` → verify enabled → click → verify editor empty AND thread count grew AND the message text appears in the thread tail.
- Send statuses: `SENT` (verified), `FAILED` (definitely not sent; auto-retried up to `MAX_ATTEMPTS` and retryable on later runs), `UNKNOWN` (possibly delivered; never retried — duplicate protection), `SKIPPED` (live thread already had messages; never retried, costs no quota).
- Dedup: profile URL slug first, name second (NFKC + RTL marks + degree badges stripped). Same-name different-person contacts are not skipped when URLs are known.
- **browser-use scripts run as Python**: dict literals need quoted keys (`{"found": False}`), and backslash escapes inside embedded JS are consumed twice — build separators with `String.fromCharCode(10)` instead of `\n`.
- Pacing is randomized between `PACING` and `PACING × PACING_JITTER` (default 6–15s); daily safety limit 15 messages (per parent `AGENTS.md`); hung browser-use calls are killed after `BU_TIMEOUT` (180s).
- AX tree `backendDOMNodeId` values are stale across runs — fetch the AX tree and box model in the same script run as the click.
- **Connections page loads only ~9 cards (verified 2026-08-15, still true 2026-08-16)** — RESOLVED: `python agent.py harvest` tops up there, then automatically paginates the 1st-degree People Search (`network=["F"]&page=N`) up to `SEARCH_MAX_PAGES` to find unsent contacts.
- Progress funnel (`total / messaged / remaining / sent today`) is saved to `data/progress.txt` by `status` after every run and by `progress` (which also fetches the live connection total).