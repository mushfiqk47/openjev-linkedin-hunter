# LinkedIn Outreach: Autonomous 1st-Degree Network Outreach Agent

An autonomous direct messaging pipeline that synchronizes newly added LinkedIn 1st-degree connections, scores their professional relevance, checks message threads for existing history, and delivers personalized outreach.

## Features

- **Delta-Sync Network Registry**:
  - Maintains `connections_registry.json` tracking all known connections with fast $O(1)$ duplicate lookups.
  - Automatically identifies new connections without visiting every profile or opening threads.
- **Thread Verification & Safety**:
  - Non-destructive DOM inspection verifies whether a candidate was already contacted.
  - Strictly prevents duplicate messaging.
- **Append-Only Ledger**:
  - Permanently tracks every contacted member in `data/Complete.md`.
- **Dynamic Personalization**:
  - Formats outreach messages using templates in `data/message.py`.
  - Injects candidate first names, portfolio links, and customized conversation openers.
- **Zero-Delay High-Throughput Mode**:
  - Configurable anti-spam pacing (`PACING=0`, `PACING_JITTER=0`) for instant execution when desired.

## Running the Agent

```bash
# Run simulation (dry-run preview):
python3 -m linkedin_outreach.agent --dry-run

# Run live outreach with daily limit override:
python3 -m linkedin_outreach.agent --limit 15

# Run direct 1st-degree People Search sweep:
python3 -m linkedin_outreach.agent --search-only --start-page 1 --max-pages 20
```

## Running Tests

```bash
python3 -m unittest discover tests
```
