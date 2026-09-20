"""Storage and reporting engine for job listings."""

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from .config import OUTPUT_DIR, SEEN_JOBS_FILE, COMPANY_ALIASES


def _norm_text(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum() or ch.isspace()).strip()


def normalize_company(company: str) -> str:
    """Canonical company key resolving poster aliases (nextjobz -> european it institute)."""
    c = _norm_text(company)
    return COMPANY_ALIASES.get(c, c)


def normalize_signature(title: str, company: str) -> str:
    """Creates a normalized string signature to detect duplicate postings across queries."""
    t = _norm_text(title)
    c = normalize_company(company)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t)
    c = re.sub(r"\s+", " ", c)
    return f"{t} @@ {c}"


def jd_hash(description: str) -> str:
    """Stable hash of normalized JD body — catches same JD reposted under other posters."""
    body = re.sub(r"\s+", " ", (_norm_text(description or "") or ""))[:2000]
    return hashlib.sha256(body.encode()).hexdigest()[:16] if body else ""


def sanitize_md_cell(s: str, max_len: int = 80) -> str:
    """Make a string safe for a markdown table cell: no newlines/pipes, bounded length."""
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = s.replace("|", "/")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s or "—"


def extract_deadline(description: str) -> str:
    m = re.search(
        r"(?:last date|deadline|apply by|apply before)\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
        description or "",
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def extract_posted_hint(description: str) -> str:
    # Detail pane rarely has posted date; card metadata sometimes does — best effort.
    m = re.search(r"(\d+\s+(?:hour|day|week|month)s?\s+ago|just now|today|yesterday)", description or "", re.IGNORECASE)
    return m.group(1).strip() if m else ""


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


def compute_priority(score: int, employment_type: str, missing_count: int) -> str:
    if employment_type == "intern" and score >= 80:
        return "P2"  # good lead but not a full-time target role
    if score >= 85 and missing_count <= 2:
        return "P1 apply-now"
    if score >= 75:
        return "P2"
    return "P3"


def build_cover_hook(title: str, company: str, jd_keywords: list) -> str:
    kws = ", ".join((jd_keywords or [])[:3]) or "Figma, design systems, prototyping"
    t = sanitize_md_cell(title, 60)
    c = sanitize_md_cell(company, 40)
    return f"Pursuing the {t} at {c} — my {kws} work maps directly to your brief."


def extract_jd_keywords(title: str, description: str, vocab: list[str] | None = None) -> list[str]:
    """Best-effort keyword hits from JD against skill vocab (also used pre-LLM)."""
    try:
        from .config import SKILL_VOCAB
    except Exception:
        SKILL_VOCAB = []
    vocab = vocab or SKILL_VOCAB
    text = f"{title or ''}\n{description or ''}".lower()
    hits = [v for v in vocab if v.lower() in text]
    # Prefer multi-word / most specific first, cap at 10
    hits.sort(key=lambda v: (-len(v), v))
    return hits[:10]


def load_seen_state(path: Path = SEEN_JOBS_FILE) -> dict:
    """Loads all seen job IDs, signatures, JD hashes, skip reasons, and search queries."""
    default_state = {
        "seen_ids": set(),
        "seen_signatures": set(),
        "seen_jd_hashes": set(),
        "searched_queries": set(),
        "skip_reasons": {},
    }
    if not path.exists():
        return default_state
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "seen_ids": set(data.get("seen_ids", [])),
                "seen_signatures": set(data.get("seen_signatures", [])),
                "seen_jd_hashes": set(data.get("seen_jd_hashes", [])),
                "searched_queries": set(data.get("searched_queries", [])),
                "skip_reasons": dict(data.get("skip_reasons", {})),
            }
    except Exception:
        return default_state


def _persist_seen(seen_state: dict, path: Path = SEEN_JOBS_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "seen_ids": sorted(seen_state["seen_ids"]),
                "seen_signatures": sorted(seen_state["seen_signatures"]),
                "seen_jd_hashes": sorted(seen_state.get("seen_jd_hashes", set())),
                "searched_queries": sorted(seen_state["searched_queries"]),
                "skip_reasons": dict(seen_state.get("skip_reasons", {})),
            }, f, indent=2)
    except Exception:
        pass


