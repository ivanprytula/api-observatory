"""Unit tests for notification dispatching (Pillar 8)."""

from __future__ import annotations

from typing import Any

import pytest

import services.ingestor.notifications as notifications
from services.ingestor.config import settings


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, recorder: list[dict[str, Any]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        self._recorder.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse()


async def test_dispatch_notification_event_disabled_returns_skipped() -> None:
    old_enabled = settings.notifications_enabled
    settings.notifications_enabled = False
    try:
        result = await notifications.dispatch_notification_event(
            event="test_event",
            message="hello",
        )
        assert result["sent"] == 0
        assert result["failed"] == 0
        assert result["detail"] == "notifications disabled"
    finally:
        settings.notifications_enabled = old_enabled


async def test_dispatch_notification_event_slack_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        notifications.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(calls),
    )

    old_enabled = settings.notifications_enabled
    old_default_channels = settings.notification_default_channels
    old_slack_url = settings.notification_slack_webhook_url

    settings.notifications_enabled = True
    settings.notification_default_channels = "slack"
    settings.notification_slack_webhook_url = "https://slack.example/webhook"

    try:
        result = await notifications.dispatch_notification_event(
            event="background_task_failed",
            message="task failed",
            severity="critical",
            context={"task_id": "t1"},
        )
        assert result["sent"] == 1
        assert result["failed"] == 0
        assert calls
        assert calls[0]["url"] == "https://slack.example/webhook"
    finally:
        settings.notifications_enabled = old_enabled
        settings.notification_default_channels = old_default_channels
        settings.notification_slack_webhook_url = old_slack_url
