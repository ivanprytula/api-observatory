"""Unit tests for Sentry setup logic."""

from __future__ import annotations

from typing import Any

import pytest

from services.ingestor.config import settings
from services.ingestor.core import sentry as sentry_module


def test_setup_sentry_returns_false_when_disabled() -> None:
    old_enabled = settings.sentry_enabled
    settings.sentry_enabled = False
    try:
        assert sentry_module.setup_sentry() is False
    finally:
        settings.sentry_enabled = old_enabled


def test_setup_sentry_returns_false_without_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_enabled = settings.sentry_enabled
    old_dsn = settings.sentry_dsn
    old_available = sentry_module.SENTRY_SDK_AVAILABLE
    settings.sentry_enabled = True
    settings.sentry_dsn = None

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_module, "SENTRY_SDK_AVAILABLE", True)
    monkeypatch.setattr(
        sentry_module, "_sentry_init", lambda **kwargs: calls.append(kwargs)
    )

    try:
        assert sentry_module.setup_sentry() is False
        assert calls == []
    finally:
        settings.sentry_enabled = old_enabled
        settings.sentry_dsn = old_dsn
        sentry_module.SENTRY_SDK_AVAILABLE = old_available


def test_setup_sentry_initializes_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    old_enabled = settings.sentry_enabled
    old_dsn = settings.sentry_dsn
    old_traces = settings.sentry_traces_sample_rate
    old_available = sentry_module.SENTRY_SDK_AVAILABLE

    settings.sentry_enabled = True
    settings.sentry_dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
    settings.sentry_traces_sample_rate = 0.2

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_module, "SENTRY_SDK_AVAILABLE", True)
    monkeypatch.setattr(
        sentry_module, "_sentry_init", lambda **kwargs: calls.append(kwargs)
    )

    try:
        assert sentry_module.setup_sentry() is True
        assert len(calls) == 1
        assert calls[0]["dsn"] == settings.sentry_dsn
        assert calls[0]["traces_sample_rate"] == 0.2
    finally:
        settings.sentry_enabled = old_enabled
        settings.sentry_dsn = old_dsn
        settings.sentry_traces_sample_rate = old_traces
        sentry_module.SENTRY_SDK_AVAILABLE = old_available


def test_setup_sentry_returns_false_when_sdk_missing() -> None:
    old_enabled = settings.sentry_enabled
    old_dsn = settings.sentry_dsn
    old_available = sentry_module.SENTRY_SDK_AVAILABLE

    settings.sentry_enabled = True
    settings.sentry_dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
    sentry_module.SENTRY_SDK_AVAILABLE = False

    try:
        assert sentry_module.setup_sentry() is False
    finally:
        settings.sentry_enabled = old_enabled
        settings.sentry_dsn = old_dsn
        sentry_module.SENTRY_SDK_AVAILABLE = old_available
