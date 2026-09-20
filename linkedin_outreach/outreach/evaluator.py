import json
import os
import sys
import urllib.error
import urllib.request

from outreach.config import (
    BACKEND_SRC,
    CV_FILE,
    DEFAULT_FILTER_LOW_RELEVANCE,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_SEMIF_BASE_URL,
    DEFAULT_SEMIF_ENABLED,
    DEFAULT_SEMIF_MODEL,
    get_int,
    get_str,
)

if BACKEND_SRC not in sys.path and os.path.isdir(BACKEND_SRC):
    sys.path.insert(0, BACKEND_SRC)

try:
    from semif_phase1.remote import load_model, score
    SEMIF_AVAILABLE = True
except Exception:
    SEMIF_AVAILABLE = False
    load_model = None
    score = None

DISQUALIFIED_HEADLINE_TOKENS = [
    "radiologist", "radiology", "doctor", "physician", "nurse", "clinic", "hospital",
    "pharmacist", "pharmacy", "medical officer", "dentist",
    "accountant", "audit associate", "auditor", "cashier", "banking officer",
    "devops engineer", "cloud infrastructure",
    "video editor", "videographer", "cinematographer",
    "telecaller", "call center", "customer support executive",
    "warehouse", "delivery driver", "delivery boy", "driver",
    "cook", "chef", "waiter", "security guard",
    "fashion designer", "textile designer", "apparel merchandiser",
    "civil engineer", "mechanical engineer", "electrical engineer",
]

_cv_cache = []

def load_candidate_profile():

    if _cv_cache:
        return _cv_cache[0]
    profile = (
        "Mushfiq Kabir — UI/UX and Graphic Designer. Experienced in SaaS platforms, "
        "mobile apps, Figma workflows, design systems, and wireframing/prototyping. "
        "Searching for job or project-based work."
    )
    if os.path.exists(CV_FILE):
        try:
            with open(CV_FILE, encoding="utf-8") as f:
                data = json.load(f)
                basics = data.get("basics", {})
                summary = data.get("summary", "")
                label = basics.get("label", "UI/UX Designer")
                name = basics.get("name", "Mushfiq Kabir")
                profile = f"{name} — {label}. {summary}"
        except Exception:
            pass
    _cv_cache.append(profile)
    return profile

def bm25_prescreen(headline):

    h = (headline or "").lower()
    if not h:
        return None
    for bad in DISQUALIFIED_HEADLINE_TOKENS:
        if bad in h:
            return {
                "archetype": "disqualified",
                "relevance": 10,
                "reason": f"disqualified headline keyword ('{bad}')",
                "backend": "prescreen",
            }
    return None

def heuristic_evaluate(name, headline):

    h = (headline or "").lower()

    recruiter_kw = ["recruiter", "talent acquisition", "talent partner", "headhunter",
                    "hiring", "sourcer", "people ops", "human resources", "hr manager"]
    if any(k in h for k in recruiter_kw):
        return {
            "archetype": "recruiter",
            "relevance": 95,
            "reason": "recruiter/hiring manager keyword match",
            "backend": "heuristic",
        }

    founder_kw = ["founder", "co-founder", "ceo", "cto", "cpo", "managing director",
                  "owner", "partner", "chief executive", "vp of product", "head of product"]
    if any(k in h for k in founder_kw):
        return {
            "archetype": "founder",
            "relevance": 90,
            "reason": "founder/executive keyword match",
            "backend": "heuristic",
        }

    peer_kw = ["ui/ux", "ui designer", "ux designer", "product designer", "visual designer",
               "design lead", "head of design", "design system", "interaction designer", "figma"]
    if any(k in h for k in peer_kw):
        return {
            "archetype": "peer",
            "relevance": 85,
            "reason": "peer product/UI/UX designer match",
            "backend": "heuristic",
        }

    general_kw = ["software", "developer", "engineer", "frontend", "full stack",
                  "product manager", "project manager", "marketing", "digital"]
    if any(k in h for k in general_kw):
        return {
            "archetype": "general",
            "relevance": 70,
            "reason": "tech/software general professional match",
            "backend": "heuristic",
        }

    return {
        "archetype": "general",
        "relevance": 60,
        "reason": "general 1st-degree connection",
        "backend": "heuristic",
    }

