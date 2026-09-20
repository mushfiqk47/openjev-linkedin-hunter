"""Message dispatch: send personalized DMs to pending contacts.

Behavior:
  - Skips anyone logged SENT/UNKNOWN/SKIPPED in the ledger (matched by name OR
    profile URL, so two people with the same name are never confused).
  - Live thread pre-check (THREAD_CHECK, on by default): opens the contact's
    conversation and, if it already has messages, logs SKIPPED instead of
    sending — a duplicate guard against the source of truth, not just the
    local ledger. THREAD_CHECK_STRICT=1 also skips when the check is
    inconclusive.
  - Enforces DAILY_LIMIT (SENT + UNKNOWN count toward it) and jittered
    PACING (fixed intervals look bot-like).
  - Verifies delivery: editor cleared AND thread grew AND message text in
    the thread tail.
  - FAILED sends are retried up to MAX_ATTEMPTS; UNKNOWN outcomes (may have
    delivered) are never retried — a message cannot be sent twice.
  - Appends one ledger line per contact and refreshes progress.txt.
"""
import base64
import json
import os
import random
import time
from datetime import date

from outreach.browser import run_bu_script
from outreach.config import (CONTACTS_FILE, DEFAULT_FILTER_LOW_RELEVANCE,
                             DEFAULT_MIN_RELEVANCE_SCORE, get_float, get_int)
from outreach.evaluator import evaluate_contact
from outreach.ledger import (append_ledger, count_sent_today, is_messaged,
                             norm_name, parse_ledger, profile_slug, sent_keys)
from outreach.messaging import build_message
from outreach.progress import refresh_progress

# Browser-use script for one send. Outer quotes are triple-DOUBLE; the inner
# js(...) calls use triple-single. Placeholders: __URL__, __MSG_B64__.
SEND_JS = """
import base64, json, time

target_url = \"__URL__\"

if \"/messaging/compose\" in target_url:
    js(f\"window.location.href = '{target_url}'\")
    time.sleep(3)
else:
    # Profile URL: navigate, then find the Message button / compose anchor
    js(f\"window.location.href = '{target_url}'\")
    time.sleep(3)
    msg_target = js('''(() => {
        const msgAnchor = Array.from(document.querySelectorAll('a[href*=\"/messaging/compose\"]')).find(a => (a.innerText || '').trim() === 'Message');
        if (msgAnchor) {
            return { found: true, href: msgAnchor.getAttribute('href') };
        }
        const msgBtn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'Message');
        if (msgBtn) {
            msgBtn.click();
            return { found: true, clicked: true };
        }
        return { found: false };
    })()''')

    msg_target = msg_target or {}
    if msg_target.get(\"href\"):
        href = msg_target[\"href\"]
        if not href.startswith('http'):
            href = 'https://www.linkedin.com' + href
        js(f\"window.location.href = '{href}'\")
        time.sleep(3)
    elif msg_target.get(\"clicked\"):
        time.sleep(2)

# Poll for the composer to mount (max ~10s)
editor = {\"found\": False}
for attempt in range(10):
    editor = js('''(() => {
        const el = document.querySelector('.msg-form__contenteditable');
        if (!el) return { found: false };
        el.focus();
        return { found: true };
    })()''') or {\"found\": False}
    if editor.get(\"found\"):
        break
    time.sleep(1.0)

if not editor.get(\"found\"):
    print(\"RESULT:\" + json.dumps({\"stage\": \"editor\", \"ok\": False}))
else:
    before = js('''(() => {
        const thread = document.querySelector('.msg-s-message-list');
        return { count: thread ? thread.querySelectorAll('li').length : 0 };
    })()''') or {\"count\": 0}

    cdp(\"Input.insertText\", text=base64.b64decode(\"__MSG_B64__\").decode('utf-8'))

    js('''(() => {
        const el = document.querySelector('.msg-form__contenteditable');
        if (el) {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    })()''')
    time.sleep(1.5)

    send = js('''(() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'Send');
        if (!btn) return { found: false };
        return { found: true, disabled: btn.disabled };
    })()''') or {\"found\": False}

    if send.get(\"found\") and not send.get(\"disabled\"):
        js('''(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'Send');
            if (btn) btn.click();
        })()''')
        time.sleep(3)
        state = js('''(() => {
            const thread = document.querySelector('.msg-s-message-list');
            const ed = document.querySelector('.msg-form__contenteditable');
            return {
                afterCount: thread ? thread.querySelectorAll('li').length : 0,
                editorEmpty: ed ? ed.innerText.trim() === '' : null,
                threadTail: thread ? thread.innerText.slice(-600) : ''
            };
        })()''') or {}
        result = {
            \"stage\": \"sent\",
            \"beforeCount\": before.get(\"count\", 0),
            \"afterCount\": state.get(\"afterCount\", 0),
            \"editorEmpty\": state.get(\"editorEmpty\"),
            \"threadTail\": state.get(\"threadTail\", \"\")
        }
        print(\"RESULT:\" + json.dumps(result))
    else:
        print(\"RESULT:\" + json.dumps({\"stage\": \"send_button\", \"ok\": False, \"found\": send.get(\"found\"), \"disabled\": send.get(\"disabled\")}))
"""


