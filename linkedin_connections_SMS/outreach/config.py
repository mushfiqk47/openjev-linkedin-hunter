"""Central configuration: every file path and setting lives here.

All runtime data and user-editable files live in <repo>/data/. Nothing else
in the engine hardcodes a path — modules import their paths from here.
"""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")


def data_file(filename):
    """Validated path inside data/ — refuses anything that would escape it."""
    full = os.path.abspath(os.path.join(DATA_DIR, filename))
    base = os.path.abspath(DATA_DIR)
    if os.path.commonpath([base, full]) != base:
        raise ValueError(f"path escapes data directory: {full}")
    return full


CONTACTS_FILE = data_file("contacts.json")
LEDGER_FILE = data_file("Complete.md")
PROGRESS_FILE = data_file("progress.txt")
TOTAL_FILE = data_file("total_connections.txt")
ENV_FILE = data_file(".env")
MESSAGE_FILE = data_file("message.py")

# Seconds before a hung browser-use call is killed (protects every batch)
BU_TIMEOUT = int(os.environ.get("BU_TIMEOUT", "180"))

DEFAULT_PORTFOLIO_URL = "https://mushfiqkabiruix.vercel.app/"
DEFAULT_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"


def load_env(env_path=None):
    """Load data/.env (KEY=value per line, '#' comments, no quotes).
    Values already in the environment win — session overrides file."""
    if env_path is None:
        env_path = ENV_FILE
    if not os.path.isfile(env_path):
        return
    if os.path.commonpath([os.path.abspath(DATA_DIR), os.path.abspath(env_path)]) != os.path.abspath(DATA_DIR):
        print(f"[WARN] refusing to load .env outside the data directory: {env_path}")
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_str(name, default):
    return os.environ.get(name, default)
