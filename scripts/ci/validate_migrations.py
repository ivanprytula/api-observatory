#!/usr/bin/env python3
"""Validate Alembic migration contracts for a service."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


REQUIRED_MIGRATIONS = (
    "upgrade head",
    "current --check-heads",
    "downgrade -1",
    "upgrade head",
    "current --check-heads",
    "check",
)


def _run_alembic(
    args: Sequence[str], *, cwd: Path | None = None, database_url: str
) -> None:
    env = {
        "DATABASE_URL": database_url,
        "PYTHONPATH": str(cwd) if cwd else "",
    }
    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"alembic {' '.join(args)} failed with exit code {result.returncode}"
        )
    print(result.stdout.strip())


def validate(database_url: str, *, alembic_config: Path | None = None) -> None:
    cwd = alembic_config.parent if alembic_config else None

    for command in REQUIRED_MIGRATIONS:
        args = command.split()
        if alembic_config:
            args = ["-c", str(alembic_config), *args]
        _run_alembic(args, cwd=cwd, database_url=database_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Alembic migration contracts")
    parser.add_argument("database_url", help="SQLAlchemy database URL")
    parser.add_argument(
        "--alembic-config",
        type=Path,
        default=None,
        help="Path to alembic.ini (default: root alembic.ini)",
    )
    args = parser.parse_args(argv)

    try:
        validate(args.database_url, alembic_config=args.alembic_config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Migration validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
