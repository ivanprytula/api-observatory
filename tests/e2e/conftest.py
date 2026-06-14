"""E2E test configuration — custom CLI options."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-chaos",
        action="store_true",
        default=False,
        help="Run chaos tests that kill/restart Docker containers",
    )
