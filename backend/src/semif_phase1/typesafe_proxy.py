"""Local API-key proxy for the TypeSafe (Jev) System One endpoint.

TypeSafe expects one secret API key and its ``POST /v1/systemone`` contract is
not OpenAI-compatible, so client tooling cannot talk to it directly. This
stdlib-only proxy sits in front of it:

* generates a *local* key (``SEMIF_PROXY_API_KEY``) that clients use;
* keeps the real TypeSafe key (``TYPESAFE_API_KEY``) only in the env file;
* forwards every path, injecting the real key server-side, so the real key
  never leaves this machine's process environment;
* retries ``429``/``529`` with exponential backoff, as the API docs advise.

Nothing is sent anywhere except ``TYPESAFE_API_BASE``. Stdlib only, matching
the ``remote`` backend's constraints.

Quick start::

    # 1. paste the real TypeSafe key into .env (never on the command line)
    #    TYPESAFE_API_KEY=ts_live_...
    # 2. generate the local key clients will use
    semif-proxy --generate-key
    # 3. run the proxy
    semif-proxy
    # 4. point any client at the proxy instead of api.typesafe.ai
    curl -X POST http://127.0.0.1:4001/typesafe/v1/systemone \\
      -H "Authorization: Bearer $SEMIF_PROXY_API_KEY" \\
      -H 'Content-Type: application/json' \\
      -d '{"state": "...", "model": "jev-latest", "questions": {...}}'
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .remote import load_dotenv

#: Environment variables read for the proxy (see `.env.example`).
ENV_TYPESAFE_KEY = "TYPESAFE_API_KEY"
ENV_TYPESAFE_BASE = "TYPESAFE_API_BASE"
ENV_PROXY_KEY = "SEMIF_PROXY_API_KEY"
ENV_PROXY_HOST = "SEMIF_PROXY_HOST"
ENV_PROXY_PORT = "SEMIF_PROXY_PORT"
ENV_PROXY_TIMEOUT = "SEMIF_PROXY_TIMEOUT"

DEFAULT_TYPESAFE_BASE = "https://api.typesafe.ai"
DEFAULT_PROXY_HOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 4001
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.5
KEY_PREFIX = "sk-semif-"

#: Statuses the TypeSafe docs say to retry with exponential backoff.
RETRY_STATUSES = frozenset({429, 529})
#: Paths handled locally instead of being forwarded upstream.
HEALTH_PATHS = frozenset({"/", "/health", "/healthz"})


def generate_api_key() -> str:
    """Return a fresh local proxy key (``sk-semif-`` + 48 hex chars)."""
    return KEY_PREFIX + secrets.token_hex(24)


def mask_key(key: str | None) -> str:
    """Render a key for logs without exposing its secret half."""
    if not key:
        return "(unset)"
    return key if len(key) <= 12 else f"{key[:12]}...{key[-4:]}"


def normalize_path(path: str) -> str:
    """Strip a leading ``/typesafe`` prefix, mirroring LiteLLM's pass-through.

    ``/typesafe/v1/systemone`` -> ``/v1/systemone``; ``/v1/systemone`` is kept
    as-is so the proxy also works when a client points straight at it.
    Query strings are preserved.
    """
    raw = path or "/"
    if raw == "/typesafe":
        return "/"
    if raw.startswith("/typesafe/") or raw.startswith("/typesafe?"):
        raw = raw[len("/typesafe"):]
    return raw or "/"


def upsert_env(path: Path, updates: dict[str, str]) -> dict[str, str]:
    """Set ``KEY=VALUE`` lines in a dotenv file, preserving everything else.

    Rewrites only the keys named in ``updates`` (matching a leading ``export ``)
    and appends the rest. Creates the file and its parents when missing.
    Returns ``updates`` for convenience.
    """
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        body = stripped[len("export "):].lstrip() if stripped.startswith("export ") else stripped
        key = body.split("=", 1)[0].strip() if "=" in body else None
        if key in updates:
            result.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            result.append(line)
    for key, value in updates.items():
        if key not in seen:
            result.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(result).rstrip("\n") + "\n")
    return updates


@dataclass
class Upstream:
    """Minimal stdlib client for the TypeSafe evaluation endpoint."""

    base_url: str
    api_key: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    retries: int = DEFAULT_RETRIES
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    sleep: object = time.sleep

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("TypeSafe base URL must start with http:// or https://")
        if not self.api_key:
            raise ValueError("TypeSafe API key is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")
        if self.retries < 0:
            raise ValueError("Retries cannot be negative")

    def request(self, method: str, path: str, body: bytes = b"", content_type: str | None = None):
        """Forward one request; return ``(status, content_type, body)``.

        Retries ``429``/``529`` and transient network failures with exponential
        backoff. Upstream error bodies are passed through unchanged.
        """
        url = self.base_url + normalize_path(path)
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        attempt = 0
        while True:
            request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return (
                        response.status,
                        response.headers.get("Content-Type") or "application/json",
                        response.read(),
                    )
            except urllib.error.HTTPError as error:
                payload = error.read()
                if error.code in RETRY_STATUSES and attempt < self.retries:
                    self.sleep(self.backoff_seconds * (2 ** attempt))
                    attempt += 1
                    continue
                return error.code, error.headers.get("Content-Type") or "application/json", payload
            except urllib.error.URLError as error:
                if attempt < self.retries:
                    self.sleep(self.backoff_seconds * (2 ** attempt))
                    attempt += 1
                    continue
                raise RuntimeError(f"TypeSafe request to {url} failed after {attempt + 1} attempts: {error}") from error


def _health_payload(upstream: Upstream, proxy_key: str) -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "proxy": "semif-typesafe-proxy",
            "upstream": upstream.base_url,
            "upstream_key": mask_key(upstream.api_key),
            "proxy_key": mask_key(proxy_key),
            "models": ["jev-latest"],
            "endpoints": {
                "evaluate": "POST /typesafe/v1/systemone",
                "forwarded": "any path under /typesafe/ (and every other path)",
            },
        },
        indent=2,
    ).encode()


def make_handler(upstream: Upstream, proxy_key: str, auth_required: bool = True):
    """Build the request handler class bound to one upstream and key."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "SemIFTypeSafeProxy/1.0"

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _authorized(self) -> bool:
            if not auth_required:
                return True
            header = self.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "bearer" or not token:
                return False
            # Accept either the local proxy key or the real key, so pasting the
            # TypeSafe key into a client still works.
            return any(
                hmac.compare_digest(token, candidate)
                for candidate in (proxy_key, upstream.api_key)
                if candidate
            )

        def _forward(self) -> None:
            if self.path in HEALTH_PATHS:
                payload = _health_payload(upstream, proxy_key)
                self._send(200, payload, "application/json")
                return
            if not self._authorized():
                self._send(401, b'{"error": "invalid or missing API key"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, b'{"error": "invalid Content-Length"}', "application/json")
                return
            body = self.rfile.read(length) if length else b""
            try:
                status, content_type, payload = upstream.request(
                    self.command, self.path, body, self.headers.get("Content-Type")
                )
            except RuntimeError as error:
                self._send(502, json.dumps({"error": str(error)}).encode(), "application/json")
                return
            self._send(status, payload, content_type)

        def do_GET(self) -> None:
            self._forward()

        def do_HEAD(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def do_PUT(self) -> None:
            self._forward()

        def do_PATCH(self) -> None:
            self._forward()

        def do_DELETE(self) -> None:
            self._forward()

        def log_message(self, *args) -> None:  # keep the console quiet
            pass

    return Handler


def _resolve_port(value: str | None, fallback: int) -> int:
    if value is None or value == "":
        return fallback
    if not re.fullmatch(r"\d+", value):
        raise ValueError("Proxy port must be an integer")
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy the TypeSafe (Jev) System One API with a local API key.")
    parser.add_argument("--generate-key", action="store_true",
                        help="Generate and store a fresh SEMIF_PROXY_API_KEY, then exit.")
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Dotenv file with TYPESAFE_*/SEMIF_PROXY_* settings (default: ./.env).")
    parser.add_argument("--host", default=None, help=f"Bind host (default: {ENV_PROXY_HOST} or {DEFAULT_PROXY_HOST}).")
    parser.add_argument("--port", type=int, default=None, help=f"Bind port (default: {ENV_PROXY_PORT} or {DEFAULT_PROXY_PORT}).")
    parser.add_argument("--typesafe-base", default=None,
                        help=f"Upstream base URL (default: {ENV_TYPESAFE_BASE} or {DEFAULT_TYPESAFE_BASE}).")
    parser.add_argument("--typesafe-key", default=None,
                        help=f"Upstream API key (default: {ENV_TYPESAFE_KEY}). Prefer the env file.")
    parser.add_argument("--timeout", type=float, default=None,
                        help=f"Seconds per upstream request (default: {ENV_PROXY_TIMEOUT} or {DEFAULT_TIMEOUT_SECONDS}).")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help="Retries on 429/529 or network failure (default: %(default)s).")
    parser.add_argument("--no-auth", action="store_true",
                        help="Do not require a key from clients (local-only debugging; not recommended).")
    args = parser.parse_args()

    env_file = args.env_file or Path(".env")
    if args.env_file and not env_file.exists():
        parser.error(f"Env file not found: {env_file}")
    if env_file.exists():
        load_dotenv(env_file)

    if args.generate_key:
        key = generate_api_key()
        upsert_env(env_file, {ENV_PROXY_KEY: key})
        print(f"Generated local API key and wrote it to {env_file}:\n  {ENV_PROXY_KEY}={key}")
        return

    typesafe_key = args.typesafe_key or os.environ.get(ENV_TYPESAFE_KEY)
    if not typesafe_key:
        parser.error(
            f"Missing the real TypeSafe key. Paste it into {env_file} as\n"
            f"  {ENV_TYPESAFE_KEY}=ts_live_...\n"
            "then run `semif-proxy` again (it never leaves this machine)."
        )
    base_url = args.typesafe_base or os.environ.get(ENV_TYPESAFE_BASE) or DEFAULT_TYPESAFE_BASE
    try:
        timeout = args.timeout if args.timeout is not None else float(
            os.environ.get(ENV_PROXY_TIMEOUT) or DEFAULT_TIMEOUT_SECONDS
        )
        host = args.host or os.environ.get(ENV_PROXY_HOST) or DEFAULT_PROXY_HOST
        port = args.port if args.port is not None else _resolve_port(os.environ.get(ENV_PROXY_PORT), DEFAULT_PROXY_PORT)
    except ValueError as error:
        parser.error(str(error))
    if timeout <= 0:
        parser.error("--timeout must be positive")

    proxy_key = os.environ.get(ENV_PROXY_KEY) or ""
    if not proxy_key and not args.no_auth:
        proxy_key = generate_api_key()
        upsert_env(env_file, {ENV_PROXY_KEY: proxy_key})
        print(f"No {ENV_PROXY_KEY} found; generated one and wrote it to {env_file}.")

    upstream = Upstream(base_url=base_url, api_key=typesafe_key, timeout_seconds=timeout, retries=args.retries)
    handler = make_handler(upstream, proxy_key, auth_required=not args.no_auth)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"SemIf TypeSafe proxy on http://{host}:{port}\n"
        f"  upstream      {base_url}\n"
        f"  upstream key  {mask_key(typesafe_key)}\n"
        f"  client key    {mask_key(proxy_key) if not args.no_auth else '(auth disabled)'}\n"
        f"  evaluate      POST http://{host}:{port}/typesafe/v1/systemone\n"
        "Ctrl+C to stop."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
