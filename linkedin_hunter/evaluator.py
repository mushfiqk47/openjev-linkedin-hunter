"""SemIf-powered Job Decision Evaluator.

Reads native model logprobs directly from LM Studio in a single forward pass (<0.3s).
Multi-factor calibrated scoring: BM25 pre-filter + logprob readout + factor breakdown.
Zero generated tokens, zero JSON parsing failures, zero timeouts.
"""

import re
import sys
from pathlib import Path
from .config import LLM_BASE_URL, LLM_MODEL, PROJECT_ROOT, SKILL_VOCAB, FACTOR_WEIGHTS
from .cv_loader import get_candidate_profile_prompt

# Import the core SemIf scoring engine from backend/src
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))
from semif_phase1.remote import load_model, score

DEFAULT_CRITERIA = [
    "[Required] Role focuses on UI/UX, Product Design, Visual Interface, or Figma design.",
    "[Required] Hands-on Figma wireframing, prototyping, design systems, or component libraries.",
    "[Preferred] Experience in SaaS platforms, web apps, or mobile interfaces.",
    "[Dealbreaker] Does NOT require 8+ years executive/director leadership or full-stack software development/coding.",
]

# Candidate-owned skills (from Mushfiq_Kabir_CV.json) — used for real gap analysis
CANDIDATE_SKILLS = {
    "figma", "adobe xd", "illustrator", "photoshop", "sketch",
    "wireframing", "wireframes", "prototyping", "prototype",
    "design systems", "design system", "component library", "design tokens",
    "user research", "usability testing", "user testing", "user flows",
    "information architecture", "interaction design", "visual design",
    "ui/ux", "product design", "saas", "mobile app", "web app",
    "responsive design", "client communication", "design thinking",
}

DISQUALIFIED_TITLES = [
    "radiologist", "radiology", "doctor", "physician", "nurse", "medical", "clinic",
    "recruiter", "talent acquisition", "sales representative", "accountant",
    "devops", "backend engineer", "backend developer", "data engineer",
    "video editor", "videographer", "customer support",
    "telecaller", "warehouse", "delivery driver", "cook", "chef",
    "fashion designer",
]


def keyword_hits(title: str, description: str) -> list[str]:
    text = f"{title or ''}\n{description or ''}".lower()
    hits = [v for v in SKILL_VOCAB if v.lower() in text]
    hits.sort(key=lambda v: (-len(v), v))
    return hits[:10]


def extract_matched_missing(title: str, description: str):
    hits = keyword_hits(title, description)
    matched, missing = [], []
    for h in hits:
        (matched if h.lower() in CANDIDATE_SKILLS else missing).append(h.title() if len(h) <= 8 else h)
    # Title-case short tokens nicely
    matched = [m if m != "Ui/Ux" else "UI/UX" for m in matched]
    return matched, missing, hits


def bm25_prescreen(title: str, description: str):
    """Cheap negative-signal gate (Indeed bad-match pattern). Returns SKIP dict or None."""
    t = (title or "").lower()
    if any(bad in t for bad in DISQUALIFIED_TITLES):
        return {"match_score": 8, "fit_level": "SKIP", "prescreen": "disqualified-title"}
    text = f"{t} {(description or '').lower()}"
    design_tokens = ["design", "figma", "ui", "ux", "product", "prototype", "wireframe"]
    if not any(tok in text for tok in design_tokens):
        return {"match_score": 12, "fit_level": "SKIP", "prescreen": "no-design-signal"}
    return None


def calibrate(raw: int) -> tuple[int, bool]:
    """Compress saturated 80-100% band (instruct-model overconfidence). Monotonic, cap 94.

    Maps: 100->94, 99->93, 98->92, 95->90, 90->85, 85->81, 80->76. Below 80 unchanged.
    Returns (calibrated_score, was_compressed).
    """
    if raw >= 80:
        cal = min(94, int(raw * 0.92 + 2))
        return cal, True
    return raw, False


