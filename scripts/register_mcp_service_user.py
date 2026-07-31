#!/usr/bin/env python3
"""Register the `mcp-service` account the MCP server (services/mcp/) logs in
as. Idempotent — safe to re-run; treats a 409 (username/email already taken)
as success.

Usage:
    (
        set -a
        source services/mcp/.env
        set +a
        uv run python scripts/register_mcp_service_user.py
    )

Requires the ingestor to be running and reachable at $INGESTOR_URL
(default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx


DEFAULT_INGESTOR_URL = "http://localhost:8000"
DEFAULT_USERNAME = "mcp-service"
# UserCreate.email is a strict EmailStr (email-validator) — reserved/special-use
# TLDs like .local/.test/.invalid are rejected, so a placeholder domain must be
# a real one (matches bruno/auth/1-register.bru's own admin@example.com).
DEFAULT_EMAIL_DOMAIN = "example.com"
DEFAULT_ROLE = "writer"  # minimum role satisfying resume_agent_run's jwt_role_guard


def register(
    ingestor_url: str, username: str, email: str, password: str, role: str
) -> int:
    url = f"{ingestor_url.rstrip('/')}/api/v1/auth/register"
    body = {
        "username": username,
        "email": email,
        "password": password,
        "role": role,
    }
    try:
        response = httpx.post(url, json=body, timeout=10.0)
    except httpx.HTTPError as exc:
        print(f"Could not reach {url}: {exc}", file=sys.stderr)
        return 1

    if response.status_code == httpx.codes.CREATED:
        print(f"Registered {username!r} (role={role!r}).")
        return 0
    if response.status_code == httpx.codes.CONFLICT:
        print(f"{username!r} is already registered — nothing to do.")
        return 0

    print(
        f"Registration failed: {response.status_code} {response.text}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ingestor-url",
        default=os.environ.get("INGESTOR_URL", DEFAULT_INGESTOR_URL),
    )
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument(
        "--email",
        default=None,
        help=f"Defaults to {{username}}@{DEFAULT_EMAIL_DOMAIN} (must pass strict "
        "email validation — reserved TLDs like .local/.test/.invalid are rejected).",
    )
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument(
        "--password",
        default=os.environ.get("MCP_SERVICE_PASSWORD"),
        help="Prefer the MCP_SERVICE_PASSWORD env var over this flag.",
    )
    args = parser.parse_args(argv)

    if not args.password:
        print(
            "Password required: set MCP_SERVICE_PASSWORD or pass --password.",
            file=sys.stderr,
        )
        return 2

    email = args.email or f"{args.username}@{DEFAULT_EMAIL_DOMAIN}"
    return register(args.ingestor_url, args.username, email, args.password, args.role)


if __name__ == "__main__":
    raise SystemExit(main())
