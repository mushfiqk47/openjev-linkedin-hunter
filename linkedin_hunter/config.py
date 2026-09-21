import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT_DIR = BASE_DIR / "output"
SEEN_JOBS_FILE = BASE_DIR / "seen_jobs.json"
CV_JSON_PATH = PROJECT_ROOT / "Mushfiq_Kabir_CV.json"
ENV_FILE = BASE_DIR / ".env"
ROOT_ENV_FILE = PROJECT_ROOT / ".env"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_env(env_path: Path | str | None = None):

    candidates = []
    if env_path is not None:
        candidates.append(Path(env_path))
    else:
        candidates.extend([ENV_FILE, ROOT_ENV_FILE])

    for path in candidates:
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        except Exception as e:
            print(f"[WARN] Failed reading .env at {path}: {e}")

load_env()

def get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default

def get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default

def get_str(name: str, default: str) -> str:
    return os.environ.get(name, default)

def get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    val = str(val).strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default

_queries_env = os.environ.get("DEFAULT_QUERIES")
if _queries_env:
    DEFAULT_QUERIES = [q.strip() for q in _queries_env.split(",") if q.strip()]
else:
    DEFAULT_QUERIES = [
        "UI/UX Designer",
        "Product Designer",
        "Figma Designer",
        "UI Designer",
        "Design Systems Designer",
    ]

RECENCY_FILTERS = {
    "24h": "r86400",
    "week": "r604800",
    "any": "",
}

WORK_TYPES = {
    "remote": "2",
    "on_site": "1",
    "hybrid": "3",
    "all": "",
}

LLM_BASE_URL = get_str("LLM_BASE_URL", get_str("SEMIF_REMOTE_BASE_URL", "http://localhost:1234/v1"))
LLM_MODEL = get_str("LLM_MODEL", get_str("SEMIF_REMOTE_MODEL", "qwen3.5-4b"))

DEFAULT_MIN_SCORE = get_int("DEFAULT_MIN_SCORE", 70)
DEFAULT_MIN_MATCHES = get_int("DAILY_TARGET_MATCHES", get_int("DEFAULT_MIN_MATCHES", 10))
DEFAULT_MAX_PAGES_PER_QUERY = get_int("DEFAULT_MAX_PAGES_PER_QUERY", 2)
DEFAULT_JOB_LIMIT = get_int("DEFAULT_JOB_LIMIT", 50)
FEED_MIN_SCORE = get_int("FEED_MIN_SCORE", 65)
DAILY_EVALUATE_CAP = get_int("DAILY_EVALUATE_CAP", 120)

ENABLE_HUMAN_DELAYS = get_bool("ENABLE_HUMAN_DELAYS", False)
HUMAN_DELAY_MIN = get_float("HUMAN_DELAY_MIN", 0.0)
HUMAN_DELAY_MAX = get_float("HUMAN_DELAY_MAX", 0.0)
CARD_CLICK_DELAY_MIN = get_float("CARD_CLICK_DELAY_MIN", 0.0)
CARD_CLICK_DELAY_MAX = get_float("CARD_CLICK_DELAY_MAX", 0.0)

SKILL_VOCAB = [
    "figma", "adobe xd", "illustrator", "photoshop", "sketch", "framer",
    "wireframing", "wireframes", "prototyping", "prototype",
    "design systems", "design system", "component library", "design tokens",
    "auto-layout", "user research", "usability testing", "user testing",
    "user flows", "user journey", "information architecture",
    "interaction design", "visual design", "ui/ux", "product design",
    "saas", "mobile app", "web app", "responsive design",
    "accessibility", "a/b testing", "cro", "analytics", "html/css",
]

FACTOR_WEIGHTS = {
    "role_fit": 0.35,
    "tools_fit": 0.30,
    "level_fit": 0.20,
    "domain_fit": 0.15,
}

COMPANY_ALIASES = {
    "nextjobz": "european it institute",
    "bdjobs.com": "bdjobs",
    "mybdjobs": "bdjobs",
}

CHROME_CDP_URL = get_str("CHROME_CDP_URL", "http://localhost:9222")
