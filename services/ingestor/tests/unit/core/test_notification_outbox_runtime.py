"""Unit proof for the ingestor-owned notification outbox runtime."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from services.ingestor import events
from services.ingestor.core.config import settings
from services.ingestor.notification_outbox_publisher import (
    OutboxPublishBatchResult,
    SessionFactory,
    notification_outbox_publisher_enabled,
    run_notification_outbox_publisher,
)


pytestmark = pytest.mark.unit


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args) -> None:
        return None


def _session_factory() -> _SessionContext:
    return _SessionContext()


def test_runtime_requires_all_three_opt_in_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "notification_delivery_mode", "broker")
    monkeypatch.setattr(settings, "broker_enabled", True)
    assert notification_outbox_publisher_enabled() is True

    monkeypatch.setattr(settings, "broker_enabled", False)
    assert notification_outbox_publisher_enabled() is False
    monkeypatch.setattr(settings, "broker_enabled", True)
    monkeypatch.setattr(settings, "notification_delivery_mode", "direct")
    assert notification_outbox_publisher_enabled() is False


async def test_strict_publish_adapter_requires_a_connected_producer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(events, "_producer", None)
    with pytest.raises(RuntimeError, match="not connected"):
        await events.publish_event_bytes("topic", b"value")

    send_and_wait = AsyncMock()
    monkeypatch.setattr(
        events,
        "_producer",
        SimpleNamespace(send_and_wait=send_and_wait),
    )
    await events.publish_event_bytes("topic", b"value")
    send_and_wait.assert_awaited_once_with("topic", value=b"value")


async def test_runtime_recovers_after_batch_failure_and_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = asyncio.Event()
    calls = 0

    async def batch(*_args, **_kwargs) -> OutboxPublishBatchResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        if calls == 3:
            completed.set()
        return OutboxPublishBatchResult(0, 0, 0, 0)

    monkeypatch.setattr(
        "services.ingestor.notification_outbox_publisher."
        "publish_notification_outbox_batch",
        batch,
    )
    task = asyncio.create_task(
        run_notification_outbox_publisher(
            cast("SessionFactory", _session_factory),
            AsyncMock(),
            poll_interval_seconds=0.001,
        )
    )
    try:
        await asyncio.wait_for(completed.wait(), timeout=1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls >= 3


async def test_runtime_propagates_cancellation_during_a_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def stalled_batch(*_args, **_kwargs) -> OutboxPublishBatchResult:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(
        "services.ingestor.notification_outbox_publisher."
        "publish_notification_outbox_batch",
        stalled_batch,
    )
    task = asyncio.create_task(
        run_notification_outbox_publisher(
            cast("SessionFactory", _session_factory),
            AsyncMock(),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