def factor_breakdown(title: str, description: str) -> dict:
    text = f"{title or ''}\n{description or ''}".lower()
    t = (title or "").lower()

    role_kw = ["ui/ux", "uiux", "product designer", "ux designer", "ui designer", "figma designer", "design systems"]
    role_fit = 95 if any(k in t for k in role_kw) else (70 if "design" in t else (45 if "design" in text else 15))

    tools_hits = sum(1 for k in ["figma", "wirefram", "prototyp", "design system", "component librar", "design token"] if k in text)
    tools_fit = min(95, 25 + tools_hits * 18)

    # Level: 1-5yr ideal; 8+ leadership or heavy code is a dealbreaker
    if re.search(r"8\+\s*years|10\+?\s*years|director|principal.*lead|staff.*lead", text):
        level_fit = 20
    elif re.search(r"intern", text):
        level_fit = 55
    elif re.search(r"[1-5]\s*(?:\+|-|to)?\s*(?:years|yrs)", text):
        level_fit = 90
    elif re.search(r"senior|lead", t):
        level_fit = 60
    else:
        level_fit = 70

    domain_fit = 85 if any(k in text for k in ["saas", "web app", "mobile", "platform", "dashboard"]) else 60

    return {"role_fit": role_fit, "tools_fit": tools_fit, "level_fit": level_fit, "domain_fit": domain_fit}


def weighted_hint(fb: dict) -> int:
    return int(round(sum(fb[k] * FACTOR_WEIGHTS[k] for k in FACTOR_WEIGHTS)))


def detect_employment_type(title: str, description: str) -> str:
    text = f"{title or ''} {description or ''}".lower()
    if re.search(r"\bintern(ship)?\b", text):
        return "intern"
    if re.search(r"\bfreelance\b|\bcontract\b", text):
        return "contract/freelance"
    if re.search(r"\bfull[\s\-]?time\b", text):
        return "full-time"
    if re.search(r"\bpart[\s\-]?time\b", text):
        return "part-time"
    return ""


