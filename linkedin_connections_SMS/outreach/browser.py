"""The browser-use execution seam.

Everything that talks to Chrome goes through run_bu_script — tests mock this
one function to exercise entire harvest/send flows without a browser.
"""
import subprocess

from outreach.config import BU_TIMEOUT


def run_bu_script(script, timeout=None):
    """Run a script through the browser-use CLI. Never raises; errors come
    back via stderr so callers can decide how to handle them."""
    timeout = timeout or BU_TIMEOUT
    try:
        p = subprocess.run(
            ['browser-use'],
            input=script,
            text=True,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        return p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return "", f"TIMEOUT: browser-use did not finish within {timeout}s (is Chrome/CDP alive?)"
    except FileNotFoundError:
        return "", "ERROR: 'browser-use' CLI not found on PATH"
    except Exception as e:
        return "", f"ERROR running browser-use: {e}"


def parse_marker_line(out, marker):
    """Extract the first '<marker>{json}' line from browser-use output."""
    for line in out.splitlines():
        if line.startswith(marker):
            try:
                import json
                return json.loads(line[len(marker):].strip())
            except Exception:
                return None
    return None
