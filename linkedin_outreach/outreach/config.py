import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")

def data_file(filename):

    full = os.path.abspath(os.path.join(DATA_DIR, filename))
    base = os.path.abspath(DATA_DIR)
    if os.path.commonpath([base, full]) != base:
        raise ValueError(f"path escapes data directory: {full}")
    return full

LEDGER_FILE = data_file("Complete.md")
REGISTRY_FILE = data_file("connections_registry.json")
PROGRESS_FILE = data_file("progress.txt")
TOTAL_FILE = data_file("total_connections.txt")
MESSAGE_FILE = data_file("message.py")

DEFAULT_PORTFOLIO_URL = "https://mushfiqkabiruix.vercel.app/"
DEFAULT_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"

BACKEND_SRC = os.path.abspath(os.path.join(ROOT_DIR, "..", "backend", "src"))

DEFAULT_SEMIF_ENABLED = 1
DEFAULT_SEMIF_BASE_URL = "http://localhost:1234/v1"
DEFAULT_SEMIF_MODEL = "qwen3.5-4b"
DEFAULT_MIN_RELEVANCE_SCORE = 50
DEFAULT_FILTER_LOW_RELEVANCE = 1

def load_env(env_path=None):

    targets = []
    if env_path is not None:
        targets.append(os.path.abspath(env_path))
    else:
        root_env = os.path.abspath(os.path.join(ROOT_DIR, ".env"))
        data_env = os.path.abspath(os.path.join(DATA_DIR, ".env"))
        if os.path.isfile(root_env):
            targets.append(root_env)
        if os.path.isfile(data_env) and data_env != root_env:
            targets.append(data_env)

    for path in targets:
        if not os.path.isfile(path):
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
            print(f"[WARN] Failed reading .env file at {path}: {e}")

def get_bool(name, default=False):

    val = os.environ.get(name)
    if val is None:
        return default
    val = str(val).strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default

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
