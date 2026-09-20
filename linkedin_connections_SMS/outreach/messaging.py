"""The outreach message: rendered from the user-editable data/message.py.

Placeholders: {name}, {portfolio}, {headline}.
The greeting uses the full cleaned name — nothing else.
The template file is data the user owns — never edit engine code to change
the wording.
"""
import importlib.util
import os
import sys

from outreach.config import DEFAULT_PORTFOLIO_URL, MESSAGE_FILE, get_str
from outreach.names import clean_display_name

DEFAULT_MESSAGE = (
    "Hi, {name}\n\n"
    "I hope all is well with you. I wanted to let you know I'm currently searching for a job or any project-based work. "
    "If you ever have something I could help with or know of any leads, it would genuinely mean a lot to me right now.\n"
    "To see my work: {portfolio}\n\n"
    "Thank you for taking the time to read this!"
)

_message_template_cache = []
_templates_module_cache = []


def _get_message_module():
    """Load the user-editable data/message.py module dynamically."""
    if _templates_module_cache:
        return _templates_module_cache[0]
    mod = None
    try:
        if os.path.isfile(MESSAGE_FILE):
            spec = importlib.util.spec_from_file_location("data_message_module", MESSAGE_FILE)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
    except Exception as e:
        print(f"[WARN] data/message.py could not be loaded ({e}); using built-in default template.")
        mod = None
    _templates_module_cache.append(mod)
    return mod


def get_template_for_archetype(archetype=None):
    """Retrieve the template corresponding to archetype (recruiter, founder, peer, general)."""
    if _message_template_cache:
        return _message_template_cache[0], "custom override"
    mod = _get_message_module()
    if mod is not None:
        if archetype == "recruiter" and hasattr(mod, "MESSAGE_RECRUITER"):
            return getattr(mod, "MESSAGE_RECRUITER"), "data/message.py (recruiter)"
        elif archetype == "founder" and hasattr(mod, "MESSAGE_FOUNDER"):
            return getattr(mod, "MESSAGE_FOUNDER"), "data/message.py (founder)"
        elif archetype == "peer" and hasattr(mod, "MESSAGE_PEER"):
            return getattr(mod, "MESSAGE_PEER"), "data/message.py (peer)"
        elif hasattr(mod, "MESSAGE") and mod.MESSAGE:
            return getattr(mod, "MESSAGE"), "data/message.py (general)"
    return DEFAULT_MESSAGE, "built-in default"


def message_template_source(archetype=None):
    """(template, origin) — origin is 'data/message.py' or 'built-in default'."""
    return get_template_for_archetype(archetype)


def build_message(name, contact=None):
    """Render the outreach message. `contact` (optional dict) enables the
    {headline}, {archetype} placeholders, and chooses the optimal template."""
    portfolio = get_str("PORTFOLIO_URL", DEFAULT_PORTFOLIO_URL)
    headline = ""
    archetype = "general"
    if isinstance(contact, dict):
        headline = clean_display_name(contact.get("headline", "") or "")
        archetype = contact.get("archetype", "general") or "general"
    fields = {
        "name": clean_display_name(name),
        "portfolio": portfolio,
        "headline": headline,
        "archetype": archetype,
    }
    template, _ = get_template_for_archetype(archetype)
    try:
        return template.format(**fields)
    except Exception as e:
        print(f"[WARN] data/message.py template for {archetype} had a bad placeholder ({e}); using built-in default.")
        return DEFAULT_MESSAGE.format(**fields)
