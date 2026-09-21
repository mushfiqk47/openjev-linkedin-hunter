import re
import unicodedata
import urllib.parse

def clean_display_name(n):
    n = unicodedata.normalize("NFKC", n or "").replace("\u200e", "").replace("\u200f", "").strip()
    n = re.sub(r'\s*•\s*(1st|2nd|3rd\+).*$', '', n)
    n = re.sub(r'[\s_]+', ' ', n).strip()
    return n

def norm_name(n):

    return clean_display_name(n).lower()

def profile_slug(url):

    m = re.search(r'/in/([^/?#]+)', url or "")
    return m.group(1).strip('/').lower() if m else ""