# Live thread pre-check (feature: source-of-truth duplicate guard).
#
# Navigates to the contact's conversation (compose URL, or profile -> Message)
# and counts any messages ALREADY in the thread BEFORE inserting text. If a
# conversation exists, the caller skips the send entirely. Placeholder: __URL__.
#
# Template-authoring rules: browser-use execs this as Python, so dict keys are
# quoted and embedded JS avoids backslash escapes (single quotes only).
THREAD_CHECK_JS = """
import json, time

target_url = '__URL__'

if '/messaging/compose' in target_url:
    js(f"window.location.href = '{target_url}'")
    time.sleep(3)
else:
    # Profile URL: navigate, then find the Message button / compose anchor
    js(f"window.location.href = '{target_url}'")
    time.sleep(3)
    msg_target = js('''(() => {
        const msgAnchor = Array.from(document.querySelectorAll('a[href*="/messaging/compose"]')).find(a => (a.innerText || '').trim() === 'Message');
        if (msgAnchor) {
            return { found: true, href: msgAnchor.getAttribute('href') };
        }
        const msgBtn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'Message');
        if (msgBtn) {
            msgBtn.click();
            return { found: true, clicked: true };
        }
        return { found: false };
    })()''')

    msg_target = msg_target or {}
    if msg_target.get('href'):
        href = msg_target['href']
        if not href.startswith('http'):
            href = 'https://www.linkedin.com' + href
        js(f"window.location.href = '{href}'")
        time.sleep(3)
    elif msg_target.get('clicked'):
        time.sleep(2)

# Poll until the conversation (message list) or composer renders (max ~10s)
ready = False
for attempt in range(10):
    found = js('''(() => {
        return !!(document.querySelector('.msg-s-message-list') || document.querySelector('.msg-form__contenteditable'));
    })()''')
    if found:
        ready = True
        break
    time.sleep(1.0)

existing = js('''(() => {
    const list = document.querySelector('.msg-s-message-list');
    if (!list) return { hasMessages: false, count: 0 };
    const events = list.querySelectorAll('.msg-s-event-listitem');
    if (events.length) return { hasMessages: true, count: events.length };
    let messages = 0;
    list.querySelectorAll('li').forEach(li => {
        if (li.querySelector('.msg-s-message-list__time-heading, .msg-s-message-list__new-message-divider')) return;
        if ((li.innerText || '').trim()) messages += 1;
    });
    return { hasMessages: messages > 0, count: messages };
})()''') or { 'hasMessages': False, 'count': 0 }

print("THREAD:" + json.dumps({ 'ready': ready, 'hasMessages': existing.get('hasMessages'), 'count': existing.get('count', 0) }))
"""


def thread_decision(has_messages, detail, strict=False):
    """Should the send be skipped because the thread already has messages?

    ``has_messages`` is True/False, or None when the check was inconclusive.
    Returns (skip, reason). In strict mode an inconclusive check also skips, so
    a duplicate is never risked; otherwise the caller proceeds and relies on
    the ledger for dedup.
    """
    if has_messages is True:
        return True, detail
    if has_messages is None and strict:
        return True, f"thread check inconclusive ({detail}); strict mode"
    return False, detail


def check_existing_thread(contact):
    """Open the conversation and report whether it already has messages.

    Returns (has_messages, detail): True (already messaged -> skip),
    False (empty conversation -> safe to send), or None (inconclusive).
    """
    url = contact.get("compose_url") or contact.get("profile_url", "")
    script = THREAD_CHECK_JS.replace(
        "__URL__", url.replace("\\", "\\\\").replace("'", "\\'"))
    out, err = run_bu_script(script)
    payload = None
    for line in out.splitlines():
        if line.startswith("THREAD:"):
            try:
                payload = json.loads(line[len("THREAD:"):].strip())
            except Exception:
                payload = None
            break
    if payload is None:
        timed_out = bool(err) and err.strip().upper().startswith("TIMEOUT")
        return None, "no THREAD result" + (" (browser-use timed out)" if timed_out else "")
    if payload.get("hasMessages"):
        return True, f"conversation already has {payload.get('count', '?')} message(s)"
    if not payload.get("ready"):
        return None, "message list / composer never mounted"
    return False, "conversation is empty"


