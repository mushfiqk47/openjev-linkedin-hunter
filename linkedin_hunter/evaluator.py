import re
import sys
from .config import FACTOR_WEIGHTS, LLM_BASE_URL, LLM_MODEL, PROJECT_ROOT, SKILL_VOCAB
from .cv_loader import get_candidate_profile_prompt
from .judgments import Judge, weighted_axes

sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

DECISION_WEIGHT = 0.5
AXES_WEIGHT = 0.5

DEFAULT_CRITERIA = [
    "[Required] Role focuses on UI/UX, Product Design, Visual Interface, or Figma design.",
    "[Required] Hands-on Figma wireframing, prototyping, design systems, or component libraries.",
    "[Preferred] Experience in SaaS platforms, web apps, or mobile interfaces.",
    "[Dealbreaker] Does NOT require 8+ years executive/director leadership or full-stack software development/coding.",
]

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

    matched = [m if m != "Ui/Ux" else "UI/UX" for m in matched]
    return matched, missing, hits

def bm25_prescreen(title: str, description: str):

    t = (title or "").lower()
    if any(bad in t for bad in DISQUALIFIED_TITLES):
        return {"match_score": 8, "fit_level": "SKIP", "prescreen": "disqualified-title"}
    text = f"{t} {(description or '').lower()}"
    design_tokens = ["design", "figma", "ui", "ux", "product", "prototype", "wireframe"]
    if not any(tok in text for tok in design_tokens):
        return {"match_score": 12, "fit_level": "SKIP", "prescreen": "no-design-signal"}
    return None

def calibrate(raw: int) -> tuple[int, bool]:

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

def blend_score(decision_pct: int, axes_hint: int) -> int:

    return int(round(DECISION_WEIGHT * decision_pct + AXES_WEIGHT * axes_hint))

def choose_skip_reason(axes: dict, missing: list[str], fit_level: str) -> str:

    if fit_level == "ERROR":
        return "Evaluation error; not scored."
    weakest = min(axes, key=axes.get) if axes else ""
    reasons = {
        "role_fit": "Not a design role.",
        "tools_fit": "No hands-on Figma / design-tools requirement.",
        "level_fit": "Seniority mismatch (too senior, coding-heavy, or intern).",
        "domain_fit": "Domain off-target.",
    }
    if axes and axes.get(weakest, 100) < 45 and reasons.get(weakest):
        return reasons[weakest]
    if missing:
        return f"Missing core signals: {', '.join(missing[:3])}."
    return "Below the fit threshold."

