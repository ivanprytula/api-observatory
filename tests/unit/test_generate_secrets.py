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
    "INGESTOR_DB_PASSWORD",
    "INFERENCE_DB_PASSWORD",
    "CACHE_PASSWORD",
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


def _generated_values(tmp_path: Path) -> dict[str, str]:
    generated = tmp_path / ".env.generated"
    return {
        key: value
        for line in generated.read_text(encoding="utf-8").splitlines()
        if "=" in line
        for key, value in [line.split("=", maxsplit=1)]
    }


def test_generator_creates_generated_file_without_env(tmp_path: Path) -> None:
    result = _run_generator(tmp_path)

    assert result.returncode == 0
    generated = tmp_path / ".env.generated"
    assert generated.exists()
    assert stat.S_IMODE(generated.stat().st_mode) == 0o600
    assert not (tmp_path / ".env").exists()


def test_generator_does_not_touch_existing_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# Generic local settings\nENVIRONMENT=development\n", encoding="utf-8"
    )

    result = _run_generator(tmp_path)

    assert result.returncode == 0
    assert env_path.read_text(encoding="utf-8") == (
        "# Generic local settings\nENVIRONMENT=development\n"
    )
    values = _generated_values(tmp_path)
    assert all(key in values for key in _CORE_SECRET_KEYS)
    assert values["INGESTOR_DB_PASSWORD"] != values["INFERENCE_DB_PASSWORD"]
    assert values["INGESTOR_DB_PASSWORD"].isalnum()
    assert values["INFERENCE_DB_PASSWORD"].isalnum()
    comments = [
        line
        for line in (tmp_path / ".env.generated")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("# Generated")
        and "UTC by scripts/tools/generate-secrets.py" in line
    ]
    assert len(comments) == 1
    assert all(_GENERATION_COMMENT.fullmatch(comment) for comment in comments)
    generated_values = [values[key] for key in _CORE_SECRET_KEYS]
    assert all(value not in result.stdout for value in generated_values)


def test_generator_writes_selected_key_to_generated_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("CACHE_ENABLED=false\n", encoding="utf-8")

    result = _run_generator(tmp_path, "--redis")

    assert result.returncode == 0
    assert env_path.read_text(encoding="utf-8") == "CACHE_ENABLED=false\n"
    values = _generated_values(tmp_path)
    assert values["CACHE_PASSWORD"] != ""
    assert (tmp_path / ".env.generated").read_text(encoding="utf-8").count(
        "CACHE_PASSWORD="
    ) == 1


def test_generator_rejects_unsupported_secret_flags(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ENVIRONMENT=development\n", encoding="utf-8")

    result = _run_generator(tmp_path, "--session")

    assert result.returncode == 2
    assert "unrecognized arguments: --session" in result.stderr


def test_generator_uses_short_names_only(tmp_path: Path) -> None:
    result = _run_generator(tmp_path)

    assert result.returncode == 0
    values = _generated_values(tmp_path)
    assert all(key in values for key in _CORE_SECRET_KEYS)
    assert not any(key.startswith("API_OBS_") for key in values)
    assert not any(key in {"POSTGRES_PASSWORD", "REDIS_PASSWORD"} for key in values)


def test_generator_removed_settings_not_in_generated(tmp_path: Path) -> None:
    result = _run_generator(tmp_path, "--inference-db")

    assert result.returncode == 0
    values = _generated_values(tmp_path)
    assert "INFERENCE_ENABLED" not in values
