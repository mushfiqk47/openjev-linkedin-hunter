from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass

from .config import LLM_BASE_URL, LLM_MODEL
from .cv_loader import get_candidate_profile_prompt
from .judgments import Judge

NEXT_ACTIONS = {
    "apply_now": "Apply now — strong fit and hireable now.",
    "outreach_recruiter": "Message the hiring lead first — good fit, relationship helps.",
    "save_for_later": "Save for later — plausible but not urgent.",
    "skip": "Skip — not worth the application effort.",
}

COVER_ANGLES = {
    "design_systems": "Design systems, component libraries and design tokens at scale",
    "figma_craft": "Hands-on Figma craft: wireframes, prototyping and auto-layout",
    "user_research": "User research and usability testing to de-risk product decisions",
    "saas_product": "Shipping product UI for SaaS and web apps iteratively",
    "mobile": "Mobile app interface design and responsive patterns",
    "visual_brand": "Visual design, brand polish and interface aesthetics",
}

FRESHNESS_LABELS = {
    "fresh": "Posted within the last 24-48 hours.",
    "this_week": "Posted within the past week.",
    "older": "Older than a week.",
    "unknown": "No posting date visible.",
}

def _first_name(author: str) -> str:
    parts = [p for p in re.split(r"\s+", (author or "").strip()) if p]
    return parts[0] if parts else "there"

@dataclass
class Triaged:

    next_action: str
    action_confidence: float
    employer_fit: int
    freshness: str
    cover_angles: list[str]
    recruiter_message: str
    reason: str
    model_calls: int

    def to_dict(self) -> dict:
        return {
            "next_action": self.next_action,
            "action_confidence": round(self.action_confidence, 3),
            "employer_fit": self.employer_fit,
            "freshness": self.freshness,
            "cover_angles": self.cover_angles,
            "recruiter_message": self.recruiter_message,
            "triage_reason": self.reason,
            "triage_calls": self.model_calls,
        }

class ApplyTriage:

    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL,
                 client=None, meta: dict | None = None):
        self.model = model
        self.base_url = base_url
        self.candidate_profile = get_candidate_profile_prompt()
        self.judge = Judge(base_url=base_url, model=model, client=client, meta=meta)

    def _state(self, job: dict) -> str:
        return f"""=== CANDIDATE PROFILE ===
{self.candidate_profile}

=== JOB POSTING ===
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Type: {job.get('employment_type', '')}
Hiring lead: {job.get('recruiter_name', '')}
Description:
{(job.get('description') or '')[:2500]}
"""

    def employer_fit(self, job: dict, state: str) -> tuple[int, float]:
        probability, seconds = self.judge.binary(
            "Is this employer a plausible direct-hire fit for a remote UI/UX designer "
            "(not a staffing spam farm, unrelated domain, or unpaid listing)?",
            state,
            "Yes, a plausible direct-hire employer.",
            "No, unlikely or low-quality employer.",
            row_id=f"triage-employer-{abs(hash(job.get('job_id', '')))}",
        )
        return int(round(probability * 100)), seconds

    def freshness(self, job: dict, state: str) -> tuple[str, float]:
        hint = job.get("posted_hint") or ""
        label, _probability, seconds = self.judge.classify(
            "How recent is this posting?",
            f"{state}\n\n=== POSTED HINT ===\n{hint or 'none'}",
            FRESHNESS_LABELS,
            row_id=f"triage-fresh-{abs(hash(job.get('job_id', '')))}",
        )
        return label, seconds

    def cover_angles(self, job: dict, state: str) -> tuple[list[str], str, float]:
        ranked, seconds = self.judge.rank(
            "Which of the candidate's strengths should lead the cover letter for this posting?",
            state,
            list(COVER_ANGLES.items()),
            row_id=f"triage-angles-{abs(hash(job.get('job_id', '')))}",
        )
        angles = [angle_id for angle_id, _probability in ranked if _probability >= 0.05][:3]
        texts = [COVER_ANGLES[angle_id] for angle_id in angles] or [COVER_ANGLES["figma_craft"]]
        return angles, texts[0], seconds

    def next_action(self, job: dict, state: str, employer_fit: int,
                    freshness: str, has_recruiter: bool) -> tuple[str, float, float]:
        context = (
            f"{state}\n\n=== SIGNALS ===\n"
            f"employer_fit={employer_fit}\nfreshness={freshness}\nhas_hiring_lead={has_recruiter}\n"
        )
        action, probability, seconds = self.judge.classify(
            "What is the single best next action for this opportunity?",
            context,
            NEXT_ACTIONS,
            row_id=f"triage-action-{abs(hash(job.get('job_id', '')))}",
        )
        return action, probability, seconds

    def recruiter_message(self, job: dict, angle_text: str) -> str:
        name = _first_name(job.get("recruiter_name") or job.get("company", ""))
        title = (job.get("title") or "the role").split("(")[0].strip()
        company = job.get("company") or "your team"
        return (
            f"Hi {name}, I saw your {title} opening at {company} — my work on "
            f"{angle_text.lower()} maps closely to the brief. Would you be open to a quick chat?"
        )

    def triage(self, job: dict) -> dict:

        state = self._state(job)
        calls = 0
        employer_fit, seconds_e = self.employer_fit(job, state)
        freshness, seconds_f = self.freshness(job, state)
        angles, angle_text, seconds_a = self.cover_angles(job, state)
        has_recruiter = bool(job.get("recruiter_name") or job.get("recruiter_url"))
        action, confidence, seconds_n = self.next_action(job, state, employer_fit, freshness, has_recruiter)
        calls = self.judge.calls

        reason_bits = [f"employer fit {employer_fit}%", freshness.rstrip(".").lower()]
        if angles:
            reason_bits.append(f"lead angle: {angles[0]}")
        result = Triaged(
            next_action=action,
            action_confidence=confidence,
            employer_fit=employer_fit,
            freshness=freshness,
            cover_angles=angles,
            recruiter_message=self.recruiter_message(job, angle_text),
            reason=", ".join(reason_bits),
            model_calls=calls,
        )
        return result.to_dict()

def triage_job(job: dict, judge_client=None, meta: dict | None = None) -> dict:

    agent = ApplyTriage(client=judge_client, meta=meta)
    return agent.triage(job)

def main() -> None:
    from .storage import JobStore

    parser = argparse.ArgumentParser(description="Run apply-triage over saved matches.")
    parser.add_argument("--dry-run", action="store_true", help="Print the triage result without writing back.")
    parser.add_argument("--job-id", default=None, help="Triage a single job by id.")
    args = parser.parse_args()

    store = JobStore()
    jobs = store.load_matched_jobs()
    if not jobs:
        print(f"[!] No matched jobs at {store.json_file}. Run the hunter first.")
        return

    agent = ApplyTriage()
    triaged = []
    for job in jobs:
        if args.job_id and str(job.get("job_id")) != str(args.job_id):
            triaged.append(job)
            continue
        result = agent.triage(job)
        enriched = {**job, "triage": result}
        triaged.append(enriched)
        print(f"[+] {job.get('title', '')} @ {job.get('company', '')}: "
              f"{result['next_action']} (employer fit {result['employer_fit']}%)")

    if args.dry_run:
        print(json.dumps([j.get("triage") for j in triaged if j.get("triage")], indent=2))
        return

    store.rewrite(triaged)
    print(f"[✓] Triage written to {store.json_file}")

if __name__ == "__main__":
    main()
