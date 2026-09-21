from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from outreach.pipeline import PipelineParams, run_pipeline
from outreach.registry import get_registry

@dataclass
class OutreachParams:

    top: int | None = None
    limit: int | None = None
    pause: int | None = None
    dry_run: bool = False
    search_only: bool = False
    start_page: int | None = None
    max_pages: int | None = None

@dataclass
class OutreachResult:

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
