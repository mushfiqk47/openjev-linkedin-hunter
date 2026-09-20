# Connection Harvesting Strategies

This document details the multi-strategy approaches for discovering and collecting unsent 1st-degree LinkedIn connections.

All strategies deduplicate against `data/Complete.md` by **profile URL slug first, normalized name second** (`outreach/ledger.py` + `outreach/names.py` are the single source of truth), and each search card also captures the contact's **headline** (stored in `data/contacts.json`, usable in the message template as `{headline}`).

---

## Strategy A: Standard Connections Page (`/mynetwork/invite-connect/connections/`)

- **Target URL**: `https://www.linkedin.com/mynetwork/invite-connect/connections/`
- **Mechanism**: Scrolls the page 4× to lazy-load more cards (added 2026-09-21), then reads anchor tags with `aria-label^="Send a message to "` and grabs the direct compose `href`.
- **Limitation**: As observed on 2026-08-15 (still true 2026-08-16), LinkedIn's desktop web client caps the initial DOM render to ~9 connections without scroll triggers; the added scroll pass nudges more into the DOM, but the People Search fallback remains the reliable bulk source.
- **Best For**: Quick top-up of the most recent connections — `python agent.py harvest` tries this first, then automatically falls back to Strategy B.
- **Bound**: `SEARCH_MAX_PAGES` (default 50) caps the combined sweep.

---

## Strategy B: 1st-Degree People Search (`/search/results/people/?network=["F"]`)

- **Target URL**: `https://www.linkedin.com/search/results/people/?network=["F"]&page=<PAGE>`
- **Mechanism**:
  - Filter `network=["F"]` restricts search exclusively to 1st-degree connections.
  - Returns structured cards across multiple pages (`page=1`, `page=2`, `page=3`, ... up to 100 pages).
  - Each card yields `{name, headline, profile_url}`; the sweep polls for results to render and force-scrolls before scraping.
  - Pagination is seamless: `python agent.py harvest` sweeps up to `SEARCH_MAX_PAGES` pages (default 50) until `TOP_N` unsent contacts are found; `python agent.py harvest --search-only` uses `START_PAGE`/`MAX_PAGES` (default 1/10).
  - Empty pages are tolerated (3 consecutive empty pages stop the sweep early).
- **Best For**: Continuous, uninterrupted batches (10 to 500+ connections) that bypass the connections-page scroll freeze.

---

## Strategy C: Direct Profile Message Overlay Traversal

- **Target URL**: `https://www.linkedin.com/in/<profile-slug>/`
- **Mechanism**:
  - Open target profile page.
  - Locate primary action button: "Message" (`<a href="/messaging/compose/?profileUrn=...">Message</a>`).
  - Read composer container state.
- **Best For**: Targeted single-contact outreach or high-priority lead nurturing — this is exactly what `python agent.py send` (`outreach/dispatch.py`) does for every `profile_url` contact.
