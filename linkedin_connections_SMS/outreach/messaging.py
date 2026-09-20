"""The outreach message: rendered from the user-editable data/message.py.

Placeholders: {name}, {portfolio}, {headline}.
The greeting uses the full cleaned name — nothing else.
The template file is data the user owns — never edit engine code to change
the wording.
"""
import sys

from outreach.config import DATA_DIR, DEFAULT_PORTFOLIO_URL, get_str
from outreach.names import clean_display_name

DEFAULT_MESSAGE = (
    "Hi, {name}\n\n"
    "I hope all is well with you. I wanted to let you know I'm currently searching for a job or any project-based work. "
    "If you ever have something I could help with or know of any leads, it would genuinely mean a lot to me right now.\n"
    "To see my work: {portfolio}\n\n"
    "Thank you for taking the time to read this!"
)

_message_template_cache = []


def _load_message_template():
    """Load MESSAGE from the user-editable data/message.py."""
    if _message_template_cache:
        return _message_template_cache[0]
    template = None
    try:
        if DATA_DIR not in sys.path:
            sys.path.insert(0, DATA_DIR)
        import message as message_config
        template = getattr(message_config, "MESSAGE", None)
    except ImportError:
        template = None
    except Exception as e:
        print(f"[WARN] data/message.py could not be loaded ({e}); using built-in default template.")
        template = None
    _message_template_cache.append(template)
    return template


def message_template_source():
    """(template, origin) — origin is 'data/message.py' or 'built-in default'."""
    template = _load_message_template()
    return (template, "data/message.py") if template else (DEFAULT_MESSAGE, "built-in default")


def build_message(name, contact=None):
    """Render the outreach message. `contact` (optional dict) enables the
    {headline} placeholder."""
    portfolio = get_str("PORTFOLIO_URL", DEFAULT_PORTFOLIO_URL)
    headline = ""
    if isinstance(contact, dict):
        headline = clean_display_name(contact.get("headline", "") or "")
    fields = {
        "name": clean_display_name(name),
        "portfolio": portfolio,
        "headline": headline,
    }
    template = _load_message_template() or DEFAULT_MESSAGE
    try:
        return template.format(**fields)
    except Exception as e:
        print(f"[WARN] data/message.py template has a bad placeholder ({e}); using built-in default.")
        return DEFAULT_MESSAGE.format(**fields)
