#!/usr/bin/env python3
"""Generate and safely rotate local prod-like credentials in ``.env``.

Copy ``.env.example`` to the ignored ``.env`` file first, then run:

    just generate-secrets

The command updates only supported secret keys, preserves non-secret settings
and comments, restricts ``.env`` to the current user, and never prints secret
values. Production receives the same environment-variable names from its
infrastructure-owned secret delivery, not from this local file.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


_ENV_PATH = Path(".env")
_GENERATION_COMMENT_PREFIX = "# Generated at "
_SAFE_NO_AMBIG = "".join(
    character
    for character in string.ascii_letters + string.digits
    if character not in "0O1lI5S2Z"
)


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
    "POSTGRES_PASSWORD": db_password,
    "INFERENCE_DB_PASSWORD": db_password,
    "REDIS_PASSWORD": redis_password,
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
        help="Generate POSTGRES_PASSWORD only.",
    )
    parser.add_argument(
        "--inference-db",
        action="store_true",
        help="Generate INFERENCE_DB_PASSWORD only.",
    )
    parser.add_argument(
        "--redis",
        action="store_true",
        help="Generate REDIS_PASSWORD only.",
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
        "postgres": "POSTGRES_PASSWORD",
        "inference_db": "INFERENCE_DB_PASSWORD",
        "redis": "REDIS_PASSWORD",
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


def _is_generation_comment(line: str) -> bool:
    return line.startswith(_GENERATION_COMMENT_PREFIX)


def _upsert_env_values(
    env_path: Path,
    values: dict[str, str],
    generated_at: str,
) -> None:
    """Replace ``values`` in an existing dotenv file without duplicating keys."""
    if not env_path.is_file():
        raise FileNotFoundError(env_path)

    replaced: set[str] = set()
    updated_lines: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines(keepends=True):
        key, separator, _ = line.partition("=")
        normalized_key = key.strip()
        if separator and normalized_key in values:
            if normalized_key not in replaced:
                if updated_lines and _is_generation_comment(updated_lines[-1]):
                    updated_lines[-1] = _generation_comment(generated_at)
                else:
                    updated_lines.append(_generation_comment(generated_at))
                updated_lines.append(f"{normalized_key}={values[normalized_key]}\n")
                replaced.add(normalized_key)
            elif updated_lines and _is_generation_comment(updated_lines[-1]):
                updated_lines.pop()
            continue
        updated_lines.append(line)

    if updated_lines and not updated_lines[-1].endswith("\n"):
        updated_lines[-1] += "\n"
    if replaced != set(values) and updated_lines:
        updated_lines.append("\n")
    for key, value in values.items():
        if key not in replaced:
            updated_lines.append(_generation_comment(generated_at))
            updated_lines.append(f"{key}={value}\n")

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=env_path.parent,
        prefix=f".{env_path.name}.",
        delete=False,
    ) as temporary_file:
        temporary_file.writelines(updated_lines)
        temporary_path = Path(temporary_file.name)

    try:
        temporary_path.chmod(0o600)
        os.replace(temporary_path, env_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    """Generate selected credentials and store them in the local ``.env`` file."""
    args = _parse_args()
    selected_keys = _selected_keys(args)
    values = {key: _SECRET_GENERATORS[key]() for key in selected_keys}
    generated_at = (
        datetime.now(UTC).isoformat(timespec="seconds").removesuffix("+00:00")
    )

    try:
        _upsert_env_values(_ENV_PATH, values, generated_at)
    except FileNotFoundError:
        raise SystemExit(
            "Missing .env. Copy .env.example to .env before generating local credentials."
        ) from None

    print(f"Updated {len(values)} local credential value(s) in {_ENV_PATH}.")


if __name__ == "__main__":
    main()
