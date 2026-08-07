"""Chaos test wrapper for the disposable PostgreSQL blackout lab.

Skip by default; enable with --run-chaos.

Requires:
  - a ready local core stack
  - Run with: just --justfile just/labs.just lab-chaos
"""

from __future__ import annotations

import subprocess

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.chaos]


@pytest.fixture(autouse=True)
def _require_chaos_flag(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-chaos"):
        pytest.skip("Chaos tests disabled (pass --run-chaos to enable)")


def test_postgresql_blackout() -> None:
    """Inject a chaos fault and verify the service recovers.

    The shell exercise asserts readiness degradation and recovery itself.
    """
    env = {**subprocess.os.environ, "CHAOS_DURATION": "15"}
    proc = subprocess.run(
        ["bash", "infra/scripts/chaos.sh", "db"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"chaos.sh failed: {proc.stderr}"
    assert "Readiness degraded while PostgreSQL was unavailable" in proc.stdout
