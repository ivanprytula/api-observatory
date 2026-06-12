"""Integration tests for pubsub.py using a real Redis container.

These tests verify actual Redis pub/sub semantics (blocking channel reads,
message fan-out) that fakeredis does not fully emulate.  The ``real_cache``
fixture auto-skips if Docker is unavailable so the suite stays green in
environments without Docker.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import services.ingestor.pubsub as pubsub_module
from services.ingestor.pubsub import (
    PUBSUB_CHANNEL,
    publish_event,
    publish_observation_created,
    subscribe_events,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _wire_pubsub(real_cache):
    """Inject the real Cache client as the pub/sub connection for each test."""
    pubsub_module._pubsub_client = real_cache
    yield
    pubsub_module._pubsub_client = None


# ---------------------------------------------------------------------------
# publish_event
# ---------------------------------------------------------------------------


async def test_publish_event_writes_to_channel(real_cache) -> None:
    """publish_event() delivers a JSON message to PUBSUB_CHANNEL."""
    pubsub = real_cache.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)

    payload = {"value": 42}
    await publish_event("test.ping", payload)

    # Allow delivery time
    await asyncio.sleep(0.1)
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    await pubsub.unsubscribe(PUBSUB_CHANNEL)

    assert msg is not None
    data = json.loads(msg["data"])
    assert data["type"] == "test.ping"
    assert data["value"] == 42


async def test_publish_observation_created_includes_required_fields(real_cache) -> None:
    """publish_observation_created() envelope contains observation_id, source, and ts."""
    pubsub = real_cache.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)

    await publish_observation_created(observation_id=99, source="test.source")
    await asyncio.sleep(0.1)
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    await pubsub.unsubscribe(PUBSUB_CHANNEL)

    assert msg is not None
    data = json.loads(msg["data"])
    assert data["type"] == "observation.created"
    assert data["observation_id"] == 99
    assert data["source"] == "test.source"
    assert "ts" in data


# ---------------------------------------------------------------------------
# subscribe_events async generator
# ---------------------------------------------------------------------------


async def test_subscribe_events_yields_published_messages(real_cache) -> None:
    """subscribe_events() yields decoded dicts for each published message."""
    received: list[dict] = []

    async def _consumer() -> None:
        async for event in subscribe_events():
            received.append(event)
            if len(received) >= 2:
                break

    consumer_task = asyncio.create_task(_consumer())
    # Give subscriber time to attach
    await asyncio.sleep(0.1)

    await publish_event("observation.created", {"observation_id": 1, "source": "a"})
    await publish_event("observation.created", {"observation_id": 2, "source": "b"})

    try:
        await asyncio.wait_for(consumer_task, timeout=3.0)
    except TimeoutError:
        consumer_task.cancel()
        pytest.fail("subscribe_events() did not yield 2 messages within 3 s")

    assert len(received) == 2
    assert received[0]["observation_id"] == 1
    assert received[1]["observation_id"] == 2


async def test_publish_is_fail_open_when_client_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """publish_event() silently no-ops when the Cache client is not connected."""
    monkeypatch.setattr(pubsub_module, "_pubsub_client", None)
    # Should not raise
    await publish_event("observation.created", {"observation_id": 0, "source": "x"})