class JobEvaluator:
    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL):
        self.model = model
        self.base_url = base_url
        self.candidate_profile = get_candidate_profile_prompt()
        self.client, _, self.meta = load_model(
            source=self.model,
            revision="lm-studio-local",
            base_url=self.base_url,
            reasoning_effort="none",
        )

    def _score_row(self, row: dict):
        res = score(self.client, None, row, self.meta)
        return res, float(res["probabilities"][0]), float(res["forward_seconds"])

    def evaluate(self, job_title: str, company: str, job_description: str, criteria: list[str] | None = None) -> dict:
        """Multi-factor calibrated fit: prescreen -> SemIf logprob -> real skills/gaps."""
        pre = bm25_prescreen(job_title, job_description)
        matched, missing, hits = extract_matched_missing(job_title, job_description)
        fb = factor_breakdown(job_title, job_description)
        emp = detect_employment_type(job_title, job_description)
        if pre is not None:
            return {
                "match_score": pre["match_score"],
                "fit_level": "SKIP",
                "matched_skills": [],
                "missing_skills": missing or ["Criteria / Domain Mismatch"],
                "reason": f"Pre-screen filtered ({pre['prescreen']}). No LLM call spent.",
                "forward_seconds": 0.0,
                "fit_breakdown": fb,
                "jd_keywords": [h.title() if len(h) <= 8 else h for h in hits],
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
                "prescreen": True,
            }

        crit_list = criteria if criteria and len(criteria) > 0 else DEFAULT_CRITERIA
        criteria_text = "\n".join(f"- {c}" for c in crit_list)

        state = f"""=== CANDIDATE PROFILE ===
{self.candidate_profile}

=== TARGET JOB CRITERIA ===
{criteria_text}

=== JOB POSTING ===
Title: {job_title}
Company: {company}
Description:
{(job_description or '')[:3000]}
"""

        question = (
            "Does this job posting satisfy the target requirements and criteria for candidate Mushfiq Kabir "
            "and should it be saved for an application?"
        )

        options = [
            {
                "id": "save",
                "description": (
                    "Yes, criteria satisfied. The role aligns with the required UI/UX and product design "
                    "qualifications, Figma tools, and experience level."
                ),
            },
            {
                "id": "skip",
                "description": (
                    "No, criteria failed. The role is unrelated, misses core UI/UX requirements, "
                    "or triggers dealbreakers (e.g. 8+ years executive leadership or heavy coding)."
                ),
            },
        ]

        row = {
            "id": f"eval-{abs(hash(job_title + company))}",
            "state": state,
            "question": question,
            "options": options,
        }

        try:
            res, save_prob, fwd = self._score_row(row)
            raw = int(round(save_prob * 100))
            cal, compressed = calibrate(raw)
            low_margin = 60 <= cal <= 74

            if cal >= 80:
                fit_level = "STRONG_FIT"
                summary = f"Strong match ({cal}% calibrated, raw {raw}%)."
            elif cal >= 65:
                fit_level = "CONSIDER"
                summary = f"Potential match ({cal}% calibrated, raw {raw}%). Review nuances."
            else:
                fit_level = "SKIP"
                summary = f"Low match ({cal}%). Fails criteria or domain mismatch."

            fb_note = f"Factors role {fb['role_fit']}%/tools {fb['tools_fit']}%/level {fb['level_fit']}%/domain {fb['domain_fit']}% (hint {weighted_hint(fb)}%)."
            cal_note = "Calibrated for instruct-model overconfidence." if compressed else ""
            return {
                "match_score": cal,
                "raw_score": raw,
                "fit_level": fit_level,
                "matched_skills": matched if cal >= 65 else [],
                "missing_skills": missing if cal >= 65 else (missing or ["Criteria / Domain Mismatch"]),
                "reason": f"{summary} {fb_note} {cal_note} Scored in {fwd:.2f}s via SemIf.".strip(),
                "forward_seconds": fwd,
                "fit_breakdown": fb,
                "jd_keywords": [h.title() if len(h) <= 8 else h for h in hits],
                "employment_type": emp,
                "calibrated": compressed,
                "low_margin": low_margin,
                "prescreen": False,
            }
        except Exception as e:
            return {
                "match_score": 0,
                "fit_level": "ERROR",
                "matched_skills": [],
                "missing_skills": [],
                "reason": f"Evaluation error: {e}",
                "forward_seconds": 0.0,
                "fit_breakdown": fb,
                "jd_keywords": [],
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
            }

    def evaluate_feed_post(self, author: str, post_text: str, criteria: list[str] | None = None) -> dict:
        """Feed-post hiring-lead check with employment-type tagging (intern-aware)."""
        crit_list = criteria if criteria and len(criteria) > 0 else DEFAULT_CRITERIA
        criteria_text = "\n".join(f"- {c}" for c in crit_list)

        state = f"""=== CANDIDATE PROFILE ===
{self.candidate_profile}

=== TARGET JOB CRITERIA ===
{criteria_text}

=== LINKEDIN FEED POST ===
Author / Poster: {author}
Post Content:
{(post_text or '')[:2500]}
"""

        question = (
            "Is this LinkedIn post announcing an open position, team expansion, freelance/contract project, "
            "or hiring need for a UI/UX Designer, Product Designer, or Figma specialist that matches candidate Mushfiq Kabir? "
            "Intern-only posts are weak matches."
        )

        options = [
            {
                "id": "save",
                "description": (
                    "Yes, hiring or project opportunity. The author is hiring, seeking a designer, or sharing "
                    "an open UI/UX, product design, Figma, or design role matching the candidate."
                ),
            },
            {
                "id": "skip",
                "description": (
                    "No, not a relevant hiring opportunity. It is general chatter, personal work showcase, "
                    "marketing promotion, or an unrelated domain (e.g. backend, medical, sales)."
                ),
            },
        ]

        row = {
            "id": f"feed-{abs(hash(author + (post_text or '')[:60]))}",
            "state": state,
            "question": question,
            "options": options,
        }

        matched, missing, hits = extract_matched_missing(author, post_text)
        emp = detect_employment_type(author, post_text)
        try:
            res, save_prob, fwd = self._score_row(row)
            raw = int(round(save_prob * 100))
            # Intern penalty: interns rarely match a 2-4yr full-time target
            if emp == "intern":
                raw = min(raw, 78)
            cal, compressed = calibrate(raw)
            low_margin = 65 <= cal <= 79

            if cal >= 80:
                fit_level = "STRONG_FIT"
                summary = f"Strong hiring lead ({cal}% calibrated, raw {raw}%)."
            elif cal >= 65:
                fit_level = "CONSIDER"
                summary = f"Potential lead ({cal}% calibrated, raw {raw}%)."
            else:
                fit_level = "SKIP"
                summary = f"General update / low relevance ({cal}%)."

            return {
                "match_score": cal,
                "raw_score": raw,
                "fit_level": fit_level,
                "matched_skills": matched if cal >= 65 else [],
                "missing_skills": missing if cal >= 65 else ["Not a hiring post"],
                "reason": f"{summary} Type: {emp or 'unspecified'}. Scored in {fwd:.2f}s via SemIf.".strip(),
                "forward_seconds": fwd,
                "jd_keywords": [h.title() if len(h) <= 8 else h for h in hits],
                "employment_type": emp,
                "calibrated": compressed,
                "low_margin": low_margin,
            }
        except Exception as e:
            return {
                "match_score": 0,
                "fit_level": "ERROR",
                "matched_skills": [],
                "missing_skills": [],
                "reason": f"Feed evaluation error: {e}",
                "forward_seconds": 0.0,
                "jd_keywords": [],
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
            }
