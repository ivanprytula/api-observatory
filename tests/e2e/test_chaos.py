"""Chaos test wrapper — drives infra/scripts/chaos.sh and validates recovery.

Skip by default; enable with --run-chaos.

Requires:
  - docker compose up -d db cache broker ingestor dashboard
  - Run with: pytest tests/e2e/test_chaos.py --run-chaos
"""

from __future__ import annotations

import subprocess
import time

import pytest


BASE_URL = "http://localhost:8000"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-chaos",
        action="store_true",
        default=False,
        help="Run chaos tests that kill/restart Docker containers",
    )


@pytest.fixture(autouse=True)
def _require_chaos_flag(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-chaos"):
        pytest.skip("Chaos tests disabled (pass --run-chaos to enable)")


def _wait_for_readyz(timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["curl", "-sf", f"{BASE_URL}/readyz"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


@pytest.mark.parametrize("scenario", ["kill", "db", "kafka"])
def test_chaos_scenario(scenario: str) -> None:
    """Inject a chaos fault and verify the service recovers.

    Each scenario:
    1. Runs infra/scripts/chaos.sh <scenario> with CHAOS_DURATION=15
    2. Waits for /readyz to return 200 (up to 90s)
    """
    env = {**subprocess.os.environ, "CHAOS_DURATION": "15"}
    proc = subprocess.run(
        ["bash", "infra/scripts/chaos.sh", scenario],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"chaos.sh failed: {proc.stderr}"

    assert _wait_for_readyz(timeout=90), (
        f"Service did not recover after {scenario} chaos"
    )
