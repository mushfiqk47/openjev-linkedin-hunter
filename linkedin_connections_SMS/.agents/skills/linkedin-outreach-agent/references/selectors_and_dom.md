# LinkedIn DOM Selectors & CDP Interaction Guide

This reference documents the verified DOM selectors, CDP methods, and URL structures used for LinkedIn direct message outreach automation.

---

## 1. Direct Compose URL Architecture

LinkedIn's DOM messaging overlay cannot be reliably triggered via synthetic JavaScript click events (`.click()`) or CDP coordinate clicks from connection cards. Instead, direct navigation to the compose endpoint pre-populates the chat overlay immediately.

### URL Structure:
```text
https://www.linkedin.com/messaging/compose/?profileUrn=urn%3Ali%3Afsd_profile%3A<PROFILE_URN>&recipient=<PROFILE_URN>&interop=msgOverlay
```

### Extraction Logic:
On the standard connections page (`/mynetwork/invite-connect/connections/`), connection cards contain anchor tags with `aria-label="Send a message to <Name>"`. The `href` attribute of this anchor tag contains the exact direct compose URL.

```javascript
// Extract all message links on connections page
const links = [];
document.querySelectorAll('a[aria-label^="Send a message"]').forEach(a => {
  links.push({
    label: a.getAttribute('aria-label') || '',
    href: a.getAttribute('href') || ''
  });
});
```

---

## 2. Message Editor Selectors & Text Injection

### Editor Target Selector:
- Primary: `.msg-form__contenteditable`
- Attributes: `role="textbox"`, `aria-label="Write a message..."`, `contenteditable="true"`

### Injection Sequence via CDP:
1. **Focus the element:**
   ```javascript
   const el = document.querySelector('.msg-form__contenteditable');
   if (el) el.focus();
   ```
2. **Inject text via CDP `Input.insertText`:**
   ```python
   # Base64 decode message to prevent character escape / encoding corruption
   cdp("Input.insertText", text=decoded_message)
   ```
3. **Dispatch synthetic DOM input/change events:**
   LinkedIn's Ember/React state store requires input events to enable the Send button.
   ```javascript
   const el = document.querySelector('.msg-form__contenteditable');
   if (el) {
     el.dispatchEvent(new Event('input', { bubbles: true }));
     el.dispatchEvent(new Event('change', { bubbles: true }));
   }
   ```

---

## 3. Send Button Selectors & State Check

### Selector Strategy:
Find all buttons and filter by inner text:
```javascript
const btn = Array.from(document.querySelectorAll('button')).find(
  b => (b.innerText || '').trim() === 'Send'
);
const canSend = btn && !btn.disabled;
```

### Triggering Send:
```javascript
btn.click();
```

---

## 4. Post-Send Verification

Capture the thread item count BEFORE clicking Send, then verify AFTER. A send operation is only logged `SENT` when **all three** checks pass:

1. The message editor is completely cleared:
   ```javascript
   const ed = document.querySelector('.msg-form__contenteditable');
   const isCleared = ed && ed.innerText.trim() === '';
   ```
2. The message list thread grew (after vs. before the click):
   ```javascript
   const thread = document.querySelector('.msg-s-message-list');
   const count = thread ? thread.querySelectorAll('li').length : 0;
   ```
3. The thread tail contains the sent message's last line (marker check):
   ```javascript
   const tail = thread ? thread.innerText.slice(-600) : '';
   ```

### Status mapping (`classify()` in `outreach/dispatch.py`):

| Observation | Status | Retried? |
|---|---|---|
| Editor cleared + thread grew (+ marker in tail) | `SENT` (verified) | never again |
| Editor cleared + thread grew (marker missing) | `SENT` (delivered) | never again |
| Thread grew but editor state unconfirmed / editor cleared but thread didn't grow / timeout after the Send click | `UNKNOWN` | **never** (duplicate protection) |
| Composer never mounted, Send disabled/missing, or text still stuck in the editor | `FAILED` | yes, up to `MAX_ATTEMPTS` |
| Live thread pre-check found existing messages (nothing inserted) | `SKIPPED` | **never** (duplicate protection; no quota spent) |

### Live thread pre-check selectors (`THREAD_CHECK_JS`)

Before any text is inserted, the pre-check opens the conversation and counts existing messages. A non-empty thread means the contact was already messaged, so the send is skipped.

```javascript
// Existing messages in the open conversation
const list = document.querySelector('.msg-s-message-list');
const events = list ? list.querySelectorAll('.msg-s-event-listitem') : [];
const hasMessages = events.length > 0;
```

- `.msg-s-message-list` — the conversation history container (absent on a brand-new compose).
- `.msg-s-event-listitem` — one message bubble; the primary count. Date separators use `.msg-s-message-list__time-heading` / `.msg-s-message-list__new-message-divider` and are excluded in the `li` fallback.
- `.msg-form__contenteditable` — the composer; its presence means the page is ready even when the thread is empty.

The template opens either the direct compose URL or the profile → `Message` button path, polls for the list/composer (~10s), then prints `THREAD:{...}`. `dispatch.check_existing_thread()` parses that line into True / False / None (inconclusive).

### Template-authoring rules (verified 2026-08-16):

- browser-use scripts are **exec'd as Python**: dict literals need quoted keys (`{"found": False}`), or the script dies with `NameError` before anything is sent.
- Backslash escapes inside embedded JS are consumed twice (host Python parse + exec parse). Build separators/character classes without them: `String.fromCharCode(10)`, `[0-9]` instead of `\d`.
