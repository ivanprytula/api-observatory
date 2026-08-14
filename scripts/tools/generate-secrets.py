#!/usr/bin/env python3
"""Generate local credentials for the Docker development stack.

Copy ``.env.example`` to the ignored ``.env`` file first, then run ``just generate-secrets``.
By default this generates all supported local values:

* Ingestor and inference PostgreSQL passwords
* Redis password
* API bearer token
* public and internal JWT signing secrets

The generated values are written to ``.env.generated`` in the repository root. Copy
the secrets you want into your ``.env`` manually. The generated file is permissioned
as user-only (mode ``0600``); do not commit or share it. Production receives its
process-level environment variables from infrastructure-owned secret delivery, not
from this local file.
"""

from __future__ import annotations

import argparse
import secrets
import string
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


_SAFE_NO_AMBIG = "".join(
    character
    for character in string.ascii_letters + string.digits
    if character not in "0O1lI5S2Z"
)
_GENERATION_COMMENT_PREFIX = "# Generated at "


def _password(alphabet: str, length: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


def db_password(length: int = 30) -> str:
    """Return a database password safe for unescaped connection URLs."""
    return _password(_SAFE_NO_AMBIG, length)


def redis_password(length: int = 32) -> str:
    """Return a Redis-safe password without shell-sensitive characters."""
    return _password(_SAFE_NO_AMBIG, length)


def jwt_secret(bits: int = 512) -> str:
    """Return a hexadecimal JWT signing secret."""
    return secrets.token_hex(bits // 8)


def api_token(length: int = 48) -> str:
    """Return a bearer token safe for environment-variable parsing."""
    return _password(_SAFE_NO_AMBIG + "_-", length)


_SECRET_GENERATORS: dict[str, Callable[[], str]] = {
    "INGESTOR_DB_PASSWORD": db_password,
    "INFERENCE_DB_PASSWORD": db_password,
    "CACHE_PASSWORD": redis_password,
    "JWT_SECRET": jwt_secret,
    "API_V1_BEARER_TOKEN": api_token,
    "INTERNAL_JWT_SECRET": lambda: jwt_secret(384),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or rotate supported local credentials in .env."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate the full local prod-like credential set (the default).",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Generate INGESTOR_DB_PASSWORD only.",
    )
    parser.add_argument(
        "--inference-db",
        action="store_true",
        help="Generate INFERENCE_DB_PASSWORD only.",
    )
    parser.add_argument(
        "--redis",
        action="store_true",
        help="Generate CACHE_PASSWORD only.",
    )
    parser.add_argument(
        "--jwt",
        action="store_true",
        help="Generate JWT_SECRET only.",
    )
    parser.add_argument(
        "--api-token",
        action="store_true",
        help="Generate API_V1_BEARER_TOKEN only.",
    )
    parser.add_argument(
        "--internal-jwt",
        action="store_true",
        help="Generate INTERNAL_JWT_SECRET only.",
    )
    return parser.parse_args()


def _selected_keys(args: argparse.Namespace) -> tuple[str, ...]:
    flags = {
        "postgres": "INGESTOR_DB_PASSWORD",
        "inference_db": "INFERENCE_DB_PASSWORD",
        "redis": "CACHE_PASSWORD",
        "jwt": "JWT_SECRET",
        "api_token": "API_V1_BEARER_TOKEN",
        "internal_jwt": "INTERNAL_JWT_SECRET",
    }
    selected = tuple(env_var for flag, env_var in flags.items() if getattr(args, flag))
    if selected:
        return selected
    return tuple(_SECRET_GENERATORS)


def _generation_comment(generated_at: str) -> str:
    return (
        f"{_GENERATION_COMMENT_PREFIX}{generated_at} UTC "
        "by scripts/tools/generate-secrets.py\n"
    )


_GENERATED_PATH = Path(".env.generated")


def _write_generated(values: dict[str, str], generated_at: str) -> None:
    lines = [
        "# Generated secrets — copy the values you want into .env manually.\n",
        "# Do not commit this file.\n",
        _generation_comment(generated_at),
        "\n",
    ]
    for key, value in values.items():
        lines.append(f"{key}={value}\n")
    _GENERATED_PATH.write_text("".join(lines), encoding="utf-8")
    _GENERATED_PATH.chmod(0o600)


def main() -> None:
    """Generate selected credentials and write them to ``.env.generated``."""
    args = _parse_args()
    selected_keys = _selected_keys(args)
    values = {key: _SECRET_GENERATORS[key]() for key in selected_keys}
    generated_at = (
        datetime.now(UTC).isoformat(timespec="seconds").removesuffix("+00:00")
    )

    _write_generated(values, generated_at)

    print(f"Wrote {len(values)} generated secret(s) to {_GENERATED_PATH}.")


if __name__ == "__main__":
    main()
