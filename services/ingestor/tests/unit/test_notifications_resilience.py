"""Notification behavior remains fail-open through resilience controls."""

from __future__ import annotations

from unittest.mock import AsyncMock

from services.ingestor import notifications


async def test_notification_failure_is_returned_per_channel(
    monkeypatch,
) -> None:
    monkeypatch.setattr(notifications.settings, "notifications_enabled", True)
    monkeypatch.setattr(
        notifications,
        "_dispatch_to_channel_unprotected",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )

    result = await notifications.dispatch_notification_event(
        event="test_event",
        message="test message",
        channels=["webhook"],
    )

    assert result["sent"] == 0
    assert result["failed"] == 1
    assert result["results"][0]["status"] == "failed"