class SemIfJudge:

    def __init__(self, base_url=None, model=None, client=None, meta=None):
        self.base_url = base_url or get_str("SEMIF_BASE_URL", DEFAULT_SEMIF_BASE_URL)
        self.model = model or get_str("SEMIF_MODEL", DEFAULT_SEMIF_MODEL)
        if client is not None:
            self.client = client
            self.meta = meta or {"source": self.model, "backend": "injected"}
        else:
            if not SEMIF_AVAILABLE:
                raise RuntimeError("semif_phase1 is not available")
            self.client, _, self.meta = load_model(
                source=self.model,
                revision="lm-studio-local",
                base_url=self.base_url,
                reasoning_effort="none",
            )

    def judge(self, question, state, options, row_id="eval"):
        row = {
            "id": str(row_id),
            "state": state,
            "question": question,
            "options": [{"id": str(oid), "description": str(desc)} for oid, desc in options],
        }
        res = score(self.client, None, row, self.meta)
        probs = [float(p) for p in res["probabilities"]]
        opt_ids = [str(i) for i in res["option_ids"]]
        best_idx = max(range(len(probs)), key=probs.__getitem__)
        return opt_ids[best_idx], probs[best_idx], probs, res.get("forward_seconds", 0.0)

    def classify_archetype(self, name, headline):
        state = (
            f"Candidate: Mushfiq Kabir, UI/UX Designer looking for job or project-based work.\n"
            f"Connection Name: {name}\n"
            f"Connection Headline: {headline or 'Not specified'}"
        )
        question = "What professional role category does this connection belong to?"
        options = [
            ("recruiter", "Recruiter, Talent Acquisition, HR Manager, Sourcer, or Hiring Partner."),
            ("founder", "Founder, Co-Founder, CEO, CTO, VP, Managing Director, or Agency Owner."),
            ("peer", "UI/UX Designer, Product Designer, Visual Designer, or Design Lead."),
            ("general", "Other tech, product, engineering, software, or digital role."),
        ]
        top_id, prob, _, _ = self.judge(question, state, options, row_id="archetype")
        return top_id, prob

    def score_relevance(self, name, headline):
        state = (
            f"Candidate: Mushfiq Kabir, UI/UX Designer looking for full-time or project design roles.\n"
            f"Connection: {name}\n"
            f"Headline: {headline or 'Not specified'}"
        )
        question = (
            "Is this contact a valuable connection to reach out to for UI/UX design jobs, "
            "freelance work, referrals, or design opportunities?"
        )
        options = [
            ("yes", "Yes, high relevance: recruiter, hiring decision maker, peer designer, or in tech/digital."),
            ("no", "No, low relevance: completely unrelated field, manual labor, non-tech, or student."),
        ]
        top_id, prob, probs, _ = self.judge(question, state, options, row_id="relevance")
        p_yes = probs[0] if top_id == "yes" else probs[1]
        return int(round(p_yes * 100))

_judge_instance = None

def get_judge():

    global _judge_instance
    if _judge_instance is not None:
        return _judge_instance
    enabled = get_int("SEMIF_ENABLED", DEFAULT_SEMIF_ENABLED) != 0
    if not enabled or not SEMIF_AVAILABLE:
        return None
    try:
        _judge_instance = SemIfJudge()
        return _judge_instance
    except Exception:
        return None

def reset_judge():
    global _judge_instance
    _judge_instance = None

def check_semif_connection(base_url=None, timeout=2):

    url = (base_url or get_str("SEMIF_BASE_URL", DEFAULT_SEMIF_BASE_URL)).rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SemIf-Preflight/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return True, f"LM Studio reachable ({len(models)} model(s): {', '.join(models[:3])})"
            return False, f"LM Studio returned status {resp.status}"
    except urllib.error.URLError as e:
        return False, f"Connection refused or timed out ({e.reason})"
    except Exception as e:
        return False, str(e)

def evaluate_contact(contact, judge=None):

    name = contact.get("name", "")
    headline = contact.get("headline", "")

    prescreen_result = bm25_prescreen(headline)
    if prescreen_result is not None:
        return prescreen_result

    active_judge = judge or get_judge()
    if active_judge is not None:
        try:
            archetype, prob = active_judge.classify_archetype(name, headline)
            relevance = active_judge.score_relevance(name, headline)
            return {
                "archetype": archetype,
                "relevance": relevance,
                "reason": f"SemIf classified as {archetype} (confidence: {round(prob*100)}%)",
                "backend": "semif",
            }
        except Exception:

            pass

    return heuristic_evaluate(name, headline)
