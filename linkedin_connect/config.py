import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_env(env_path: Path | str | None = None):
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(BASE_DIR / ".env")
    candidates.append(PROJECT_ROOT / ".env")

    for p in candidates:
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass
            break

load_env()

def get_str(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()

def get_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default

def get_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default

def get_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")

DEFAULT_QUERIES = [
    "Head of Design",
    "Creative Director",
    "Technical Recruiter",
    "Startup Founder",
    "Product Design Manager",
    "Design Lead",
    "Talent Partner",
    "VP Design",
    "Co-Founder CEO",
]

TARGET_QUERIES = [
    q.strip()
    for q in get_str("TARGET_QUERIES", ",".join(DEFAULT_QUERIES)).split(",")
    if q.strip()
]

DAILY_CONNECT_LIMIT = get_int("DAILY_CONNECT_LIMIT", 15)
MIN_CONNECT_SCORE = get_int("MIN_CONNECT_SCORE", 75)
MAX_PAGES_PER_QUERY = get_int("MAX_PAGES_PER_QUERY", 3)
CONNECT_DELAY = get_float("CONNECT_DELAY", 3.0)
SCROLL_DELAY = get_float("SCROLL_DELAY", 0.5)
DRY_RUN = get_bool("DRY_RUN", False)

CHROME_CDP_URL = get_str("CHROME_CDP_URL", "http://localhost:9222")
LLM_BASE_URL = get_str("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = get_str("LLM_MODEL", "qwen3.5-4b")