def classify(result, marker, timed_out=False):
    """Map a RESULT payload to (status, detail).
    SENT = delivered (thread grew + editor cleared); UNKNOWN = possibly
    delivered — never auto-retry (a thread that grew means SOMETHING was
    sent, so retrying could duplicate the DM); FAILED = definitely not sent."""
    if result is None:
        if timed_out:
            return "UNKNOWN", "no RESULT and browser-use timed out (send state unknown)"
        return "FAILED", "no RESULT from browser-use"
    if result.get("stage") != "sent":
        return "FAILED", f"stopped before sending (stage: {result.get('stage')}, found: {result.get('found')}, disabled: {result.get('disabled')})"
    editor_empty = result.get("editorEmpty") is True
    grew = result.get("afterCount", 0) > result.get("beforeCount", 0)
    tail = result.get("threadTail") or ""
    if grew:
        if editor_empty:
            detail = "verified" if marker in tail else "delivered (marker not in thread tail)"
            return "SENT", detail
        return "UNKNOWN", "thread grew but editor state unconfirmed"
    if editor_empty:
        return "UNKNOWN", "editor cleared but thread did not grow"
    return "FAILED", "editor still contains the message text"


def send_with_retries(contact, max_attempts):
    """Try to message one contact; retries only definite failures.
    Returns (status, detail)."""
    url = contact.get("compose_url") or contact.get("profile_url", "")
    msg = build_message(contact["name"], contact)
    marker = msg.strip().split("\n")[-1][:60]
    script = (SEND_JS
              .replace("__URL__", url.replace("\\", "\\\\").replace('"', '\\"'))
              .replace("__MSG_B64__", base64.b64encode(msg.encode("utf-8")).decode("ascii")))
    status, detail = "FAILED", "not attempted"
    for attempt in range(1, max_attempts + 1):
        out, err = run_bu_script(script)
        result = None
        for line in out.splitlines():
            if line.startswith("RESULT:"):
                try:
                    result = json.loads(line[len("RESULT:"):].strip())
                except Exception:
                    result = None
                break
        timed_out = bool(err) and err.strip().upper().startswith("TIMEOUT")
        status, detail = classify(result, marker, timed_out=timed_out)
        if status != "FAILED":
            break
        if err and err.strip():
            detail += f" | stderr: {err.strip()[:150]}"
        if attempt < max_attempts:
            print(f"    attempt {attempt} failed ({detail}); retrying in 10s...")
            time.sleep(10)
    return status, detail


