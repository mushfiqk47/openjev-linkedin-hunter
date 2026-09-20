"""Unified Outreach Core: autonomous execution seam for LinkedIn direct-message outreach.

Connects the CLI and assistant to the pure self-updating pipeline:
  - Persistent connection registry with $O(1)$ state lookups
  - Automatic network delta synchronization for newly added/removed connections
  - Zero redundant browser double-checks for already messaged/skipped connections
  - SemIf backend decision engine integration for persona classification and relevance scoring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from outreach.pipeline import PipelineParams, PipelineResult, run_pipeline
from outreach.registry import ConnectionsRegistry, get_registry


@dataclass
class OutreachParams:
    """Configuration for autonomous outreach execution."""

    top: int | None = None          # Target batch of unsent leads to discover (default: 25)
    limit: int | None = None        # Daily send limit override (default: 15)
    pause: int | None = None        # Optional review pause (in seconds)
    dry_run: bool = False           # Simulate actions without sending messages
    search_only: bool = False       # Skip connections page, search directly
    start_page: int | None = None   # First search page
    max_pages: int | None = None    # Maximum search pages to sweep


@dataclass
class OutreachResult:
    """Outcome of an outreach run."""

    harvested: int = 0
    pending: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    remaining_budget: int = 0
    items: list[dict] = field(default_factory=list)


@dataclass
class OutreachHooks:
    on_event: Callable[[str, str], None] = lambda msg, level="info": None
    should_stop: Callable[[], bool] = lambda: False


def run_outreach(params: OutreachParams, hooks: OutreachHooks = OutreachHooks()) -> OutreachResult:
    """Run the pure self-updating outreach pipeline."""
    pipe_params = PipelineParams(
        top=params.top,
        limit=params.limit,
        pause=params.pause,
        dry_run=params.dry_run,
        search_only=params.search_only,
        start_page=params.start_page,
        max_pages=params.max_pages,
    )

    reg = get_registry()
    pipe_result = run_pipeline(
        params=pipe_params,
        registry=reg,
        on_event=hooks.on_event,
        should_stop=hooks.should_stop,
    )

    return OutreachResult(
        harvested=pipe_result.synced,
        pending=pipe_result.unsent_found,
        sent=pipe_result.sent,
        skipped=pipe_result.skipped,
        failed=pipe_result.failed,
        remaining_budget=pipe_result.remaining_budget,
        items=pipe_result.items,
    )