def save_seen_job(job_id: str, title: str, company: str, seen_state: dict | None = None,
                  path: Path = SEEN_JOBS_FILE, description: str = "", reason: str = ""):
    """Persists a job ID, its normalized signature, and JD hash to prevent re-evaluation."""
    sig = normalize_signature(title, company)
    jh = jd_hash(description) if description else ""
    if seen_state is not None:
        seen_state["seen_ids"].add(job_id)
        seen_state["seen_signatures"].add(sig)
        if jh:
            seen_state.setdefault("seen_jd_hashes", set()).add(jh)
        if reason:
            seen_state.setdefault("skip_reasons", {})[str(job_id)] = reason
        _persist_seen(seen_state, path)
    else:
        current = load_seen_state(path)
        current["seen_ids"].add(job_id)
        current["seen_signatures"].add(sig)
        if jh:
            current.setdefault("seen_jd_hashes", set()).add(jh)
        if reason:
            current.setdefault("skip_reasons", {})[str(job_id)] = reason
        _persist_seen(current, path)


def save_searched_query(query: str, seen_state: dict | None = None, path: Path = SEEN_JOBS_FILE):
    """Records that a search query has been performed to avoid repeating the exact search."""
    q_norm = query.strip().lower()
    if seen_state is not None:
        seen_state["searched_queries"].add(q_norm)
        _persist_seen(seen_state, path)
    else:
        current = load_seen_state(path)
        current["searched_queries"].add(q_norm)
        _persist_seen(current, path)


def is_job_seen(job_id: str, title: str, company: str, seen_state: dict, description: str = "") -> bool:
    """Checks ID, (title, company) signature, and JD-body hash."""
    if job_id and job_id in seen_state["seen_ids"]:
        return True
    sig = normalize_signature(title, company)
    if sig in seen_state["seen_signatures"]:
        return True
    if description:
        jh = jd_hash(description)
        if jh and jh in seen_state.get("seen_jd_hashes", set()):
            return True
    return False


def load_seen_job_ids(path: Path = SEEN_JOBS_FILE) -> set[str]:
    state = load_seen_state(path)
    return state["seen_ids"]


def save_seen_job_id(job_id: str, path: Path = SEEN_JOBS_FILE):
    save_seen_job(job_id, "", "", path=path)


def get_stats(path: Path = SEEN_JOBS_FILE) -> dict:
    st = load_seen_state(path)
    reasons: dict[str, int] = {}
    for r in st.get("skip_reasons", {}).values():
        reasons[r] = reasons.get(r, 0) + 1
    return {
        "seen_ids": len(st["seen_ids"]),
        "seen_signatures": len(st["seen_signatures"]),
        "seen_jd_hashes": len(st.get("seen_jd_hashes", set())),
        "searched_queries": len(st["searched_queries"]),
        "skip_reasons": reasons,
    }


