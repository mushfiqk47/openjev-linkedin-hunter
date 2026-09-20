import datetime
from pathlib import Path

from outreach.browser import parse_marker_line, run_bu_script
from outreach.config import (DEFAULT_CONNECTIONS_URL, PROGRESS_FILE, TOTAL_FILE,
                             get_str)
from outreach.ledger import count_sent_today, parse_ledger, sent_keys

CONNECTIONS_URL = DEFAULT_CONNECTIONS_URL

COUNT_JS = """
import json, time

js("window.location.href = '__CONNECTIONS_URL__'")

for i in range(30):
    ready = js('''(() => {
        const main = document.querySelector('main');
        return !!(main && main.innerText.trim().length > 0);
    })()''')
    if ready:
        break
    time.sleep(0.05)

count = js('''(() => {
    const NL = String.fromCharCode(10);
    const CR = String.fromCharCode(13);
    const lineSep = new RegExp('[' + NL + CR + ']+');
    function fromLines(text) {
        const parts = String(text).split(lineSep);
        for (let line of parts) {
            let t = line.trim();
            let lower = t.toLowerCase();
            if (lower.indexOf('mutual') !== -1) continue;
            let word = 'connections';
            if (lower.endsWith(word)) {
                // candidate: "453 connections" / "1,234 Connections"
            } else if (lower.endsWith('connection')) {
                word = 'connection';
            } else {
                continue;
            }
            let numPart = t.slice(0, t.length - word.length).trim();
            if (numPart && /^[0-9][0-9,.]*$/.test(numPart)) {
                return numPart;
            }
        }
        return null;
    }
    let value = null;
    const h1 = document.querySelector('h1');
    if (h1) value = fromLines(h1.innerText);
    if (!value) value = fromLines(document.title);
    if (!value) {
        const main = document.querySelector('main');
        if (main) value = fromLines(main.innerText.slice(0, 3000));
    }
    return { count: value };
})()''')

print(\"COUNT:\" + json.dumps(count))
"""

def fetch_total_connections(timeout=None):

    script = COUNT_JS.replace("__CONNECTIONS_URL__", get_str("LINKEDIN_CONNECTIONS_URL", CONNECTIONS_URL))
    out, err = run_bu_script(script, timeout=timeout)
    payload = parse_marker_line(out, "COUNT:")
    if payload and payload.get("count") is not None:
        try:
            return int(str(payload["count"]).replace(",", "").replace(".", "").strip())
        except Exception:
            return None
    if err and err.strip():
        print(f"[WARN] browser-use: {err.strip()[:200]}")
    return None

def read_saved_total():

    try:
        value = int(TOTAL_FILE.read_text(encoding="utf-8").strip())
        return value if value >= 0 else None
    except Exception:
        return None

def refresh_progress(total_connections=None):

    entries = parse_ledger()
    sent_names, _ = sent_keys(entries)
    if total_connections is None:
        total_connections = read_saved_total()
    if not isinstance(total_connections, int) or total_connections < 0:
        total_connections = None
    messaged = len(sent_names)
    remaining = (total_connections - messaged) if total_connections is not None else None
    sent_today = count_sent_today(entries)

    lines = [
        f"total_connections: {total_connections if total_connections is not None else 'unknown'}",
        f"messaged_unique: {messaged}",
        f"remaining: {remaining if remaining is not None else 'unknown'}",
        f"sent_today: {sent_today}",
        f"daily_limit: {get_str('DAILY_LIMIT', '15')}",
        f"updated_at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    PROGRESS_TXT = Path(PROGRESS_FILE)
    PROGRESS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if total_connections is not None:
        Path(TOTAL_FILE).write_text(str(total_connections) + "\n", encoding="utf-8")
    return {
        "total_connections": total_connections,
        "messaged_unique": messaged,
        "remaining": remaining,
        "sent_today": sent_today,
    }

def run(timeout=None):

    print("Fetching total connection count from LinkedIn...")
    total = fetch_total_connections(timeout=timeout)
    if total is None:
        print("[WARN] could not read the connection count (Chrome/CDP off, page changed,")
        print("       or not logged in). Keeping any previously saved total.")
    data = refresh_progress(total)
    total_str = data["total_connections"] if data["total_connections"] is not None else "unknown"
    remaining_str = data["remaining"] if data["remaining"] is not None else "unknown"
    print("--------------------------------------------------")
    print(f"Total Connections : {total_str}")
    print(f"Already Messaged  : {data['messaged_unique']}")
    print(f"Remaining         : {remaining_str}")
    print(f"Sent Today        : {data['sent_today']} (limit {get_str('DAILY_LIMIT', '15')})")
    print(f"Saved to          : {PROGRESS_FILE}")
    print("--------------------------------------------------")
    return data
