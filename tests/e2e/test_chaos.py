"""Chaos test wrapper — drives infra/scripts/chaos.sh and validates recovery."""

from __future__ import annotations

import subprocess
import time

import pytest


BASE_URL = "http://localhost:8000"


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
    """Inject a chaos fault and verify the service recovers."""
    env = {"CHAOS_DURATION": "15"}
    proc = subprocess.run(
        ["bash", "infra/scripts/chaos.sh", scenario],
        env={**subprocess.os.environ, **env},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"chaos.sh failed: {proc.stderr}"

    assert _wait_for_readyz(timeout=90), (
        f"Service did not recover after {scenario} chaos"
    )
