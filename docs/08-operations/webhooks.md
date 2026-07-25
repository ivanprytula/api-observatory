# Webhook Boundaries

API Observatory does not run a standalone inbound webhook gateway. Earlier designs
reserved port `8004` for one, but no current service, route, database table, or deployment
manifest implements that design.

## Current Behavior

The implemented webhook capability is an **outbound notification channel**. Operational
events are dispatched from the ingestor through
[`services/ingestor/notifications.py`](../../services/ingestor/notifications.py). Provider
configuration is optional, dispatch is bounded by timeouts and resilience controls, and a
provider failure does not roll back the application event that caused the notification.

The notification API and subscription API are registered in:

- [`services/ingestor/routers/notifications.py`](../../services/ingestor/routers/notifications.py)
- [`services/ingestor/routers/subscriptions.py`](../../services/ingestor/routers/subscriptions.py)

Focused proof:

```bash
uv run pytest services/ingestor/tests/unit/core/test_notifications.py \
  services/ingestor/tests/unit/test_notifications_resilience.py \
  services/ingestor/tests/integration/test_notifications_api.py -q
```

## Deferred Inbound Gateway

An inbound webhook gateway would need signature verification, replay protection,
payload limits, tenant ownership, audit retention, and idempotent broker publication. It
should remain a **Decision** topic until a real integration requires push delivery instead
of scheduled probing. A port reservation or an old design document is not evidence that
the gateway exists.

The adoption trigger is a dependency whose polling interval cannot meet its freshness or
cost requirement and which offers signed webhooks with documented retry semantics.
