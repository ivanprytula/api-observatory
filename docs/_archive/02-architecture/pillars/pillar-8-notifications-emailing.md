# Pillar 8: Notifications and Emailing

Track: E — Archive and Historical Snapshots

**Tier**: Middle (🟡) with operational impact
**Status**: Baseline implemented (April 23, 2026)

---

## Implemented Baseline

- Notification abstraction in [ingestor/notifications.py](../../services/ingestor/notifications.py)
- Supported channels:
  - `slack` (incoming webhook)
  - `telegram` (bot token + chat id)
  - `webhook` (generic JSON webhook, suitable for Jira automation)
  - `email` (Resend transactional API)
- Background worker failure alert hook integrated in [ingestor/core/background_workers.py](../../services/ingestor/core/background_workers.py)
- Manual dispatch API route in [ingestor/api/routes/notifications.py](../../services/ingestor/api/routes/notifications.py)
- Test endpoint: `POST /api/v1/notifications/test`
- Sentry SDK integration wired at app startup for centralized exception tracking

---

## Team-Tool Strategy (Jira + Slack + Telegram)

Recommended routing:

1. **Warning severity**

- Send to Slack channel (fast visibility, low noise)
- Optional Telegram mirror for on-call mobile visibility

1. **Critical severity**

- Send to Slack + Telegram immediately
- Trigger Jira automation via webhook to create/transition incident ticket

1. **Audit/summary notifications**

- Send email summaries (Resend) to engineering DL

Flow example:

```text
Background task fails
  -> notification service
  -> Sentry event (stack trace + release context)
    -> Slack alert (team channel)
    -> Telegram alert (on-call)
    -> Jira webhook (create issue INC-xxx)
    -> Email summary (optional, batched)
```

---

## Provider Recommendation

### Email providers

- **Resend**: Best fit now. Simple HTTP API, fast setup, good developer experience. Implemented in this baseline.
- **AWS SES**: Best at scale in AWS. Strong deliverability and low cost, but higher setup complexity.
- **Gmail SMTP**: Useful for ad-hoc personal testing only; avoid for production alerting.
- **Proton Mail**: Good privacy mailbox option, but not ideal as transactional notification backend.

### Messaging channels

- **Slack**: Primary real-time alert channel for engineering collaboration.
- **Telegram**: Secondary on-call/mobile channel for critical alerts.
- **Jira**: Incident workflow tracking via webhook/automation for ticket creation.

---

## Suggested Environment Variables

```text
NOTIFICATIONS_ENABLED=true
NOTIFICATION_DEFAULT_CHANNELS=slack,telegram,webhook,email

NOTIFICATION_SLACK_WEBHOOK_URL=
NOTIFICATION_TELEGRAM_BOT_TOKEN=
NOTIFICATION_TELEGRAM_CHAT_ID=
NOTIFICATION_WEBHOOK_URL=

NOTIFICATION_EMAIL_PROVIDER=resend
NOTIFICATION_RESEND_API_KEY=
NOTIFICATION_EMAIL_FROM=
NOTIFICATION_EMAIL_TO=team@example.com
```

---

## Next Implementation Slice

- Add deduplication window for repeated alerts (anti-noise)
- Add retry/backoff with circuit breaking for notification providers
- Add Jira-specific payload adapter (issue type, project key, labels)
- Add admin UI controls for test dispatch and per-channel toggles
