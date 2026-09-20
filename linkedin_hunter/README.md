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
  Evaluates fit probabilities directly from native token logprobs in LM Studio. Zero prompt hallucinations, zero JSON parsing failures, and zero timeouts.
- **Persistent Anti-Duplicate Memory:**
  Maintains signature hashing (`{title} @@ {company}`) in `seen_jobs.json` to skip previously evaluated cards in 0.001s.
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
| `--view-profiles` | | `True` | Visit recruiter and company profiles to gather details |
| `--headless` | | `False` | Run browser invisibly in the background |

---

## 📄 Output Files

- `output/jobs_report.md`: Markdown summary table with match percentages, AI fit analysis, and direct application / profile links.
- `output/jobs.csv`: Spreadsheet export formatted for spreadsheet trackers.
- `output/matched_jobs.json`: Full structured JSON data records.
- `seen_jobs.json`: Deduplication cache containing evaluated IDs and signatures.
