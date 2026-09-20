"""Name and profile-URL normalization: the dedup key machinery.

Two different people can share a name, never a profile slug. All comparison
keys are produced here so dedup rules live in exactly one place. The message
greeting uses the full cleaned name — no first-name guessing, no title
handling.
"""
import re
import unicodedata


def clean_display_name(n):
    n = unicodedata.normalize("NFKC", n or "").replace("\u200e", "").replace("\u200f", "").strip()
    n = re.sub(r'\s*•\s*(1st|2nd|3rd\+).*$', '', n)
    n = re.sub(r'[\s_]+', ' ', n).strip()
    return n


def norm_name(n):
    """Canonical dedup key for a name (cleaned + lowercased)."""
    return clean_display_name(n).lower()


def profile_slug(url):
    """Canonical dedup key for a profile URL: the first /in/ segment."""
    m = re.search(r'/in/([^/?#]+)', url or "")
    return m.group(1).strip('/').lower() if m else ""
