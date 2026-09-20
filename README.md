# 🎯 OpenJev · Autonomous LinkedIn Job Hunter & Decision Engine

An end-to-end autonomous agent platform combining **SemIf** (TypeSafe Jev baseline for sub-second deterministic decision-making) with an **Autonomous LinkedIn Browser Agent**, candidate CV alignment, and an **Analogue-inspired Web Dashboard & Agent Launcher**.

---

## 🌟 Overview

This repository houses a unified ecosystem:

1. **SemIf Decision Engine (`backend/`)**: High-performance semantic decision engine ("semantic `if`"). Instead of generating natural language or JSON and parsing text, SemIf extracts decision probabilities **directly from native model logprobs** in a single forward pass (<0.3s) via LM Studio (`qwen3.5-4b`) or native PyTorch. Zero hallucinations, zero parsing errors, zero timeouts.
2. **Autonomous LinkedIn Job Hunter Agent (`linkedin_hunter/`)**: Connects to the user's real browser session via Chrome DevTools Protocol (CDP port 9222), navigates LinkedIn, evaluates opportunities against the candidate's CV ([`Mushfiq_Kabir_CV.json`](Mushfiq_Kabir_CV.json)) with SemIf, auto-rotates search queries, deduplicates cards instantly, and automatically transitions to scrolling the candidate's LinkedIn News Feed until target match quotas are satisfied.
3. **Interactive CLI Assistant (`agent/main.py`, `assistant.sh`)**: Clean terminal interface to trigger hunting, inspect reports, login to LinkedIn, and launch the dashboard.
4. **Analogue Web Dashboard & Agent Launcher (`linkedin_hunter/web.py`)**: Monochromatic UI (pure black `#000000`, tight negative tracking, 18px radius cards, 9999px pills) with an interactive agent launcher, live streaming terminal console with graceful stop capability, and a full Markdown report viewer.

---

## 📐 Architecture & Key Components

```
jev-api/
├── agent/                         # Autonomous Assistant & CLI
│   └── main.py                    # Unified interactive CLI entrypoint
├── backend/                       # SemIf (OpenJev) Decision Engine
│   ├── src/semif_phase1/
│   │   ├── remote.py              # Logprob extractor for LM Studio / vLLM / Ollama
│   │   ├── direct.py              # Native PyTorch CUDA inference engine
│   │   ├── jev_server.py          # TypeSafe Jev API drop-in server (:8090)
│   │   ├── server.py              # SemIf interactive test UI (:8080)
│   │   └── typesafe_proxy.py      # TypeSafe reverse proxy with client auth
│   └── tests/                     # Test suite for SemIf decision scoring
├── linkedin_hunter/               # Autonomous LinkedIn Browser Agent
│   ├── browser.py                 # Playwright CDP automation & feed scraper (extract-first, jittered pacing)
│   ├── hunt_core.py               # Deep hunting module: single run_hunt() seam for CLI + Web
│   ├── evaluator.py               # Calibrated SemIf evaluator (BM25 prescreen, model-judged axes)
│   ├── judgments.py               # Atomic model judgments (binary / classify / rank / axes)
│   ├── triage.py                  # Apply-triage agent: next action, cover angle, recruiter opener
│   ├── hunter.py                  # Thin CLI adapter over hunt_core (argparse → HuntParams)
│   ├── storage.py                 # JD-hash dedup, enriched reports (Top 3, priorities, hooks)
│   ├── config.py                  # Queries, filters, thresholds, skill vocabulary, timing
│   ├── cv_loader.py               # CV JSON → prompt profile
│   ├── login.py                   # One-time LinkedIn session login helper
│   ├── web.py                     # Analogue Web Dashboard & UI Agent Launcher (:8085)
│   ├── seen_jobs.json             # Persistent deduplication database (IDs, signatures, JD hashes)
│   └── output/
│       ├── jobs_report.md         # Generated markdown report with recruiter links
│       ├── jobs.csv               # CSV export of matched opportunities
│       └── matched_jobs.json      # Structured JSON records
├── Mushfiq_Kabir_CV.json          # Candidate profile & design qualifications
├── assistant.sh                   # Unified executable launcher script
├── HOW_TO_RUN.md                  # SemIf backend guide
└── README.md                      # Project documentation
```

