from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.ingestor.notifications as notifications
from services.ingestor.config import settings
from services.ingestor.constants import (
    NOTIFICATION_SEVERITY_CRITICAL,
    NOTIFICATION_SEVERITY_INFO,
    NOTIFICATION_SEVERITY_WARNING,
)
from services.ingestor.models import NotificationDelivery


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._calls = calls

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
        self._calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse()


# ---------------------------------------------------------------------------
# _parse_channels
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseChannels:
    def test_valid_channels_parsed(self) -> None:
        result = notifications._parse_channels("slack,telegram,webhook,email")
        assert result == ["slack", "telegram", "webhook", "email"]

    def test_invalid_channels_filtered(self) -> None:
        result = notifications._parse_channels("slack,invalid,sms,email")
        assert result == ["slack", "email"]

    def test_empty_string_returns_empty(self) -> None:
        assert notifications._parse_channels("") == []

    def test_whitespace_and_case_normalized(self) -> None:
        result = notifications._parse_channels(" SLACK , Telegram ")
        assert result == ["slack", "telegram"]

    def test_duplicates_preserved_in_order(self) -> None:
        result = notifications._parse_channels("slack,slack")
        assert result == ["slack", "slack"]

    def test_only_invalid_returns_empty(self) -> None:
        assert notifications._parse_channels("sms,fax") == []


# ---------------------------------------------------------------------------
# configured_notification_channels
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfiguredChannels:
    def test_returns_parsed_channels(self) -> None:
        with patch.object(
            notifications.settings, "notification_default_channels", "slack,email"
        ):
            assert notifications.configured_notification_channels() == [
                "slack",
                "email",
            ]

    def test_empty_when_not_set(self) -> None:
        with patch.object(notifications.settings, "notification_default_channels", ""):
            assert notifications.configured_notification_channels() == []


# ---------------------------------------------------------------------------
# _email_recipients
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmailRecipients:
    def test_parses_recipients(self) -> None:
        with patch.object(
            notifications.settings, "notification_email_to", "a@x.com, b@x.com"
        ):
            assert notifications._email_recipients() == ["a@x.com", "b@x.com"]

    def test_empty_when_not_set(self) -> None:
        with patch.object(notifications.settings, "notification_email_to", ""):
            assert notifications._email_recipients() == []

    def test_filters_empty_entries(self) -> None:
        with patch.object(
            notifications.settings, "notification_email_to", "  , a@x.com, ,"
        ):
            assert notifications._email_recipients() == ["a@x.com"]


# ---------------------------------------------------------------------------
# _dispatch_to_channel_unprotected
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchToChannelUnprotected:
    async def test_slack_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notifications, "_send_slack", AsyncMock(return_value="slack delivered")
        )
        result = await notifications._dispatch_to_channel_unprotected(
            channel="slack", event="e", message="m", severity="warning", context={}
        )
        assert result == "slack delivered"

    async def test_telegram_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notifications,
            "_send_telegram",
            AsyncMock(return_value="telegram delivered"),
        )
        result = await notifications._dispatch_to_channel_unprotected(
            channel="telegram", event="e", message="m", severity="warning", context={}
        )
        assert result == "telegram delivered"

    async def test_webhook_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notifications, "_send_webhook", AsyncMock(return_value="webhook delivered")
        )
        result = await notifications._dispatch_to_channel_unprotected(
            channel="webhook", event="e", message="m", severity="warning", context={}
        )
        assert result == "webhook delivered"

    async def test_email_dispatches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notifications, "_send_email", AsyncMock(return_value="email delivered")
        )
        result = await notifications._dispatch_to_channel_unprotected(
            channel="email", event="e", message="m", severity="warning", context={}
        )
        assert result == "email delivered"

    async def test_unknown_channel_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported channel"):
            await notifications._dispatch_to_channel_unprotected(
                channel="sms", event="e", message="m", severity="warning", context={}
            )


