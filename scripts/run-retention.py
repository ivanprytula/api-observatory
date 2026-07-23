#!/usr/bin/env python3
"""Run one bounded observation-retention batch outside the scheduler."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.ingestor.config import settings  # noqa: E402
from services.ingestor.database import AsyncSessionLocal, engine  # noqa: E402
from services.ingestor.jobs import archive_old_observations  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the explicit dry-run or destructive apply mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the next eligible batch without changing data (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Archive one batch; requires RETENTION_ENABLED=true.",
    )
    return parser.parse_args(argv)


async def run(apply: bool) -> dict[str, object]:
    """Execute one retention batch and always release database resources."""
    try:
        async with AsyncSessionLocal() as session:
            return await archive_old_observations(session, apply=apply)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command and return a shell-compatible status code."""
    args = parse_args(argv)
    if args.apply and not settings.retention_enabled:
        print(
            "Refusing --apply: set RETENTION_ENABLED=true after reviewing --dry-run.",
        )
        return 2

    result = asyncio.run(run(apply=args.apply))
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