class JobStore:
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.json_file = self.output_dir / "matched_jobs.json"
        self.md_file = self.output_dir / "jobs_report.md"
        self.csv_file = self.output_dir / "jobs.csv"

    def load_matched_jobs(self) -> list[dict]:
        if not self.json_file.exists():
            return []
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_job(self, job_record: dict):
        """Appends a new matched job (JD-hash deduped, enriched) and regenerates reports."""
        jobs = self.load_matched_jobs()
        new_jh = jd_hash(job_record.get("description", ""))
        # Avoid duplicate records by ID or identical JD body
        for j in jobs:
            if j.get("job_id") == job_record.get("job_id"):
                return
            if new_jh and jd_hash(j.get("description", "")) == new_jh and new_jh != "":
                # Same JD reposted under a different poster — keep first, annotate alias
                j.setdefault("aliases", [])
                alias = f"{job_record.get('title','')} @ {job_record.get('company','')}"
                if alias not in j["aliases"]:
                    j["aliases"].append(alias)
                with open(self.json_file, "w", encoding="utf-8") as f:
                    json.dump(jobs, f, indent=2, ensure_ascii=False)
                self._write_markdown_report(jobs)
                self._write_csv_report(jobs)
                return

        # Enrich + sanitize
        title = (job_record.get("title") or "").replace("\n", " ").strip()
        company = (job_record.get("company") or "").replace("\n", " ").strip()
        desc = job_record.get("description", "") or ""
        job_record["title"] = re.sub(r"\s+", " ", title)
        job_record["company"] = re.sub(r"\s+", " ", company)
        job_record.setdefault("jd_keywords", extract_jd_keywords(title, desc))
        job_record.setdefault("deadline", extract_deadline(desc))
        job_record.setdefault("posted_hint", extract_posted_hint(desc))
        job_record.setdefault("employment_type", detect_employment_type(title, desc))
        missing = job_record.get("missing_skills", []) or []
        job_record.setdefault(
            "priority",
            compute_priority(int(job_record.get("match_score", 0)), job_record["employment_type"], len(missing)),
        )
        if not job_record.get("cover_hook"):
            job_record["cover_hook"] = build_cover_hook(title, company, job_record["jd_keywords"])
        job_record["jd_hash"] = new_jh
        job_record["saved_at"] = datetime.now().isoformat()
        jobs.append(job_record)

        # Sort: P1 first, then score descending
        order = {"P1 apply-now": 0, "P1": 0, "P2": 1, "P3": 2}
        jobs.sort(key=lambda x: (order.get(str(x.get("priority", "P3")), 2), -int(x.get("match_score", 0))))

        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)

        self._write_markdown_report(jobs)
        self._write_csv_report(jobs)

    def _write_markdown_report(self, jobs: list[dict]):
        is_feed = lambda j: str(j.get("job_id", "")).startswith("feed_") or "Feed" in str(j.get("location", ""))
        site_jobs = [j for j in jobs if not is_feed(j)]
        feed_jobs = [j for j in jobs if is_feed(j)]
        top3 = site_jobs[:3]
        lines = [
            "# 🎯 LinkedIn Matched Jobs Report",
            f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Total Matched Opportunities:** {len(jobs)} ({len(site_jobs)} jobs + {len(feed_jobs)} network leads)  ",
            "",
        ]
        if top3:
            lines += ["## ⚡ Top 3 — Apply Now", ""]
            for i, job in enumerate(top3, 1):
                lines.append(
                    f"{i}. **{sanitize_md_cell(job.get('title'), 70)}** @ **{sanitize_md_cell(job.get('company'), 40)}** "
                    f"— **{job.get('match_score', 0)}%** (`{job.get('priority', '')}`) "
                    f"[Apply / View]({job.get('job_url', '')})"
                )
            lines += ["", "---", ""]

        lines += ["## Summary Table", "",
            "| # | Score | Priority | Job Title | Company | Location | Type | Deadline | Link |",
            "|:-:|:-----:|:--------:|:----------|:--------|:---------|:----:|:--------:|:----:|",
        ]
        for idx, job in enumerate(site_jobs, 1):
            score = int(job.get("match_score", 0))
            badge = "🟢" if score >= 80 else ("🟡" if score >= 65 else "⚪")
            lines.append(
                f"| {idx} | {badge} **{score}%** | `{sanitize_md_cell(str(job.get('priority', '')), 14)}` "
                f"| {sanitize_md_cell(job.get('title'), 60)} "
                f"| **{sanitize_md_cell(job.get('company'), 30)}** "
                f"| {sanitize_md_cell(job.get('location'), 30)} "
                f"| {sanitize_md_cell(job.get('employment_type', ''), 16)} "
                f"| {sanitize_md_cell(job.get('deadline', ''), 14)} "
                f"| [Apply]({job.get('job_url', '')}) |"
            )
        lines += ["", "---", "", "## Detailed Job Breakdowns", ""]
        for job in site_jobs:
            score = int(job.get("match_score", 0))
            title = sanitize_md_cell(job.get("title"), 90)
            company = sanitize_md_cell(job.get("company"), 60)
            link = job.get("job_url", "")
            company_url = job.get("company_url", "")
            comp_display = f"[{company}]({company_url})" if company_url else company
            lines.append(f"### [{title}]({link}) — {comp_display}")
            lines.append(f"- **Match Score:** **{score}%** (`{job.get('fit_level', '')}`) · **Priority:** `{job.get('priority', '')}`")
            loc = sanitize_md_cell(job.get("location"), 60)
            lines.append(f"- **Location:** {loc}" + (f" · **Type:** {job.get('employment_type')}" if job.get("employment_type") else ""))
            if job.get("deadline"):
                lines.append(f"- **Deadline:** {job['deadline']}")
            if job.get("recruiter_name") or job.get("recruiter_url"):
                rn = job.get("recruiter_name", "Profile")
                ru = job.get("recruiter_url", "")
                lines.append(f"- **Hiring Lead:** [{rn}]({ru})" if ru else f"- **Hiring Lead:** {rn}")
            lines.append(f"- **AI Analysis:** {job.get('reason', '')}")
            fb = job.get("fit_breakdown") or {}
            if fb:
                lines.append("- **Fit breakdown:** " + ", ".join(f"{k} {v}%" for k, v in fb.items()))
            kws = ", ".join(job.get("jd_keywords", [])) or "—"
            lines.append(f"- **JD keywords (mirror in resume):** `{kws}`")
            ms = ", ".join(job.get("matched_skills", [])) or "None listed"
            lines.append(f"- **Matching skills:** `{ms}`")
            gaps = ", ".join(job.get("missing_skills", []))
            if gaps:
                lines.append(f"- **Gaps to address:** `{gaps}`")
            if job.get("cover_hook"):
                lines.append(f"- **Cover opener:** _{job['cover_hook']}_")
            if job.get("aliases"):
                lines.append(f"- **Also posted as:** {'; '.join(job['aliases'][:3])}")
            lines.append(f"- **Job Link:** [{link}]({link})")
            lines.append("")

        if feed_jobs:
            lines += ["---", "", "## 📡 Network Leads (LinkedIn Feed — separate from job posts)", "",
                "| Score | Author | Type | Link |",
                "|:-----:|:-------|:----:|:----:|",
            ]
            for job in feed_jobs:
                score = int(job.get("match_score", 0))
                badge = "🟢" if score >= 80 else ("🟡" if score >= 75 else "⚪")
                author = sanitize_md_cell(job.get("company", ""), 30)
                lines.append(
                    f"| {badge} **{score}%** | {author} "
                    f"| {sanitize_md_cell(job.get('employment_type', ''), 16)} "
                    f"| [View]({job.get('job_url', '')}) |"
                )
            lines += [""]
            for job in feed_jobs:
                lines.append(f"### {sanitize_md_cell(job.get('title'), 90)}")
                lines.append(f"- **Score:** **{job.get('match_score', 0)}%** · Type: {job.get('employment_type', 'n/a')}")
                lines.append(f"- **Why:** {job.get('reason', '')}")
                lines.append(f"- **Link:** [{job.get('job_url', '')}]({job.get('job_url', '')})")
                lines.append("")

        with open(self.md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _write_csv_report(self, jobs: list[dict]):
        fieldnames = [
            "match_score", "fit_level", "priority", "title", "company",
            "location", "employment_type", "deadline", "posted_hint",
            "company_url", "recruiter_name", "recruiter_url", "job_url",
            "matched_skills", "missing_skills", "jd_keywords",
            "fit_breakdown", "cover_hook", "reason", "saved_at",
        ]
        with open(self.csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for job in jobs:
                row = dict(job)
                for k in ("matched_skills", "missing_skills", "jd_keywords"):
                    if isinstance(row.get(k), list):
                        row[k] = "; ".join(row[k])
                if isinstance(row.get("fit_breakdown"), dict):
                    row["fit_breakdown"] = json.dumps(row["fit_breakdown"])
                writer.writerow(row)