# ---------------------------------------------------------------------------
# _send_slack
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendSlack:
    async def test_slack_success_with_critical_color(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        with patch.object(
            notifications.settings, "notification_slack_webhook_url", "https://hook"
        ):
            result = await notifications._send_slack(
                "incident.opened",
                "host down",
                NOTIFICATION_SEVERITY_CRITICAL,
                {"src": "api"},
            )
        assert result == "slack webhook delivered"
        payload = calls[0]["json"]
        assert payload["attachments"][0]["color"] == "danger"
        assert "CRITICAL" in payload["attachments"][0]["title"]

    async def test_slack_success_with_warning_color(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        with patch.object(
            notifications.settings, "notification_slack_webhook_url", "https://hook"
        ):
            await notifications._send_slack(
                "event", "msg", NOTIFICATION_SEVERITY_WARNING, context={}
            )
        assert calls[0]["json"]["attachments"][0]["color"] == "warning"

    async def test_slack_success_with_good_color(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        with patch.object(
            notifications.settings, "notification_slack_webhook_url", "https://hook"
        ):
            await notifications._send_slack(
                "event", "msg", NOTIFICATION_SEVERITY_INFO, context={}
            )
        assert calls[0]["json"]["attachments"][0]["color"] == "good"

    async def test_slack_raises_when_unconfigured(self) -> None:
        with (
            patch.object(notifications.settings, "notification_slack_webhook_url", ""),
            pytest.raises(ValueError, match="not configured"),
        ):
            await notifications._send_slack("e", "m", "warning", {})


# ---------------------------------------------------------------------------
# _send_telegram
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendTelegram:
    async def test_telegram_success(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        with (
            patch.object(
                notifications.settings, "notification_telegram_bot_token", "bot123"
            ),
            patch.object(
                notifications.settings, "notification_telegram_chat_id", "chat456"
            ),
        ):
            result = await notifications._send_telegram(
                "event", "hello", "critical", {"key": "val"}
            )
        assert result == "telegram message delivered"
        assert calls[0]["url"] == "https://api.telegram.org/botbot123/sendMessage"
        assert calls[0]["json"]["chat_id"] == "chat456"
        assert "[CRITICAL] event" in calls[0]["json"]["text"]
        assert "key: val" in calls[0]["json"]["text"]

    async def test_telegram_raises_when_token_missing(self) -> None:
        with (
            patch.object(notifications.settings, "notification_telegram_bot_token", ""),
            patch.object(
                notifications.settings, "notification_telegram_chat_id", "chat"
            ),
            pytest.raises(ValueError, match="missing"),
        ):
            await notifications._send_telegram("e", "m", "warning", {})

    async def test_telegram_raises_when_chat_id_missing(self) -> None:
        with (
            patch.object(
                notifications.settings, "notification_telegram_bot_token", "bot123"
            ),
            patch.object(notifications.settings, "notification_telegram_chat_id", ""),
            pytest.raises(ValueError, match="missing"),
        ):
            await notifications._send_telegram("e", "m", "warning", {})


# ---------------------------------------------------------------------------
# _send_webhook
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendWebhook:
    async def test_webhook_success(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        with patch.object(
            notifications.settings, "notification_webhook_url", "https://wh"
        ):
            result = await notifications._send_webhook("e", "m", "warning", {"ctx": 1})
        assert result == "webhook delivered"
        assert calls[0]["url"] == "https://wh"
        expected = {
            "event": "e",
            "severity": "warning",
            "message": "m",
            "context": {"ctx": 1},
        }
        assert calls[0]["json"] == expected

    async def test_webhook_raises_when_unconfigured(self) -> None:
        with (
            patch.object(notifications.settings, "notification_webhook_url", ""),
            pytest.raises(ValueError, match="not configured"),
        ):
            await notifications._send_webhook("e", "m", "warning", {})


# ---------------------------------------------------------------------------
# _send_email
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendEmail:
    async def test_email_raises_for_non_resend_provider(self, monkeypatch) -> None:
        monkeypatch.setattr(
            notifications.settings, "notification_email_provider", "smtp"
        )
        with pytest.raises(ValueError, match="Only resend provider"):
            await notifications._send_email("e", "m", "warning", {})

    async def test_email_raises_when_api_key_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(
            notifications.settings, "notification_email_provider", "resend"
        )
        monkeypatch.setattr(notifications.settings, "notification_resend_api_key", "")
        with pytest.raises(ValueError, match="resend_api_key is not configured"):
            await notifications._send_email("e", "m", "warning", {})

    async def test_email_raises_when_from_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(
            notifications.settings, "notification_email_provider", "resend"
        )
        monkeypatch.setattr(
            notifications.settings, "notification_resend_api_key", "key123"
        )
        monkeypatch.setattr(notifications.settings, "notification_email_from", "")
        with pytest.raises(ValueError, match="email_from is not configured"):
            await notifications._send_email("e", "m", "warning", {})

    async def test_email_raises_when_recipients_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(
            notifications.settings, "notification_email_provider", "resend"
        )
        monkeypatch.setattr(
            notifications.settings, "notification_resend_api_key", "key123"
        )
        monkeypatch.setattr(
            notifications.settings, "notification_email_from", "from@x.com"
        )
        monkeypatch.setattr(notifications.settings, "notification_email_to", "")
        with pytest.raises(ValueError, match="email_to is not configured"):
            await notifications._send_email("e", "m", "warning", {})

    async def test_email_success(self, monkeypatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            notifications.httpx, "AsyncClient", lambda *a, **kw: _FakeAsyncClient(calls)
        )
        monkeypatch.setattr(
            notifications.settings, "notification_email_provider", "resend"
        )
        monkeypatch.setattr(
            notifications.settings, "notification_resend_api_key", "key123"
        )
        monkeypatch.setattr(
            notifications.settings, "notification_email_from", "from@x.com"
        )
        monkeypatch.setattr(notifications.settings, "notification_email_to", "to@x.com")
        result = await notifications._send_email(
            "event", "msg body", "critical", {"k": "v"}
        )
        assert result == "resend email delivered"
        assert calls[0]["url"] == "https://api.resend.com/emails"
        assert calls[0]["headers"]["Authorization"] == "Bearer key123"
        assert calls[0]["json"]["to"] == ["to@x.com"]
        assert calls[0]["json"]["subject"] == "[CRITICAL] event"


# ---------------------------------------------------------------------------
# dispatch_notification_event — integration of dispatch loop
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchNotificationEvent:
    async def test_multiple_channels_all_sent(self, monkeypatch) -> None:
        monkeypatch.setattr(notifications.settings, "notifications_enabled", True)
        monkeypatch.setattr(
            notifications.settings, "notification_default_channels", "slack,webhook"
        )
        monkeypatch.setattr(
            notifications, "_dispatch_to_channel", AsyncMock(return_value="ok")
        )
        result = await notifications.dispatch_notification_event(
            event="e", message="m", channels=["slack", "webhook"]
        )
        assert result["sent"] == 2
        assert result["failed"] == 0
        assert all(r["status"] == "sent" for r in result["results"])

    async def test_partial_failure_marks_only_failed_channel(self, monkeypatch) -> None:
        monkeypatch.setattr(notifications.settings, "notifications_enabled", True)
        call_count = 0

        async def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("down")
            return "ok"

        monkeypatch.setattr(
            notifications, "_dispatch_to_channel", AsyncMock(side_effect=flaky)
        )
        result = await notifications.dispatch_notification_event(
            event="e", message="m", channels=["slack", "webhook"]
        )
        assert result["sent"] == 1
        assert result["failed"] == 1
        assert result["results"][0]["status"] == "failed"
        assert result["results"][1]["status"] == "sent"

    async def test_uses_default_channels_when_none_provided(self, monkeypatch) -> None:
        monkeypatch.setattr(notifications.settings, "notifications_enabled", True)
        monkeypatch.setattr(
            notifications.settings, "notification_default_channels", "telegram"
        )
        monkeypatch.setattr(
            notifications, "_dispatch_to_channel", AsyncMock(return_value="ok")
        )
        result = await notifications.dispatch_notification_event(
            event="e", message="m", severity="info", context={"k": "v"}
        )
        assert len(result["results"]) == 1
        assert result["results"][0]["channel"] == "telegram"


# ---------------------------------------------------------------------------
# notify_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotifyInfo:
    async def test_notify_info_calls_dispatch_with_info_severity(
        self, monkeypatch
    ) -> None:
        dispatch = AsyncMock(
            return_value={
                "sent": 1,
                "failed": 0,
                "results": [],
                "event": "e",
                "severity": "info",
            }
        )
        monkeypatch.setattr(notifications, "dispatch_notification_event", dispatch)
        result = await notifications.notify_info(
            event="startup", message="ready", context={"c": 1}
        )
        dispatch.assert_awaited_once()
        _, kwargs = dispatch.call_args
        assert kwargs["severity"] == NOTIFICATION_SEVERITY_INFO
        assert result["sent"] == 1


# ---------------------------------------------------------------------------
# notify_background_task_failed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotifyBackgroundTaskFailed:
    async def test_builds_critical_context(self, monkeypatch) -> None:
        dispatch = AsyncMock(return_value={"sent": 0, "failed": 0, "results": []})
        monkeypatch.setattr(notifications, "dispatch_notification_event", dispatch)
        await notifications.notify_background_task_failed(
            task_id="job-1", batch_size=50, error="connection refused"
        )
        _, kwargs = dispatch.call_args
        assert kwargs["severity"] == "critical"
        assert kwargs["context"]["task_id"] == "job-1"
        assert kwargs["context"]["batch_size"] == 50
        assert kwargs["context"]["error"] == "connection refused"
        assert "task_id=" in kwargs["message"]


# ---------------------------------------------------------------------------
# deliver_notification_channel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeliverNotificationChannel:
    async def test_delivers_through_dispatch_to_channel(self, monkeypatch) -> None:
        monkeypatch.setattr(
            notifications, "_dispatch_to_channel", AsyncMock(return_value="delivered")
        )
        delivery = NotificationDelivery(
            id=1,
            inbox_consumption_id=1,
            message_id="msg-1",
            incident_id=10,
            source_id=5,
            tenant_id=42,
            event_type="notification.delivery_requested.v1",
            severity="critical",
            channel="slack",
        )
        request = MagicMock()
        request.payload = MagicMock()
        request.payload.trigger_type = "availability"
        request.payload.summary = "something broke"
        request.payload.severity = "critical"
        request.payload.incident_id = 10
        request.payload.source_id = 5
        request.payload.tenant_id = 42
        request.payload.occurrence_count = 1
        request.payload.guidance = "check stuff"

        result = await notifications.deliver_notification_channel(delivery, request)
        assert result == "delivered"


# ---------------------------------------------------------------------------
# existing dispatch tests (disabled / slack success)
# ---------------------------------------------------------------------------


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