def load_pending(entries, sent_names, sent_slugs, start_idx=0):
    """Pending = not SENT/UNKNOWN by name or slug, deduped within the file."""
    if not os.path.exists(CONTACTS_FILE):
        return None
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            contacts = json.load(f)
    except Exception:
        return None
    pending, seen = [], set()
    for c in contacts:
        key = profile_slug(c.get("profile_url") or c.get("compose_url") or "") or norm_name(c.get("name", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        if not is_messaged(c, entries, sent_names, sent_slugs):
            pending.append(c)
    return pending[start_idx:]


def run(limit=None, start_idx=None, dry_run=False):
    """CLI: dispatch messages to pending contacts (safe by default)."""
    today = date.today().strftime("%Y-%m-%d")
    pacing = get_int("PACING", 6)
    pacing_jitter = get_float("PACING_JITTER", 2.5)
    max_attempts = max(1, get_int("MAX_ATTEMPTS", 2))
    start_idx = start_idx if start_idx is not None else get_int("START_IDX", 0)
    daily_limit = limit if limit is not None else get_int("DAILY_LIMIT", 15)

    thread_check = get_int("THREAD_CHECK", 1) != 0
    thread_check_strict = get_int("THREAD_CHECK_STRICT", 0) != 0
    filter_low_relevance = get_int("FILTER_LOW_RELEVANCE", DEFAULT_FILTER_LOW_RELEVANCE) != 0
    min_relevance = get_int("MIN_RELEVANCE_SCORE", DEFAULT_MIN_RELEVANCE_SCORE)

    entries = parse_ledger()
    sent_names, sent_slugs = sent_keys(entries)
    sent_today = count_sent_today(entries)
    remaining_budget = daily_limit - sent_today

    if not os.path.exists(CONTACTS_FILE):
        print(f"NO_CONTACTS_FILE: {CONTACTS_FILE} is missing - harvesting needed first.")
        refresh_progress()
        return []
    pending = load_pending(entries, sent_names, sent_slugs, start_idx)
    if pending is None:
        print(f"CONTACTS_FILE_ERROR: could not read contacts.json.")
        refresh_progress()
        return []

    if remaining_budget <= 0:
        print(f"DAILY_LIMIT_REACHED: {sent_today} already SENT today ({today}); limit is {daily_limit}.")
        print("Stop for today, or raise DAILY_LIMIT in data/.env / environment if you accept the risk.")
        refresh_progress()
        return []
    if not pending:
        print("NOTHING_TO_SEND: every contact in contacts.json is already logged in the ledger.")
        refresh_progress()
        return []
    if len(pending) > remaining_budget:
        print(f"BUDGET_WARNING: {len(pending)} pending but only {remaining_budget} left today "
              f"(limit {daily_limit}). Sending the first {remaining_budget}.")
        pending = pending[:remaining_budget]

    mode_str = " [DRY-RUN SIMULATION]" if dry_run else ""
    print(f"PLAN{mode_str}: send to {len(pending)} contacts (already messaged: {len(sent_names)}, "
          f"sent today: {sent_today}, budget left: {remaining_budget}, pacing: {pacing}-{round(pacing * pacing_jitter)}s jittered, "
          f"thread check: {'on' if thread_check else 'off'}{' (strict)' if thread_check and thread_check_strict else ''}, "
          f"semif filter: {'on (>=' + str(min_relevance) + '%)' if filter_low_relevance else 'off'})")

    results = []
    for i, c in enumerate(pending):
        name = c["name"]
        url = c.get("profile_url") or c.get("compose_url") or ""
        print(f"\n===== CONTACT {i + 1}/{len(pending)}: {name} =====")

        # SemIf: evaluate contact relevance & classify archetype
        eval_res = evaluate_contact(c)
        c["archetype"] = eval_res.get("archetype", "general")
        c["relevance"] = eval_res.get("relevance", 60)
        c["eval_reason"] = eval_res.get("reason", "")
        print(f"    [SemIf] Archetype: {c['archetype']} | Relevance: {c['relevance']}% ({eval_res.get('backend')})")
        if c["eval_reason"]:
            print(f"    [SemIf Detail] {c['eval_reason']}")

        # Low-relevance filter: skip and log to avoid wasting daily send quota
        if filter_low_relevance and c["relevance"] < min_relevance:
            status = "SKIPPED"
            detail = f"low relevance score ({c['relevance']}% < {min_relevance}%, {c['archetype']})"
            print(f"    [skip] {detail}")
            if not dry_run:
                append_ledger(name, status, url=url)
            results.append({"name": name, "status": status, "detail": detail})
            continue

        # Live duplicate guard: skip anyone whose LinkedIn conversation already
        # has messages, before spending typing/send actions on them.
        skipped = False
        status, detail = "FAILED", "not attempted"
        if thread_check and not dry_run:
            has_messages, check_detail = check_existing_thread(c)
            skipped, reason = thread_decision(has_messages, check_detail, strict=thread_check_strict)
            if skipped:
                status, detail = "SKIPPED", reason
                print(f"    [skip] {reason}")
            elif has_messages is None:
                print(f"    [warn] thread check inconclusive ({check_detail}); sending (ledger still dedups)")
        if not skipped:
            if dry_run:
                status = "SIMULATED"
                preview = build_message(name, c).replace('\n', ' ')[:90]
                detail = f"dry-run: would send [{c['archetype']}]: {preview}..."
                print(f"    [DRY-RUN] {detail}")
            else:
                try:
                    status, detail = send_with_retries(c, max_attempts)
                except Exception as e:
                    status, detail = "FAILED", f"unexpected error: {e}"
        if not dry_run:
            append_ledger(name, status, url=url)
            print(f"--> Status: {status} ({detail}) | logged to Complete.md")
        else:
            print(f"--> Status: {status} ({detail}) [simulated - ledger unchanged]")
        results.append({"name": name, "status": status, "detail": detail})
        if not dry_run and i < len(pending) - 1:
            delay = random.uniform(pacing, pacing * max(1.0, pacing_jitter))
            print(f"----- pacing {round(delay)}s before next contact -----")
            time.sleep(delay)

    print("\n==================================================")
    print("             OUTREACH BATCH COMPLETE              ")
    print("==================================================")
    for r in results:
        print(f"  - {r['name']}: {r['status']} ({r['detail']})")
    try:
        progress = refresh_progress()
        remaining_str = progress["remaining"] if progress["remaining"] is not None else "unknown"
        print("--------------------------------------------------")
        print(f"Progress: {progress['messaged_unique']} messaged of "
              f"{progress['total_connections'] if progress['total_connections'] is not None else 'unknown'} "
              f"connections ({remaining_str} remaining) - saved to progress.txt")
    except Exception as e:
        print(f"[WARN] could not refresh progress.txt: {e}")
    print("==================================================")
    return results
