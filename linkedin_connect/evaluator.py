from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from .config import LLM_BASE_URL, LLM_MODEL, MIN_CONNECT_SCORE

DISQUALIFIED_TOKENS = [
    "student", "intern", "internship", "trainee", "apprentice",
    "entry level", "junior", "job seeker", "looking for opportunity",
    "doctor", "nurse", "physician", "dentist", "medical",
    "civil engineer", "mechanical engineer", "chemical engineer",
    "accountant", "auditor", "bookkeeper", "tax consultant",
    "telecaller", "call center", "customer support representative",
    "warehouse", "driver", "courier", "cashier", "cook", "chef",
    "real estate agent", "realtor", "insurance agent",
]

DESIGN_LEADER_TOKENS = [
    "head of design", "vp of design", "vp design", "vice president design",
    "director of design", "design director", "creative director",
    "head of product design", "director of product design",
    "lead product designer", "lead ui/ux designer", "design lead",
    "principal designer", "principal product designer", "staff designer",
    "staff product designer", "design manager", "ux manager",
    "art director", "executive creative director", "chief design officer",
]

RECRUITER_TOKENS = [
    "technical recruiter", "tech recruiter", "design recruiter",
    "talent acquisition", "talent partner", "head of talent",
    "talent lead", "recruiting lead", "recruitment manager",
    "head of people", "people partner", "talent specialist",
    "senior recruiter", "lead recruiter", "headhunter", "sourcer",
]

FOUNDER_TOKENS = [
    "founder", "co-founder", "founding partner", "ceo", "chief executive officer",
    "cto", "cpo", "chief product officer", "managing director",
    "startup founder", "early stage founder", "executive director",
]

PEER_TOKENS = [
    "product designer", "ui/ux designer", "senior product designer",
    "senior ui/ux designer", "interaction designer", "visual designer",
    "figma designer", "design systems designer",
]

def prescreen_headline(headline: str) -> dict[str, Any] | None:
    h = (headline or "").lower()
    if not h:
        return {
            "archetype": "unknown",
            "score": 40,
            "fit_level": "SKIP",
            "reason": "Empty profile headline",
            "backend": "prescreen",
        }

    for bad in DISQUALIFIED_TOKENS:
        pattern = r"\b" + re.escape(bad) + r"\b"
        if re.search(pattern, h):
            return {
                "archetype": "disqualified",
                "score": 15,
                "fit_level": "SKIP",
                "reason": f"Disqualified profile token ('{bad}')",
                "backend": "prescreen",
            }

    for kw in DESIGN_LEADER_TOKENS:
        if kw in h:
            return {
                "archetype": "design_leader",
                "score": 92,
                "fit_level": "EXCELLENT",
                "reason": f"Design leadership keyword matched ('{kw}')",
                "backend": "heuristic",
            }

    for kw in FOUNDER_TOKENS:
        if kw in h:
            return {
                "archetype": "founder",
                "score": 90,
                "fit_level": "EXCELLENT",
                "reason": f"Startup founder/executive keyword matched ('{kw}')",
                "backend": "heuristic",
            }

    for kw in RECRUITER_TOKENS:
        if kw in h:
            return {
                "archetype": "recruiter",
                "score": 88,
                "fit_level": "EXCELLENT",
                "reason": f"Recruiting/talent keyword matched ('{kw}')",
                "backend": "heuristic",
            }

    for kw in PEER_TOKENS:
        if kw in h:
            return {
                "archetype": "design_peer",
                "score": 75,
                "fit_level": "GOOD",
                "reason": f"Product design peer keyword matched ('{kw}')",
                "backend": "heuristic",
            }

    return None

class ProfileEvaluator:
    def __init__(self, base_url: str = LLM_BASE_URL, model: str = LLM_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def evaluate(self, name: str, headline: str, location: str = "") -> dict[str, Any]:
        pre = prescreen_headline(headline)
        if pre is not None:
            score = pre["score"]
            pre["name"] = name
            pre["headline"] = headline
            pre["location"] = location
            pre["qualified"] = score >= MIN_CONNECT_SCORE
            return pre

        llm_res = self._call_llm(name, headline, location)
        if llm_res:
            score = llm_res.get("score", 65)
            llm_res["name"] = name
            llm_res["headline"] = headline
            llm_res["location"] = location
            llm_res["qualified"] = score >= MIN_CONNECT_SCORE
            llm_res["fit_level"] = "EXCELLENT" if score >= 85 else ("GOOD" if score >= 75 else "SKIP")
            return llm_res

        score = 65
        return {
            "name": name,
            "headline": headline,
            "location": location,
            "archetype": "general",
            "score": score,
            "fit_level": "SKIP",
            "reason": "Unclassified headline without strong target keywords",
            "backend": "fallback",
            "qualified": score >= MIN_CONNECT_SCORE,
        }

    def _call_llm(self, name: str, headline: str, location: str) -> dict[str, Any] | None:
        prompt = f"""You are evaluating a LinkedIn profile for networking relevance.
The ideal connections are:
1. Design Leaders (Head of Design, Creative Director, VP Design, Design Manager)
2. Tech & Design Recruiters (Talent Partner, Technical Recruiter, Head of Talent)
3. Startup Founders / Executives (CEO, Co-Founder, CTO, CPO)

Profile Information:
Name: {name}
Headline: {headline}
Location: {location}

Rate this profile from 0 to 100 on networking value for a Senior UI/UX & Product Designer.
Return ONLY valid JSON:
{{
  "archetype": "design_leader" | "recruiter" | "founder" | "other",
  "score": <0-100 integer>,
  "reason": "<short 1-sentence rationale>"
}}"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a professional recruiting evaluator. Return only JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                m = re.search(r"\{.*\}", content, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    parsed["backend"] = "llm"
                    return parsed
        except Exception:
            pass
        return None
