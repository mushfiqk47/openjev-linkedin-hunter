"""LinkedIn Outreach Agent engine.

Deep modules behind one interface: `python agent.py <command>` (see agent.py).
Layout:
  config    — every path and setting (single source of truth)
  browser   — browser-use execution seam (mockable in tests)
  names     — name/URL normalization and dedup keys
  ledger    — Complete.md behavior: parse, query, append
  messaging — the outreach message (rendered from data/message.py)
  progress  — total/messaged/remaining funnel tracking
  harvest   — contact harvesting (connections page + paginated search)
  dispatch  — message sending, delivery verification, retry
  report    — status and preflight diagnostics
"""

__version__ = "2.0.0"