---

## ⚡ Key Capabilities

### 1. Zero-Hallucination Decision Scoring (SemIf)
- **Sub-300ms Forward Pass:** Evaluates fit by calculating native token logits on LM Studio (`qwen3.5-4b`) with `reasoning_effort="none"`.
- **BM25 Prescreen (zero LLM cost):** Disqualified titles and no-design-signal posts filter to `SKIP` before any model call.
- **Calibrated Scores:** Raw logprob percentages are monotonically compressed (cap 94) to counter instruct-model overconfidence; `raw_score` is preserved and `low_margin` flags borderline cases for manual review.
- **Factor Breakdown + Real Gaps:** Each evaluation returns `role/tools/level/domain` fits, JD keywords extracted against a skill vocabulary, matched vs missing skills, employment type, and a cover-letter hook.
- **Model-Judged Axes + Exhaustive Triage:** `role/tools/level/domain` are scored by the model (blended into the fit score) rather than regex; caps are soft by default so every card and feed post is evaluated, each non-match carrying a one-line `skip_reason`.
- **Apply-Triage Agent:** `python -m linkedin_hunter.triage` chains instant judgments over saved matches — employer fit, freshness, cover-letter angle, recruiter opener, and one recommended next action.
- **CV Profile Alignment:** Compares candidate skills, experience level, tools (Figma, Design Systems), and dealbreakers against job descriptions and feed post content.

### 2. Autonomous LinkedIn Hunter
- **CDP Session Attachment:** Connects directly to your running browser (Brave or Chrome) via port 9222. Preserves your active session cookies, bypassing Cloudflare, CAPTCHAs, and 2FA authwalls.
- **Dual Hunting Modes:**
  1. **Search with Dynamic Feed Fallback:** Evaluates top search pages across rotated queries (`UI/UX Designer`, `Product Designer`, `Figma Designer`). When search results yield fewer than the target quota, the agent smoothly transitions to your LinkedIn News Feed and scrolls continuously until the goal is satisfied.
  2. **Direct Feed Scan (`--feed-only`):** Navigates directly to `https://www.linkedin.com/feed/` to discover organic hiring posts from your network.
- **Multi-Target Feed Scroller:** Targets `<main id="workspace">` / `.scaffold-layout__main` with `PageDown` key events, scrolling reliably across modern dynamic LinkedIn layouts.
- **Text Expansion (`… more`):** Automatically clicks collapsed `… more` buttons on feed updates so complete job descriptions, emails, and criteria are exposed to SemIf.
- **Instant Persistent Deduplication:** ID + `{title} @@ {company}` signature + JD-body hash in `seen_jobs.json` avoids re-evaluating previously seen postings (including identical JDs reposted under different posters, merged as aliases).
- **Easy Apply Filter:** Optional `f_AL=true` + recent-first sorting (`--easy-apply` / dashboard checkbox).
- **Extract-First Scraping:** Card metadata is snapshotted via a single JS pass before visiting details — no detached-element failures; role-based waits replace fixed sleeps.
- **Hiring Lead Inspection:** Automatically identifies hiring managers / recruiters (`/in/<username>`) and company profiles (`/company/<name>`).
- **One Hunting Core:** `hunt_core.run_hunt()` is the single seam behind both CLI and Web (query rotation, caps, feed fallback); both entrypoints are thin adapters, and fakes make it testable without LM Studio or Playwright.

