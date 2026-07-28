"""Regression tests for the local credential generator."""

from __future__ import annotations

import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


_SCRIPT = Path(__file__).parents[2] / "scripts/tools/generate-secrets.py"
_CORE_SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "INFERENCE_DB_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET",
    "API_V1_BEARER_TOKEN",
    "INTERNAL_JWT_SECRET",
)
_GENERATION_COMMENT = re.compile(
    r"^# Generated at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2} UTC "
    r"by scripts/tools/generate-secrets\.py$"
)


def _run_generator(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *arguments],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )


def _env_values(env_path: Path) -> dict[str, str]:
    return {
        key: value
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if "=" in line
        for key, value in [line.split("=", maxsplit=1)]
    }


def test_generator_requires_existing_env_file(tmp_path: Path) -> None:
    result = _run_generator(tmp_path)

    assert result.returncode == 1
    assert "Copy .env.example to .env" in result.stderr
    assert not (tmp_path / ".generated.secrets.env").exists()


def test_generator_adds_core_credentials_without_exposing_them(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# Generic local settings\nENVIRONMENT=development\n", encoding="utf-8"
    )

    result = _run_generator(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "Updated 6 local credential value(s) in .env.\n"
    values = _env_values(env_path)
    assert "# Generic local settings" in env_path.read_text(encoding="utf-8")
    assert values["ENVIRONMENT"] == "development"
    assert all(key in values for key in _CORE_SECRET_KEYS)
    assert values["POSTGRES_PASSWORD"] != values["INFERENCE_DB_PASSWORD"]
    assert values["POSTGRES_PASSWORD"].isalnum()
    assert values["INFERENCE_DB_PASSWORD"].isalnum()
    comments = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("# Generated")
    ]
    assert len(comments) == len(_CORE_SECRET_KEYS)
    assert all(_GENERATION_COMMENT.fullmatch(comment) for comment in comments)
    generated_values = [values[key] for key in _CORE_SECRET_KEYS]
    assert all(value not in result.stdout for value in generated_values)
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_generator_rotates_one_credential_without_duplicate_keys(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CACHE_ENABLED=false\nREDIS_PASSWORD=old-value\n", encoding="utf-8"
    )

    result = _run_generator(tmp_path, "--redis")

    assert result.returncode == 0
    values = _env_values(env_path)
    assert values["CACHE_ENABLED"] == "false"
    assert values["REDIS_PASSWORD"] != "old-value"
    assert env_path.read_text(encoding="utf-8").count("REDIS_PASSWORD=") == 1
    assert any(
        _GENERATION_COMMENT.fullmatch(line)
        for line in env_path.read_text(encoding="utf-8").splitlines()
    )


def test_generator_rejects_removed_unsupported_secret_flags(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ENVIRONMENT=development\n", encoding="utf-8")

    result = _run_generator(tmp_path, "--session")

    assert result.returncode == 2
    assert "unrecognized arguments: --session" in result.stderr
