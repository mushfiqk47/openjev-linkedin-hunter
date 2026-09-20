"""Configuration settings for LinkedIn Job Hunter."""

from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
OUTPUT_DIR = BASE_DIR / "output"
SEEN_JOBS_FILE = BASE_DIR / "seen_jobs.json"
CV_JSON_PATH = PROJECT_ROOT / "Mushfiq_Kabir_CV.json"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Search Defaults
DEFAULT_QUERIES = [
    "UI/UX Designer",
    "Product Designer",
    "Figma Designer",
    "UI Designer",
    "Design Systems Designer",
]

# LinkedIn URL Filters
# f_TPR: Time Posted Range (r86400 = past 24h, r604800 = past week)
RECENCY_FILTERS = {
    "24h": "r86400",
    "week": "r604800",
    "any": "",
}

# f_WT: Work Type (1 = On-site, 2 = Remote, 3 = Hybrid)
WORK_TYPES = {
    "remote": "2",
    "on_site": "1",
    "hybrid": "3",
    "all": "",
}

# LLM Configuration (Local LM Studio)
LLM_BASE_URL = "http://localhost:1234/v1"
LLM_MODEL = "qwen3.5-4b"
LLM_TIMEOUT = 45.0

# Matching Thresholds & Hunting Goals
DEFAULT_MIN_SCORE = 70       # out of 100
DEFAULT_MIN_MATCHES = 10     # Target minimum matched jobs to find
DEFAULT_MAX_PAGES_PER_QUERY = 2  # Max pages to paginate per query before rotating / feed fallback
DEFAULT_JOB_LIMIT = 50       # Safety maximum jobs to evaluate per run
FEED_MIN_SCORE = 65          # Min score threshold for feed opportunities
DAILY_EVALUATE_CAP = 120     # Safety cap: max LLM evaluations per run

# Human-like timing (2026 safety playbook: 2-4s jitter, avoid fixed sleeps)
HUMAN_DELAY_MIN = 2.0
HUMAN_DELAY_MAX = 4.5
CARD_CLICK_DELAY_MIN = 2.0
CARD_CLICK_DELAY_MAX = 3.2
SCROLL_BATCH = 4

# Skill vocabulary for real keyword extraction (BM25-style pre-filter + gaps)
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

# Factor weights for calibrated scoring (role > tools > level > domain)
FACTOR_WEIGHTS = {
    "role_fit": 0.35,
    "tools_fit": 0.30,
    "level_fit": 0.20,
    "domain_fit": 0.15,
}

# Company alias map for cross-poster dedup (poster -> canonical employer)
COMPANY_ALIASES = {
    "nextjobz": "european it institute",
    "bdjobs.com": "bdjobs",
    "mybdjobs": "bdjobs",
}

# Chrome & CDP Connection
# If Chrome is running with `google-chrome --remote-debugging-port=9222`, connect over CDP
CHROME_CDP_URL = "http://localhost:9222"
