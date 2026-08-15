#!/usr/bin/env python3
"""Create a user and optionally promote them to a non-viewer role.

Idempotent for registration (treats 409 as success). Promotion requires
``INTERNAL_JWT_SECRET`` to generate a short-lived internal token.

Usage:
    # Create a viewer (default):
    uv run python scripts/create_admin.py --username alice --password s3cret

    # Create and promote to admin in one shot:
    uv run python scripts/create_admin.py --username alice --password s3cret --role admin

    # Promote an existing user to operator:
    uv run python scripts/create_admin.py --username bob --role operator --promote-only
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

from libs.platform.auth import generate_internal_token


DEFAULT_INGESTOR_URL = "http://localhost:8000"
DEFAULT_EMAIL_DOMAIN = "example.com"


def _post(url: str, body: dict, headers: dict | None = None) -> httpx.Response:
    try:
        return httpx.post(url, json=body, headers=headers, timeout=10.0)
    except httpx.HTTPError as exc:
        print(f"Could not reach {url}: {exc}", file=sys.stderr)
        sys.exit(1)


def register_user(
    ingestor_url: str,
    username: str,
    email: str,
    password: str,
    role: str = "user",
) -> None:
    url = f"{ingestor_url.rstrip('/')}/api/v1/auth/register"
    resp = _post(
        url, {"username": username, "email": email, "password": password, "role": role}
    )
    if resp.status_code == httpx.codes.CREATED:
        print(f"Registered {username!r} (role={role!r}).")
    elif resp.status_code == httpx.codes.CONFLICT:
        print(f"{username!r} is already registered — nothing to do.")
    else:
        print(f"Registration failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)


def promote_user(
    ingestor_url: str,
    username: str,
    role: str,
    internal_jwt_secret: str | None = None,
) -> None:
    url = f"{ingestor_url.rstrip('/')}/api/v1/auth/users/{username}/role"
    headers: dict[str, str] = {}
    if internal_jwt_secret:
        headers["Authorization"] = (
            f"Bearer {generate_internal_token('bootstrap-script')}"
        )
    else:
        print(
            "Promotion requires INTERNAL_JWT_SECRET env var or --internal-jwt-secret.",
            file=sys.stderr,
        )
        sys.exit(2)

    resp = _post(url, {"role": role}, headers=headers)
    if resp.status_code == httpx.codes.OK:
        print(f"Promoted {username!r} to {role!r}.")
    else:
        print(f"Promotion failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or promote a user.")
    parser.add_argument(
        "--ingestor-url", default=os.environ.get("INGESTOR_URL", DEFAULT_INGESTOR_URL)
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument("--role", default="user")
    parser.add_argument(
        "--promote-only",
        action="store_true",
        help="Skip registration, promote existing user only.",
    )
    parser.add_argument(
        "--internal-jwt-secret",
        default=os.environ.get("INTERNAL_JWT_SECRET"),
        help=(
            "INTERNAL_JWT_SECRET for generating a short-lived internal token "
            "to call the promotion endpoint."
        ),
    )
    args = parser.parse_args(argv)

    email = args.email or f"{args.username}@{DEFAULT_EMAIL_DOMAIN}"

    if not args.promote_only:
        register_user(args.ingestor_url, args.username, email, args.password, "viewer")

    if args.role != "viewer":
        promote_user(
            args.ingestor_url,
            args.username,
            args.role,
            internal_jwt_secret=args.internal_jwt_secret,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