class JobEvaluator:
    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL,
                 client=None, meta: dict | None = None, use_model_axes: bool = True):

        self.model = model
        self.base_url = base_url
        self.use_model_axes = use_model_axes
        self.candidate_profile = get_candidate_profile_prompt()
        self.judge = Judge(base_url=base_url, model=model, client=client, meta=meta)
        self.client = self.judge.client
        self.meta = self.judge.meta

    def _score_row(self, row: dict):
        readout = self.judge.readout(row)
        return readout, readout.probabilities[0], readout.seconds

    def _axes(self, state: str, title: str, description: str) -> tuple[dict, float]:

        if self.use_model_axes:
            return self.judge.axis_scores(state)
        return factor_breakdown(title, description), 0.0

    def evaluate(self, job_title: str, company: str, job_description: str, criteria: list[str] | None = None) -> dict:

        pre = bm25_prescreen(job_title, job_description)
        matched, missing, hits = extract_matched_missing(job_title, job_description)
        heuristic_fb = factor_breakdown(job_title, job_description)
        emp = detect_employment_type(job_title, job_description)
        keywords = [h.title() if len(h) <= 8 else h for h in hits]
        if pre is not None:
            return {
                "match_score": pre["match_score"],
                "fit_level": "SKIP",
                "matched_skills": [],
                "missing_skills": missing or ["Criteria / Domain Mismatch"],
                "reason": f"Pre-screen filtered ({pre['prescreen']}). No LLM call spent.",
                "skip_reason": f"Pre-screen: {pre['prescreen']}.",
                "forward_seconds": 0.0,
                "fit_breakdown": heuristic_fb,
                "axes_score": weighted_hint(heuristic_fb),
                "jd_keywords": keywords,
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
                "needs_review": False,
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
            axes, axes_seconds = self._axes(state, job_title, job_description)
            axes_hint = weighted_axes(axes)
            decision_pct = int(round(save_prob * 100))
            raw = blend_score(decision_pct, axes_hint)
            cal, compressed = calibrate(raw)
            low_margin = 60 <= cal <= 74
            needs_review = low_margin or (cal < 65 and cal >= 55)

            if cal >= 80:
                fit_level = "STRONG_FIT"
                summary = f"Strong match ({cal}% calibrated, raw {raw}%)."
            elif cal >= 65:
                fit_level = "CONSIDER"
                summary = f"Potential match ({cal}% calibrated, raw {raw}%). Review nuances."
            else:
                fit_level = "SKIP"
                summary = f"Low match ({cal}%). Fails criteria or domain mismatch."

            fb_note = (f"Axes role {axes['role_fit']}%/tools {axes['tools_fit']}%/"
                       f"level {axes['level_fit']}%/domain {axes['domain_fit']}% (blend {axes_hint}%), "
                       f"decision {decision_pct}%.")
            cal_note = "Calibrated for instruct-model overconfidence." if compressed else ""
            total_seconds = fwd + axes_seconds
            skip_reason = choose_skip_reason(axes, missing, fit_level) if fit_level == "SKIP" else ""
            return {
                "match_score": cal,
                "raw_score": raw,
                "decision_score": decision_pct,
                "axes_score": axes_hint,
                "fit_level": fit_level,
                "matched_skills": matched if cal >= 65 else [],
                "missing_skills": missing if cal >= 65 else (missing or ["Criteria / Domain Mismatch"]),
                "reason": f"{summary} {fb_note} {cal_note} Scored in {total_seconds:.2f}s via SemIf.".strip(),
                "skip_reason": skip_reason,
                "forward_seconds": total_seconds,
                "fit_breakdown": axes,
                "jd_keywords": keywords,
                "employment_type": emp,
                "calibrated": compressed,
                "low_margin": low_margin,
                "needs_review": needs_review,
                "prescreen": False,
            }
        except Exception as e:
            return {
                "match_score": 0,
                "fit_level": "ERROR",
                "matched_skills": [],
                "missing_skills": [],
                "reason": f"Evaluation error: {e}",
                "skip_reason": f"Evaluation error: {e}",
                "forward_seconds": 0.0,
                "fit_breakdown": heuristic_fb,
                "axes_score": weighted_hint(heuristic_fb),
                "jd_keywords": [],
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
                "needs_review": False,
            }

    def evaluate_feed_post(self, author: str, post_text: str, criteria: list[str] | None = None) -> dict:

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

            if emp == "intern":
                raw = min(raw, 78)
            cal, compressed = calibrate(raw)
            low_margin = 65 <= cal <= 79
            needs_review = low_margin

            if cal >= 80:
                fit_level = "STRONG_FIT"
                summary = f"Strong hiring lead ({cal}% calibrated, raw {raw}%)."
            elif cal >= 65:
                fit_level = "CONSIDER"
                summary = f"Potential lead ({cal}% calibrated, raw {raw}%)."
            else:
                fit_level = "SKIP"
                summary = f"General update / low relevance ({cal}%)."

            skip_reason = ""
            if fit_level == "SKIP":
                skip_reason = ("Intern-only post (weak match)." if emp == "intern"
                               else "Not a hiring post for a matching design role.")
            return {
                "match_score": cal,
                "raw_score": raw,
                "fit_level": fit_level,
                "matched_skills": matched if cal >= 65 else [],
                "missing_skills": missing if cal >= 65 else ["Not a hiring post"],
                "reason": f"{summary} Type: {emp or 'unspecified'}. Scored in {fwd:.2f}s via SemIf.".strip(),
                "skip_reason": skip_reason,
                "forward_seconds": fwd,
                "jd_keywords": [h.title() if len(h) <= 8 else h for h in hits],
                "employment_type": emp,
                "calibrated": compressed,
                "low_margin": low_margin,
                "needs_review": needs_review,
            }
        except Exception as e:
            return {
                "match_score": 0,
                "fit_level": "ERROR",
                "matched_skills": [],
                "missing_skills": [],
                "reason": f"Feed evaluation error: {e}",
                "skip_reason": f"Feed evaluation error: {e}",
                "forward_seconds": 0.0,
                "jd_keywords": [],
                "employment_type": emp,
                "calibrated": False,
                "low_margin": False,
                "needs_review": False,
            }
