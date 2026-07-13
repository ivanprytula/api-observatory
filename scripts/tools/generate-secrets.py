#!/usr/bin/env python3
"""
Generate high-entropy secrets for database, Redis, JWT, and other services.

Uses Python's ``secrets`` module (os.urandom) — cryptographically secure.
Prints secrets to stdout; copy the relevant line into your ``.env``.

Usage:
    uv run python scripts/tools/generate-secrets.py
    uv run python scripts/tools/generate-secrets.py --all
    uv run python scripts/tools/generate-secrets.py --jwt  # just JWT
"""

from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path


# ── alphabet definitions ──────────────────────────────────────────────────────

# Avoid visually ambiguous characters: 0O, 1lI, etc.
_SAFE_ALPHA = string.ascii_letters + string.digits
_SAFE_NO_VOWELS = "".join(c for c in _SAFE_ALPHA if c not in "aeiouAEIOU")
_SAFE_NO_AMBIG = "".join(c for c in _SAFE_ALPHA if c not in "0O1lI5S2Z")
_SPECIAL = "!@#$%^&*-_=+"
_STD_SPECIAL = string.punctuation

# ── generators ────────────────────────────────────────────────────────────────


def _passwd(alphabet: str, length: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


def db_password(length: int = 30) -> str:
    """PostgreSQL-compatible: alphanumeric + a few special chars."""
    return _passwd(_SAFE_NO_AMBIG + "!@#$-_", length)


def redis_password(length: int = 32) -> str:
    """Redis-safe: alphanumeric only (avoids shell/CLI escaping issues)."""
    return _passwd(_SAFE_NO_AMBIG, length)


def jwt_secret(bits: int = 512) -> str:
    """JWT signing secret as hex (safe for any config parser)."""
    byte_len = bits // 8
    return secrets.token_hex(byte_len)


def api_token(length: int = 48) -> str:
    """Bearer token: alphanumeric + underscore/dash."""
    return _passwd(_SAFE_NO_AMBIG + "_-", length)


def session_secret(length: int = 32) -> str:
    """Streamlit / Flask session key: high-entropy hex."""
    return secrets.token_hex(length)


def encryption_key(bits: int = 256) -> str:
    """AES / Fernet-compatible key as base64."""
    import base64

    return base64.b64encode(secrets.token_bytes(bits // 8)).decode()


def url_safe_token(length: int = 40) -> str:
    """URL-safe token (no chars that need encoding).
    Example: password-reset tokens, webhook secrets."""
    return secrets.token_urlsafe(length)


def _bits_for(length: int) -> int:
    """Approximate entropy bits for the default alphabet."""
    return length * 6  # rough: ~6 bits/char for mixed alpha


# ── output file ──────────────────────────────────────────────────────────────

# Overwritten (not appended) on every run so it never accumulates secrets from
# prior invocations. Must stay out of version control — see .gitignore.
_OUTPUT_ENV_PATH = Path(".generated.secrets.env")
_output_file_started = False


def _write_secret_line(env_var: str, value: str) -> None:
    global _output_file_started
    mode = "w" if not _output_file_started else "a"
    with _OUTPUT_ENV_PATH.open(mode, encoding="utf-8") as f:
        f.write(f"{env_var}={value}\n")
    _output_file_started = True
    _OUTPUT_ENV_PATH.chmod(0o600)


# ── display ───────────────────────────────────────────────────────────────────


_SECRET_SPECS: list[tuple[str, str, str, str]] = [
    (
        "REDIS_PASSWORD",
        redis_password(),
        "redis_password",
        "Redis requirepass (alphanumeric, 32 chars, ~192 bits)",
    ),
    (
        "POSTGRES_PASSWORD",
        db_password(),
        "db_password",
        "PostgreSQL password (30 chars, ~180 bits)",
    ),
    (
        "JWT_SECRET",
        jwt_secret(),
        "jwt_secret",
        "JWT signing secret (512-bit hex, 128 hex chars)",
    ),
    (
        "API_V1_BEARER_TOKEN",
        api_token(),
        "api_token",
        "Legacy bearer token (48 chars, ~280 bits)",
    ),
    (
        "INTERNAL_JWT_SECRET",
        jwt_secret(384),
        "jwt_internal",
        "Internal service JWT secret (384-bit hex, 96 chars)",
    ),
    (
        "DOCS_PASSWORD",
        db_password(24),
        "docs_password",
        "Docs basic-auth password (24 chars, ~144 bits)",
    ),
    (
        "SESSION_SECRET",
        session_secret(),
        "session_secret",
        "Streamlit / Flask session signing key (256-bit hex, 64 chars)",
    ),
    (
        "ENCRYPTION_KEY",
        encryption_key(),
        "encryption_key",
        "AES-256 key (base64, 44 chars)",
    ),
    (
        "WEBHOOK_SECRET",
        url_safe_token(),
        "webhook_secret",
        "Webhook / password-reset token (urlsafe, 40 chars, ~240 bits)",
    ),
]


def _print_secret(env_var: str, value: str, label: str, desc: str) -> None:
    print(f"# ── {label} ──")
    print(f"# {desc}")
    _write_secret_line(env_var, value)
    print(f"# Wrote {env_var} to {_OUTPUT_ENV_PATH}")
    print()


def _print_all() -> None:
    for env_var, value, label, desc in _SECRET_SPECS:
        _print_secret(env_var, value, label, desc)

    print(f"# Secrets were written to {_OUTPUT_ENV_PATH}")
    print("# Copy values from that file into your .env and .env.example")
    print("# Regenerate any time before deploying to a new environment.")
    print("# Store a backup in your password manager / vault.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate high-entropy secrets for .env configuration."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print all secrets (default behaviour)",
    )
    parser.add_argument(
        "--redis",
        action="store_true",
        help="Redis password only",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="PostgreSQL password only",
    )
    parser.add_argument(
        "--jwt",
        action="store_true",
        help="JWT secret only",
    )
    parser.add_argument(
        "--api-token",
        action="store_true",
        help="API bearer token only",
    )
    parser.add_argument(
        "--session",
        action="store_true",
        help="Session secret only",
    )
    parser.add_argument(
        "--encryption",
        action="store_true",
        help="Encryption key only",
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Webhook secret only",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    singles = {
        "redis": ("REDIS_PASSWORD", redis_password, "redis_password", "Redis password"),
        "db": ("POSTGRES_PASSWORD", db_password, "db_password", "PostgreSQL password"),
        "jwt": ("JWT_SECRET", jwt_secret, "jwt_secret", "JWT signing secret"),
        "api_token": (
            "API_V1_BEARER_TOKEN",
            api_token,
            "api_token",
            "API bearer token",
        ),
        "session": (
            "SESSION_SECRET",
            session_secret,
            "session_secret",
            "Session secret",
        ),
        "encryption": (
            "ENCRYPTION_KEY",
            encryption_key,
            "encryption_key",
            "Encryption key",
        ),
        "webhook": (
            "WEBHOOK_SECRET",
            url_safe_token,
            "webhook_secret",
            "Webhook secret",
        ),
    }

    requested = {k for k in singles if getattr(args, k)}
    if requested:
        for name in requested:
            env_var, gen, label, desc = singles[name]
            _print_secret(env_var, gen(), label, desc)
        return

    _print_all()


if __name__ == "__main__":
    main()
