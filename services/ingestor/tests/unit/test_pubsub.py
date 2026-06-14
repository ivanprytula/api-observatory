"""Unit tests for pubsub.py — no Cache required.

Tests cover envelope structure, fail-open behavior, and the new
``publish_drift_event`` wrapper using monkeypatch to capture publish calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

import services.ingestor.pubsub as pubsub_module
from services.ingestor.pubsub import (
    publish_drift_event,
    publish_event,
    publish_job_progress,
    publish_observation_created,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def capture_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, Any]]]:
    """Replace publish_event with a no-op that observations (event_type, payload) tuples."""
    calls: list[tuple[str, dict[str, Any]]] = []

    async def _fake(event_type: str, payload: dict[str, Any]) -> None:
        calls.append((event_type, payload))

    monkeypatch.setattr(pubsub_module, "publish_event", _fake)
    return calls


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Inject a mock Cache client so publish_event runs its publish path."""
    mock = AsyncMock()
    mock.publish = AsyncMock()
    monkeypatch.setattr(pubsub_module, "_pubsub_client", mock)
    return mock


# ---------------------------------------------------------------------------
# publish_event
# ---------------------------------------------------------------------------


async def test_publish_event_no_ops_when_client_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pubsub_module, "_pubsub_client", None)
    # Should not raise
    await publish_event("any.event", {"x": 1})


async def test_publish_event_calls_cache_publish(fake_client: AsyncMock) -> None:
    await publish_event("test.event", {"key": "value"})
    fake_client.publish.assert_called_once()
    channel, raw = fake_client.publish.call_args.args
    assert channel == pubsub_module.PUBSUB_CHANNEL

    import json

    envelope = json.loads(raw)
    assert envelope["type"] == "test.event"
    assert envelope["key"] == "value"
    assert "ts" in envelope


async def test_publish_event_fail_open_on_cache_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """publish_event() swallows Cache errors so the write path is not blocked."""
    mock = AsyncMock()
    mock.publish = AsyncMock(side_effect=ConnectionError("cache down"))
    monkeypatch.setattr(pubsub_module, "_pubsub_client", mock)
    # Must not raise
    await publish_event("observation.created", {"observation_id": 1, "source": "s"})


# ---------------------------------------------------------------------------
# publish_observation_created
# ---------------------------------------------------------------------------


async def test_publish_observation_created_envelope(
    capture_publish: list[tuple[str, dict[str, Any]]],
) -> None:
    await publish_observation_created(observation_id=5, source="test.src")
    assert len(capture_publish) == 1
    event_type, payload = capture_publish[0]
    assert event_type == "observation.created"
    assert payload["observation_id"] == 5
    assert payload["source"] == "test.src"


# ---------------------------------------------------------------------------
# publish_job_progress
# ---------------------------------------------------------------------------


async def test_publish_job_progress_rounds_fraction(
    capture_publish: list[tuple[str, dict[str, Any]]],
) -> None:
    await publish_job_progress(
        job_id="j1", status="running", progress=0.333333, message="step 1"
    )
    event_type, payload = capture_publish[0]
    assert event_type == "job.progress"
    assert payload["progress"] == 0.3333


# ---------------------------------------------------------------------------
# publish_drift_event
# ---------------------------------------------------------------------------


async def test_publish_drift_event_envelope(
    capture_publish: list[tuple[str, dict[str, Any]]],
) -> None:
    await publish_drift_event(
        source_id=1,
        drift_event_id=42,
        event_type="breaking",
        severity="critical",
        compatibility_score=30.0,
    )
    assert len(capture_publish) == 1
    event_type, payload = capture_publish[0]
    assert event_type == "drift.detected"
    assert payload["source_id"] == 1
    assert payload["drift_event_id"] == 42
    assert payload["event_type"] == "breaking"
    assert payload["severity"] == "critical"
    assert payload["compatibility_score"] == 30.0


async def test_publish_drift_event_rounds_score(
    capture_publish: list[tuple[str, dict[str, Any]]],
) -> None:
    await publish_drift_event(
        source_id=2,
        drift_event_id=7,
        event_type="non_breaking",
        severity="low",
        compatibility_score=96.123456789,
    )
    _, payload = capture_publish[0]
    assert payload["compatibility_score"] == 96.1235


async def test_publish_drift_event_no_ops_when_client_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pubsub_module, "_pubsub_client", None)
    # Must not raise
    await publish_drift_event(
        source_id=1,
        drift_event_id=1,
        event_type="breaking",
        severity="high",
        compatibility_score=40.0,
    )
