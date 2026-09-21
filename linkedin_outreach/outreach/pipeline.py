from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from outreach.config import (DEFAULT_FILTER_LOW_RELEVANCE, DEFAULT_MIN_RELEVANCE_SCORE,
                              get_bool, get_float, get_int)
from outreach.dispatch import (check_existing_thread, send_with_retries, thread_decision)
from outreach.evaluator import evaluate_contact
from outreach.messaging import build_message
from outreach.progress import refresh_progress
from outreach.registry import ConnectionsRegistry, get_registry
from outreach.restricted import apply_restricted_scan, is_restricted
from outreach.sync import sync_network

@dataclass
class PipelineParams:
    limit: int | None = None
    top: int | None = None
    pause: int | None = None
    dry_run: bool = False
    search_only: bool = False
    start_page: int | None = None
    max_pages: int | None = None
    filter_low_relevance: bool | None = None
    min_relevance: int | None = None

@dataclass
class PipelineResult:
    synced: int = 0
    unsent_found: int = 0
    sent: int = 0
    skipped: int = 0
    restricted: int = 0
    failed: int = 0
    remaining_budget: int = 0
    items: list[dict] = field(default_factory=list)

def run_pipeline(
    params: PipelineParams,
    registry: ConnectionsRegistry | None = None,
    on_event: Callable[[str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> PipelineResult:

    reg = registry or get_registry()
    log = on_event or (lambda msg, lvl="info": print(f"  [{lvl}] {msg}"))
    stop = should_stop or (lambda: False)

    result = PipelineResult()
    initial_restricted = apply_restricted_scan(reg, on_event=log)
    if initial_restricted > 0:
        result.restricted += initial_restricted
        log(f"Pre-flight restricted scan: {initial_restricted} connection(s) marked RESTRICTED.", "info")
    today = date.today().strftime("%Y-%m-%d")
    daily_limit = params.limit if params.limit is not None else get_int("DAILY_LIMIT", 15)
    sent_today = reg.count_sent_today(today)
    remaining_budget = max(0, daily_limit - sent_today)
    result.remaining_budget = remaining_budget

    log(f"Daily status: {sent_today}/{daily_limit} sent today ({remaining_budget} remaining budget).", "info")

    if remaining_budget <= 0 and not params.dry_run:
        log(f"Daily limit reached ({daily_limit} messages). Halting for today to protect account.", "warning")
        refresh_progress()
        return result

    target_top = params.top if params.top is not None else get_int("TOP_N", 25)
    unsent_pool = reg.get_unsent_pool()

    if len(unsent_pool) < min(target_top, remaining_budget):
        log("Checking LinkedIn for new 1st-degree connections...", "info")
        sync_network(
            registry=reg,
            target_new=target_top,
            start_page=params.start_page or 1,
            max_search_pages=params.max_pages or 20,
            search_only=params.search_only,
            on_event=log,
        )
        unsent_pool = reg.get_unsent_pool()

    result.unsent_found = len(unsent_pool)
    log(f"Unsent candidates available: {len(unsent_pool)} (Registry tracking {reg.get_stats()['total_tracked']} total)", "info")

    if not unsent_pool:
        log("All current network connections are up-to-date! No pending unsent leads.", "success")
        refresh_progress()
        return result

    pacing = get_float("PACING", 0.0)
    pacing_jitter = get_float("PACING_JITTER", 0.0)
    max_attempts = max(1, get_int("MAX_ATTEMPTS", 2))
    thread_check = get_int("THREAD_CHECK", 1) != 0
    thread_check_strict = get_bool("THREAD_CHECK_STRICT", False)
    filter_low = (params.filter_low_relevance if params.filter_low_relevance is not None
                  else get_bool("FILTER_LOW_RELEVANCE", DEFAULT_FILTER_LOW_RELEVANCE != 0))
    min_relevance = (params.min_relevance if params.min_relevance is not None
                     else get_int("MIN_RELEVANCE_SCORE", DEFAULT_MIN_RELEVANCE_SCORE))

    to_process = unsent_pool[:remaining_budget]
    log(f"Processing up to {len(to_process)} candidate(s) for outreach...", "info")

    if params.pause and params.pause > 0:
        log(f"Review pause active: waiting {params.pause}s before dispatching...", "info")
        for _ in range(params.pause):
            if stop():
                break
            time.sleep(1)

    for i, contact in enumerate(to_process):
        if stop():
            log("Stop signal received. Halting pipeline.", "warning")
            break

        name = contact.get("name", "Connection")
        log(f"Evaluating candidate [{i + 1}/{len(to_process)}]: {name}", "info")

        restricted, rest_reason = is_restricted(contact)
        if restricted:
            log(f"  [⛔ RESTRICTED] {name}: {rest_reason}. Will not send messages.", "warning")
            if not params.dry_run:
                reg.record_restricted(contact, reason=rest_reason)
            result.restricted += 1
            result.items.append({"name": name, "status": "RESTRICTED", "detail": rest_reason})
            continue

        eval_res = evaluate_contact(contact)
        archetype = eval_res.get("archetype", "general")
        relevance = int(eval_res.get("relevance", 60))
        reason = eval_res.get("reason", "")
        contact["archetype"] = archetype
        contact["relevance"] = relevance

        log(f"  [SemIf] Archetype: {archetype} | Relevance: {relevance}% ({eval_res.get('backend')})", "info")

        if filter_low and relevance < min_relevance:
            skip_desc = f"low relevance ({relevance}% < {min_relevance}%, {archetype})"
            log(f"  [Skip] {name}: {skip_desc}", "info")
            if not params.dry_run:
                reg.record_skipped(contact, reason=skip_desc, archetype=archetype, relevance=relevance)
            result.skipped += 1
            result.items.append({"name": name, "status": "SKIPPED", "detail": skip_desc})
            continue

        if thread_check and not params.dry_run:
            has_messages, check_detail = check_existing_thread(contact)
            skipped, skip_reason = thread_decision(has_messages, check_detail, strict=thread_check_strict)
            if skipped:
                log(f"  [Skip] {name}: conversation already exists on LinkedIn.", "info")
                reg.record_skipped(contact, reason="live thread already had messages", archetype=archetype, relevance=relevance)
                result.skipped += 1
                result.items.append({"name": name, "status": "SKIPPED", "detail": skip_reason})
                continue

        msg_text = build_message(name, contact)

        if params.dry_run:
            preview = msg_text.replace("\n", " ")[:90]
            log(f"  [DRY-RUN] Would send [{archetype}] to {name}: '{preview}...'", "match")
            result.sent += 1
            result.items.append({"name": name, "status": "SIMULATED", "detail": f"dry-run: {preview}"})
        else:
            log(f"  [Dispatch] Sending {archetype} outreach to {name}...", "info")
            try:
                status, detail = send_with_retries(contact, max_attempts)
            except Exception as e:
                status, detail = "FAILED", f"dispatch exception: {e}"

            if status == "SENT":
                reg.record_sent(contact, archetype=archetype, relevance=relevance, detail=detail)
                log(f"  [✓ SENT] Delivered to {name}! Recorded in registry.", "success")
                result.sent += 1
            elif status == "SKIPPED":
                reg.record_skipped(contact, reason=detail, archetype=archetype, relevance=relevance)
                result.skipped += 1
            else:
                reg.record_failed(contact, error=detail)
                log(f"  [✗ {status}] Could not deliver to {name}: {detail}", "warning")
                result.failed += 1

            result.items.append({"name": name, "status": status, "detail": detail})

            if i < len(to_process) - 1 and pacing > 0:
                delay = random.uniform(pacing, pacing * max(1.0, pacing_jitter))
                log(f"  Pacing delay: {round(delay, 1)}s before next candidate...", "info")
                time.sleep(delay)

    refresh_progress()
    log(f"Pipeline execution finished. Sent: {result.sent} | Skipped: {result.skipped} | Restricted: {result.restricted} | Failed: {result.failed}", "success")
    return result