### 3. Analogue Web Dashboard (`http://127.0.0.1:8085`)
- **Interactive Agent Controls:** Full form controls for query, recency, work type, target matches, query rotation, profile inspection, feed fallback, Easy Apply, and fit criteria.
- **Direct Agent Triggers:** Dedicated `▶ Search Jobs` and `📰 Scan Feed` buttons.
- **Live Terminal Console:** Real-time auto-scrolling terminal log with color-coded severity tags (`[INFO]`, `[MATCH]`, `[WARNING]`, `[SUCCESS]`).
- **Graceful Stop Button:** Halts browser navigation safely at any point (`■ Stop Agent`).
- **Segmented Report Viewer:**
  - **Cards View:** Interactive cards with match percentages, priority/employment-type/deadline tags, factor breakdowns, JD keywords to mirror in your resume, gaps, and copyable cover openers.
  - **Full Report (.md View):** `Top 3 Apply Now` + summary table + detailed breakdowns + separate Network Leads section.
  - **Raw Markdown View:** Monospaced view with one-click clipboard copy and `.md` / `.csv` export links.

---

## 🛠 Prerequisites

1. **Linux / macOS / Windows (WSL2)**
2. **Python 3.11+**
3. **Local LM Studio:**
   - Base URL: `http://localhost:1234/v1`
   - Model: `qwen3.5-4b` (or any OpenAI-compatible endpoint with logprobs)
4. **Brave Browser or Google Chrome** started with remote debugging:
   ```bash
   # Launch Brave with remote debugging on port 9222:
   brave-browser --remote-debugging-port=9222 &

   # OR Google Chrome:
   google-chrome --remote-debugging-port=9222 &
   ```

---

## 🚀 How to Run

### Method 1: Launch the Analogue Web Dashboard (Recommended)

Start the web dashboard server:
```bash
./linkedin_hunter/.venv/bin/python -m linkedin_hunter.web
```
Open **`http://127.0.0.1:8085`** in your browser:
- Click **▶ Search Jobs** to search listings with automatic News Feed fallback.
- Click **📰 Scan Feed** to scan your LinkedIn News Feed directly for hiring opportunities.
- Monitor live evaluations and SemIf fit scores in the Activity Terminal.

---

### Method 2: Interactive Terminal CLI (`assistant.sh`)

Launch the interactive terminal assistant:
```bash
./assistant.sh
```
Available options:
- `1. 🔍 Hunt LinkedIn Jobs (Search + Feed Fallback)`: Search job postings and seamlessly fall back to feed if under target.
- `2. 📰 Scan LinkedIn Feed Directly (Hiring Posts)`: Scan your LinkedIn News Feed directly for hiring leads.
- `3. 📄 View Matched Jobs Report (.md)`: Print the latest formatted report in the terminal.
- `4. 🔑 Login to LinkedIn (Save Browser Session)`: Save cookies to persistent session profile.
- `5. 🌐 Launch Live Web Dashboard (http://127.0.0.1:8085)`: Start the web UI.
- `0. 🚪 Exit`: Exit assistant.

---

### Method 3: CLI Job Hunter (`hunter.py`)

Run the browser hunter with custom parameters:
```bash
# Search jobs with automatic Feed fallback until 10 matches are found:
./linkedin_hunter/.venv/bin/python -m linkedin_hunter.hunter \
  --query "UI/UX Designer" \
  --min-matches 10 \
  --recency week \
  --work-type all

# Scan LinkedIn Feed directly for hiring leads:
./linkedin_hunter/.venv/bin/python -m linkedin_hunter.hunter \
  --feed-only \
  --min-matches 10
```

