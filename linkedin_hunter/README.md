# LinkedIn Hunter: Autonomous Job Hunter Agent

An autonomous AI agent designed for automated LinkedIn job discovery, newsfeed hiring post extraction, multi-axis CV qualification evaluation, and real-time triage.

## Features

- **Multi-Axis SemIf Scoring**: Evaluates each opportunity along four weighted axes:
  - `role_fit` (35%): Direct alignment with UI/UX & Product Design focus.
  - `tools_fit` (25%): Hands-on expertise with Figma, Design Systems, and prototyping.
  - `level_fit` (20%): Mid-to-senior qualification without unreasonable executive mandates.
  - `domain_fit` (20%): Relevance to web applications, SaaS, and mobile products.
- **Extract-First Scraping**: Snapshots listings and metadata in a single fast CDP execution without detached-element errors.
- **Dynamic News Feed Fallback**: If standard job search queries return fewer matches than requested, the agent automatically transitions to scanning the LinkedIn News Feed for real-time hiring posts.
- **Zero Human Delay Option**: Configurable pacing to run at maximum machine speed (`ENABLE_HUMAN_DELAYS=0`).
- **Comprehensive Output Artifacts**: Automatically generates clean markdown reports (`output/jobs_report.md`), structured JSON data (`output/matched_jobs.json`), and spreadsheet exports (`output/jobs.csv`).

## Running the Agent

### Method 1: Autonomous Agent CLI
```bash
# Run with default settings from .env:
python3 -m linkedin_hunter.agent

# Run with custom parameters:
python3 -m linkedin_hunter.agent --query "Product Designer" --min-matches 15 --work-type remote
```

### Method 2: Core Hunter Script
```bash
python3 -m linkedin_hunter.hunter -q "UI/UX Designer" -n 10 -r week -w all
```

## Running Tests

```bash
pytest tests
```
