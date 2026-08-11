#!/usr/bin/env python3
"""Preflight workspace and service boundary checks for pre-commit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve()
CHECKS = [
    (
        "workspace manifests",
        [sys.executable, str(SCRIPT.parent / "check_workspace_manifests.py")],
    ),
    (
        "service boundaries",
        [sys.executable, str(SCRIPT.parent / "check_service_boundaries.py")],
    ),
]


def main() -> int:
    failures = 0
    for name, cmd in CHECKS:
        print(f"Checking {name}...")
        result = subprocess.run(
            cmd, cwd=SCRIPT.parent.parent, capture_output=True, text=True
        )
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            failures += 1
        else:
            print(result.stdout.strip())

    if failures:
        print(f"\n{failures} preflight check(s) failed.", file=sys.stderr)
        return 1
    print("\nAll preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
