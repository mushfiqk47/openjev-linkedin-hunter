# 🎯 Autonomous LinkedIn Job Hunter & Feed Scanner

An autonomous browser agent that pairs **Playwright Chrome DevTools Protocol (CDP)** with local **SemIf logprob AI evaluation (`qwen3.5-4b`)** to discover, screen, and save high-fit UI/UX and Product Design opportunities against candidate CV ([`Mushfiq_Kabir_CV.json`](../Mushfiq_Kabir_CV.json)).

Matching jobs and feed opportunities are saved to `output/jobs_report.md`, `output/jobs.csv`, and `output/matched_jobs.json`.

---

## 🌟 Capabilities

- **Dual Hunting Modes:**
  1. **Job Search with Automated Feed Fallback:** Evaluates top search pages across rotated queries (`UI/UX Designer`, `Product Designer`, `Figma Designer`). If search pages yield fewer than the target quota (e.g. 10 matches), it automatically transitions to your LinkedIn News Feed (`/feed/`) and scrolls continuously until the goal is satisfied.
  2. **Direct Feed Scan (`--feed-only`):** Navigates straight to `https://www.linkedin.com/feed/`, dynamically expands `… more` post descriptions, extracts hiring leads, and scores them against the CV with SemIf.
- **Dynamic Multi-Target Scroller:**
  Specifically targets `<main id="workspace">` / `.scaffold-layout__main` with `PageDown` key integration to trigger LinkedIn's dynamic virtual loading on every scroll.
- **Sub-300ms Logprob Scoring:**
  Evaluates fit probabilities directly from native token logprobs in LM Studio. Zero prompt hallucinations, zero JSON parsing failures, and zero timeouts. BM25 prescreen filters obvious non-fits first; scores are calibrated (cap 94) with `role/tools/level/domain` breakdowns, real JD keywords, gaps, and cover hooks.
- **Persistent Anti-Duplicate Memory:**
  Maintains ID + signature (`{title} @@ {company}`) + JD-body hashes in `seen_jobs.json` to skip previously evaluated cards in 0.001s — including identical JDs reposted under different posters (merged as aliases).
- **Easy Apply + Extract-First Scraping:**
  Optional Easy Apply filter with recent-first sorting; card metadata is snapshotted in one JS pass (no detached-element failures) with jittered human pacing (2.0–4.5s) and daily evaluation caps.
- **One Hunting Core:**
  `hunt_core.run_hunt()` is the single seam behind CLI (`hunter.py`) and dashboard (`web.py`); inject fakes to test without LM Studio or Playwright.
- **Recruiter Profile Inspection:**
  Automatically identifies post authors and hiring leads (`/in/<username>`) and company pages (`/company/<name>`).

---

## 🚀 How to Run

### Method 1: Connecting to Active Brave / Chrome (Recommended)
Launch your browser with remote debugging on port 9222:
```bash
# Brave:
brave-browser --remote-debugging-port=9222 &

# Google Chrome:
google-chrome --remote-debugging-port=9222 &
```

Run the hunter:
```bash
# Run Search with automatic Feed fallback until 10 matches are found:
./.venv/bin/python -m linkedin_hunter.hunter -q "UI/UX Designer" -n 10

# Scan LinkedIn Feed directly for hiring opportunities:
./.venv/bin/python -m linkedin_hunter.hunter --feed-only -n 10
```

### Method 2: Via the Analogue Web Dashboard
Launch the dashboard:
```bash
./.venv/bin/python -m linkedin_hunter.web
```
Open **`http://127.0.0.1:8085`** to launch the agent with one click, watch live activity logs, and view formatted reports.

---

## ⚙️ CLI Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--query` | `-q` | `"UI/UX Designer"` | Search keyword (e.g., `"Product Designer"`, `"Figma Designer"`) |
| `--min-matches` | `-n`, `-m` | `10` | Target qualifying matches to discover before stopping |
| `--location` | `-l` | `""` | Location filter (empty = candidate network / flexible) |
| `--recency` | `-r` | `"week"` | Posting recency: `24h` (past day), `week` (past week), or `any` |
| `--work-type` | `-w` | `"all"` | Work mode: `all`, `remote`, `on_site`, or `hybrid` |
| `--min-score` | `-s` | `70` | Minimum match percentage (0–100) required to save |
| `--max-pages` | | `2` | Max search pages per query before rotating or falling back |
| `--limit` | `--max-eval` | `120` | Safety ceiling of total raw jobs to evaluate across all queries |
| `--max-feed-scrolls`| | `80` | Safety ceiling of scrolls on the LinkedIn feed |
| `--feed-only` | | `False` | Scan LinkedIn News Feed directly without searching job posts first |
| `--easy-apply` | | `False` | Only Easy Apply jobs (`f_AL=true`, recent-first) |
| `--criteria` | | `None` | Custom SemIf criteria lines (overrides defaults) |
| `--daily-cap` | | `80` | Max LLM evaluations per run (safety cap) |
| `--rotate-queries` | | `True` | Auto-rotate related queries if under target |
| `--view-profiles` | | `True` | Visit recruiter and company profiles to gather details |
| `--save-on-linkedin` | | `False` | Also click "Save" bookmark button on LinkedIn |
| `--headless` | | `False` | Run browser invisibly in the background |

---

## 📄 Output Files

- `output/jobs_report.md`: `Top 3 Apply Now` + summary table (priority/type/deadline) + detailed breakdowns (factors, JD keywords, gaps, cover openers) + separate Network Leads section.
- `output/jobs.csv`: Spreadsheet export (scores, priorities, keywords, gaps, hooks, links).
- `output/matched_jobs.json`: Full structured JSON records (includes `raw_score`, `fit_breakdown`, `jd_hash`, `aliases`).
- `seen_jobs.json`: Deduplication cache (IDs, signatures, JD hashes, skip reasons, searched queries). Tracked intentionally for continuity; secrets never live here.
