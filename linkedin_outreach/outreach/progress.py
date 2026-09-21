import datetime
from pathlib import Path

from outreach.config import PROGRESS_FILE, TOTAL_FILE, get_str
from outreach.ledger import count_sent_today, parse_ledger, sent_keys

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
