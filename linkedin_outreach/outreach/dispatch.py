import base64
import json
import time

from outreach.browser import run_bu_script
from outreach.messaging import build_message

SEND_JS = """
import base64, json, time

target_url = "__URL__"

if "/messaging/compose" in target_url:
    js(f"window.location.href = '{target_url}'")
    time.sleep(3.5)
else:
    js(f"window.location.href = '{target_url}'")
    time.sleep(3.0)
    msg_target = {}
    for _ in range(20):
        msg_target = js('''(() => {
            const msgAnchor = Array.from(document.querySelectorAll('a[href*="/messaging/compose"]')).find(a => {
                const txt = (a.innerText || '').trim();
                const aria = (a.getAttribute('aria-label') || '').trim();
                return txt === 'Message' || aria.startsWith('Message') || txt.startsWith('Message');
            });
            if (msgAnchor) return { found: true, href: msgAnchor.getAttribute('href') };
            const msgBtn = Array.from(document.querySelectorAll('button')).find(b => {
                const txt = (b.innerText || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                return txt === 'Message' || aria.startsWith('Message') || txt.startsWith('Message');
            });
            if (msgBtn) {
                msgBtn.click();
                return { found: true, clicked: true };
            }
            return { found: false };
        })()''') or {}
        if msg_target.get("found"):
            break
        time.sleep(0.5)

    if msg_target.get("href"):
        href = msg_target["href"]
        if not href.startswith('http'):
            href = 'https://www.linkedin.com' + href
        js(f"window.location.href = '{href}'")
        time.sleep(3.5)
    elif msg_target.get("clicked"):
        time.sleep(2.5)

editor = {"found": False}
for attempt in range(20):
    editor = js('''(() => {
        const el = document.querySelector('.msg-form__contenteditable');
        if (!el) return { found: false };
        el.focus();
        return { found: true };
    })()''') or {"found": False}
    if editor.get("found"):
        break
    time.sleep(0.8)

if not editor.get("found"):
    print("RESULT:" + json.dumps({"stage": "editor", "ok": False}))
else:
    before = js('''(() => {
        const thread = document.querySelector('.msg-s-message-list');
        return { count: thread ? thread.querySelectorAll('li').length : 0 };
    })()''') or {"count": 0}

    cdp("Input.insertText", text=base64.b64decode("__MSG_B64__").decode('utf-8'))

    js('''(() => {
        const el = document.querySelector('.msg-form__contenteditable');
        if (el) {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    })()''')
    time.sleep(2.0)

    send = {"found": False}
    for _ in range(16):
        send = js('''(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => {
                const t = (b.innerText || '').trim();
                const a = (b.getAttribute('aria-label') || '').trim();
                return t === 'Send' || a === 'Send' || (b.type === 'submit' && t.includes('Send'));
            });
            if (!btn) return { found: false };
            return { found: true, disabled: btn.disabled };
        })()''') or {"found": False}
        if send.get("found") and not send.get("disabled"):
            break
        time.sleep(0.5)

    if send.get("found") and not send.get("disabled"):
        js('''(() => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => {
                const t = (b.innerText || '').trim();
                const a = (b.getAttribute('aria-label') || '').trim();
                return t === 'Send' || a === 'Send' || (b.type === 'submit' && t.includes('Send'));
            });
            if (btn) btn.click();
        })()''')
        time.sleep(3.0)
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
            "stage": "sent",
            "beforeCount": before.get("count", 0),
            "afterCount": state.get("afterCount", 0),
            "editorEmpty": state.get("editorEmpty"),
            "threadTail": state.get("threadTail", "")
        }
        print("RESULT:" + json.dumps(result))
    else:
        print("RESULT:" + json.dumps({"stage": "send_button", "ok": False, "found": send.get("found"), "disabled": send.get("disabled")}))
"""

THREAD_CHECK_JS = """
import json, time

target_url = '__URL__'

if '/messaging/compose' in target_url:
    js(f"window.location.href = '{target_url}'")
    time.sleep(3.5)
else:
    js(f"window.location.href = '{target_url}'")
    time.sleep(3.0)
    msg_target = {}
    for _ in range(20):
        msg_target = js('''(() => {
            const msgAnchor = Array.from(document.querySelectorAll('a[href*="/messaging/compose"]')).find(a => {
                const txt = (a.innerText || '').trim();
                const aria = (a.getAttribute('aria-label') || '').trim();
                return txt === 'Message' || aria.startsWith('Message') || txt.startsWith('Message');
            });
            if (msgAnchor) return { found: true, href: msgAnchor.getAttribute('href') };
            const msgBtn = Array.from(document.querySelectorAll('button')).find(b => {
                const txt = (b.innerText || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                return txt === 'Message' || aria.startsWith('Message') || txt.startsWith('Message');
            });
            if (msgBtn) {
                msgBtn.click();
                return { found: true, clicked: true };
            }
            return { found: false };
        })()''') or {}
        if msg_target.get('found'):
            break
        time.sleep(0.5)

    if msg_target.get('href'):
        href = msg_target['href']
        if not href.startswith('http'):
            href = 'https://www.linkedin.com' + href
        js(f"window.location.href = '{href}'")
        time.sleep(3.5)
    elif msg_target.get('clicked'):
        time.sleep(2.5)

ready = False
for attempt in range(20):
    found = js('''(() => {
        return !!(document.querySelector('.msg-s-message-list') || document.querySelector('.msg-form__contenteditable'));
    })()''')
    if found:
        ready = True
        break
    time.sleep(0.8)

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

    if has_messages is True:
        return True, detail
    if has_messages is None and strict:
        return True, f"thread check inconclusive ({detail}); strict mode"
    return False, detail

def check_existing_thread(contact):

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
            print(f"    attempt {attempt} failed ({detail}); retrying in 3.0s...")
            time.sleep(3.0)
    return status, detail

