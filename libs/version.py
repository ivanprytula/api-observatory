"""Version helpers for contracts and services.

This module uses a strict, fail-fast resolution strategy to avoid confusing
fallbacks when determining runtime provenance. Two sources are supported for
the *service* version (in order of precedence):

- `SERVICE_VERSION` environment variable (recommended; CI should set it)
- repo-level `VERSION` file at the repository root (convenient for local dev)

The canonical contracts version is read from `libs/contracts/VERSION` and
must exist. If any required source is missing, this module raises an
informative exception so failures are visible early.

Usage:
    from libs.version import get_version_payload
    payload = get_version_payload()
    # -> {"contracts": "0.1.3", "service": "1.2.3+gabc1234"}
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


CONTRACTS_VERSION_FILE = Path(__file__).parent / "contracts" / "VERSION"
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_VERSION_FILE = REPO_ROOT / "VERSION"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def get_contracts_version() -> str:
    """Return the canonical contracts version from `libs/contracts/VERSION`.

    Raises:
        RuntimeError: when the contracts VERSION file is missing or empty.
    """
    if not CONTRACTS_VERSION_FILE.exists():
        raise RuntimeError(
            f"Missing contracts VERSION file: {CONTRACTS_VERSION_FILE}. "
            "Run scripts/bump_contracts_version.py "
            "(or the check-contracts-version pre-commit hook) to create/update it."
        )
    v = _read_text(CONTRACTS_VERSION_FILE)
    if not v:
        raise RuntimeError(f"Empty contracts VERSION file: {CONTRACTS_VERSION_FILE}")
    return v


@lru_cache(maxsize=1)
def get_service_version() -> str:
    """Resolve the service version using a minimal, explicit strategy.

    Resolution order (strict):
    1. `SERVICE_VERSION` environment variable (preferred)
    2. `VERSION` file at repository root

    Raises:
        RuntimeError: when neither source provides a non-empty version string.
    """
    sv = os.getenv("SERVICE_VERSION")
    if sv:
        return sv.strip()

    if REPO_VERSION_FILE.exists():
        v = _read_text(REPO_VERSION_FILE)
        if v:
            return v
        raise RuntimeError(
            f"Repo-level VERSION file exists but is empty: {REPO_VERSION_FILE}"
        )

    raise RuntimeError(
        "SERVICE_VERSION not set and repo-level VERSION file not found. "
        "CI should set SERVICE_VERSION; for local dev create a VERSION file at repo root."
    )


def get_version_payload() -> dict[str, str]:
    """Return the payload object used by health/readiness endpoints.

    Example: {"contracts": "0.1.3", "service": "1.2.3+gabc1234"}
    """
    return {"contracts": get_contracts_version(), "service": get_service_version()}


__all__ = ["get_contracts_version", "get_service_version", "get_version_payload"]
