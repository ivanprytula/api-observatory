"""Unit proof for Redpanda notification worker offset discipline."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiokafka import TopicPartition

from services.ingestor.notification_delivery_worker import (
    _decode_notification_request,
    run_notification_delivery_worker,
)


pytestmark = pytest.mark.unit


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


def _session_factory() -> _SessionContext:
    return _SessionContext()


async def test_worker_commits_each_record_only_after_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partition = TopicPartition("notifications.delivery.requests.v1", 0)
    record = SimpleNamespace(
        value=b'{"message_id":"incident:1:notification:1"}',
        offset=7,
        topic="notifications.delivery.requests.v1",
        partition=0,
    )
    consumer = SimpleNamespace(
        getmany=AsyncMock(return_value={partition: [record]}),
        commit=AsyncMock(),
    )
    persisted = asyncio.Event()

    async def process(_db: object, _value: bytes, _deliver: object) -> None:
        persisted.set()
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "services.ingestor.notification_delivery_worker.process_notification_record",
        process,
    )

    with pytest.raises(asyncio.CancelledError):
        await run_notification_delivery_worker(
            consumer,
            _session_factory,
            AsyncMock(),
        )

    assert persisted.is_set()
    consumer.commit.assert_not_awaited()


async def test_worker_commits_the_processed_record_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partition = TopicPartition("notifications.delivery.requests.v1", 0)
    record = SimpleNamespace(
        value=b'{"message_id":"incident:1:notification:1"}',
        offset=7,
        topic="notifications.delivery.requests.v1",
        partition=0,
    )
    consumer = SimpleNamespace(
        getmany=AsyncMock(return_value={partition: [record]}),
        commit=AsyncMock(),
    )

    async def process(_db: object, _value: bytes, _deliver: object) -> None:
        return None

    async def no_due_work(_db: object, _deliver: object, *, limit: int) -> None:
        assert limit == 10
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "services.ingestor.notification_delivery_worker.process_notification_record",
        process,
    )
    monkeypatch.setattr(
        "services.ingestor.notification_delivery_worker.deliver_due_notifications",
        no_due_work,
    )

    with pytest.raises(asyncio.CancelledError):
        await run_notification_delivery_worker(
            consumer,
            _session_factory,
            AsyncMock(),
        )

    consumer.commit.assert_awaited_once_with({partition: 8})


def test_decode_rejects_non_object_or_invalid_json() -> None:
    with pytest.raises(ValueError, match="empty"):
        _decode_notification_request(None)
    with pytest.raises(ValueError, match="valid JSON"):
        _decode_notification_request(b"not json")
    with pytest.raises(ValueError, match="JSON object"):
        _decode_notification_request(b"[]")
