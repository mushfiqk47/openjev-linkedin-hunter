import json
from pathlib import Path
from .config import CV_JSON_PATH

def load_cv_data(path: Path = CV_JSON_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"CV JSON file not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_candidate_profile_prompt(cv_data: dict | None = None) -> str:

    if cv_data is None:
        cv_data = load_cv_data()

    basics = cv_data.get("basics", {})
    summary = cv_data.get("summary", "")

    skills_list = []
    for cat in cv_data.get("skills", []):
        category_name = cat.get("category", "")
        keywords = ", ".join(cat.get("keywords", []))
        skills_list.append(f"- {category_name}: {keywords}")
    skills_text = "\n".join(skills_list)

    work_list = []
    for job in cv_data.get("work", []):
        pos = job.get("position", "")
        comp = job.get("company", "")
        start = job.get("startDate", "")
        end = job.get("endDate", "")
        highlights = "; ".join(job.get("highlights", []))
        work_list.append(f"- {pos} at {comp} ({start} - {end}): {highlights}")
    work_text = "\n".join(work_list)

    projects_list = []
    for proj in cv_data.get("projects", []):
        name = proj.get("name", "")
        ptype = proj.get("type", "")
        desc = proj.get("description", "")
        projects_list.append(f"- {name} ({ptype}): {desc}")
    projects_text = "\n".join(projects_list)

    profile = f"""
Candidate Name: {basics.get('name', 'Mushfiq Kabir')}
Target Titles: {basics.get('label', 'Graphic & UI/UX Designer')}, Product Designer, UI Designer, Figma Designer
Location: {basics.get('location', {}).get('city', 'Dhaka')}, {basics.get('location', {}).get('country', 'Bangladesh')} (Seeking Remote / Flexible)
Summary: {summary}

Core Technical Skills:
{skills_text}

Experience:
{work_text}

Key Projects & Portfolio:
{projects_text}
""".strip()
    return profile
