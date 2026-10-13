"""Read-only HTTPS staging acceptance probe.

Does not authenticate, upload documents, mutate staging or print secrets.
A successful probe covers reachability and public response headers ONLY.
"""
from __future__ import annotations

import argparse
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def validate_target(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("Use the bare public HTTPS staging origin without credentials or paths")
    return f"https://{parsed.netloc.lower()}"


def assess(status: int, headers: dict[str, str], *, login: bool) -> list[str]:
    normalized = {str(k).lower(): str(v).strip().lower() for k, v in headers.items()}
    failures = []
    if status != (200 if login else 401):
        failures.append("Unexpected login/session HTTP status")
    if not normalized.get("strict-transport-security", "").startswith("max-age="):
        failures.append("Missing HTTPS HSTS")
    if normalized.get("x-content-type-options") != "nosniff":
        failures.append("Missing nosniff header")
    if login and "html" not in normalized.get("content-type", ""):
        failures.append("Login page did not return HTML")
    if not login and "no-store" not in normalized.get("cache-control", ""):
        failures.append("Unauthenticated session response must not be cached")
    return failures


def run(origin: str, *, timeout: int = 12) -> dict[str, str]:
    base = validate_target(origin)
    context = ssl.create_default_context()
    for path, login in (("/login", True), ("/api/session/me", False)):
        request = Request(base + path, headers={"User-Agent": "WorkMate-staging-health/1.0"})
        try:
            with urlopen(request, timeout=timeout, context=context) as response:
                status = response.status
                headers = dict(response.headers.items())
                final = response.geturl()
        except HTTPError as error:
            status, headers, final = error.code, dict(error.headers.items()), error.geturl()
            error.close()
        if urlsplit(final).scheme != "https" or urlsplit(final).netloc.lower() != urlsplit(base).netloc.lower():
            raise RuntimeError("Public endpoint redirected off the expected HTTPS host")
        failures = assess(status, headers, login=login)
        if failures:
            raise RuntimeError("Staging acceptance failed on " + path + ": " + "; ".join(failures))
    return {"status": "pass", "checks": "HTTPS login headers and unauthorized session response"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Public TLS/login read-only WorkMate staging check")
    parser.add_argument("--origin", required=True, help="Bare HTTPS staging origin")
    args = parser.parse_args()
    print(run(args.origin))