#### CLI Options:
| Flag | Short | Default | Description |
|---|---|---|---|
| `--query` | `-q` | `UI/UX Designer` | Primary job search query |
| `--min-matches` | `-n`, `-m` | `10` | Target minimum qualifying matches to find before stopping |
| `--location` | `-l` | `""` | Search location (empty = candidate network / flexible) |
| `--recency` | `-r` | `week` | Posting recency filter (`24h`, `week`, `any`) |
| `--work-type` | `-w` | `all` | Work type filter (`all`, `remote`, `on_site`, `hybrid`) |
| `--min-score` | `-s` | `70` | Minimum match percentage (0–100) required to qualify |
| `--max-pages` | | `2` | Max search pages to evaluate per query before rotating or falling back |
| `--limit` | `--max-eval` | `120` | Safety ceiling of total raw jobs to evaluate across queries |
| `--max-feed-scrolls` | | `80` | Safety ceiling of scrolls on the LinkedIn feed |
| `--feed-only` | | `False` | Scan LinkedIn News Feed directly without searching job posts first |
| `--easy-apply` | | `False` | Only Easy Apply jobs (`f_AL=true`, recent-first) |
| `--criteria` | | `None` | Custom SemIf criteria lines (overrides defaults) |
| `--daily-cap` | | `80` | Soft cap; only enforced with `--enforce-caps` |
| `--enforce-caps` | | `False` | Restore the old early-stop at `--daily-cap`/`--limit` (default is exhaustive triage) |
| `--rotate-queries` | | `True` | Automatically rotate related queries if under target |
| `--view-profiles` | | `True` | Visit recruiter and company profiles to gather details |
| `--save-on-linkedin` | | `False` | Also click "Save" bookmark button on LinkedIn |
| `--headless` | | `False` | Run browser in background headless mode |

---

### Method 4: SemIf Decision Engine & Jev Choice Server

To test or benchmark the underlying SemIf decision engine:

```bash
# Run SemIf Interactive Test UI on port 8080:
cd backend
python3 -m semif_phase1.server --port 8080

# Run TypeSafe Jev Drop-In Choice Server on port 8090:
python3 -m semif_phase1.jev_server --port 8090
```

---

## 📡 Web Dashboard API Endpoints

The dashboard server exposes clean JSON REST endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Analogue web dashboard interface |
| `/api/jobs` | `GET` | List of all matched opportunities and scoring details |
| `/api/stats` | `GET` | Dedup/eval stats (`seen_ids`, `seen_jd_hashes`, `skip_reasons`, `matched`) |
| `/api/agent/status` | `GET` | Active agent status (`running`, `agent`, live log buffer) |
| `/api/agent/launch` | `POST` | Launch LinkedIn Hunter or Feed agent with parameters |
| `/api/agent/stop` | `POST` | Send stop flag to halt running browser agent gracefully |
| `/api/agent/clear_logs` | `POST` | Clear in-memory terminal console buffer |
| `/output/jobs_report.md` | `GET` | Rendered / raw Markdown jobs report |
| `/output/jobs.csv` | `GET` | Downloadable CSV export of matched opportunities |

---

## 📄 Candidate Profile & Alignment Criteria

Candidate qualifications are loaded from [`Mushfiq_Kabir_CV.json`](Mushfiq_Kabir_CV.json):
- **Candidate Label:** UI/UX & Product Designer.
- **Key Competencies:** Figma, Design Systems, Auto-Layout, Component Libraries, User Research, Prototyping.
- **Criteria Definition:**
  ```
  [Required] Role focuses on UI/UX, Product Design, Visual Interface, or Figma design.
  [Required] Hands-on Figma wireframing, prototyping, design systems, or component libraries.
  [Preferred] Experience with SaaS platforms, web apps, or mobile interfaces.
  [Dealbreaker] Does NOT require 8+ years executive leadership or full-stack software coding.
  ```

---

## 🛡 Security & Design Standards

- **Zero Credentials in Code:** Reuses active authenticated sessions via Chrome DevTools Protocol (CDP). Real API keys live only in ignored `.env` files (root + `backend/.env`), never in git.
- **Human-Paced Navigation:** Uses random human jitter (2.0–4.5s) between clicks and scrolls to respect LinkedIn rate limits, with daily evaluation caps.
- **Analogue Minimalist Aesthetic:** Monochromatic palette (`#000000`, `#ffffff`, `#666666`), negative letter tracking, 18px rounded cards, 9999px pills, zero artificial shadows.
