"""Dashboard core — framework-agnostic business logic.

Public surface:
    DashboardConfig, config     — settings
    AuthManager, AuthState      — OAuth2 lifecycle
    DashboardApiError           — typed API error
    api_client functions        — typed HTTP functions (fetch_*, probe_*, source CRUD)
    metrics_parser              — Prometheus text parsing
"""

from services.dashboard.core.api_client import DashboardApiError
from services.dashboard.core.auth import AuthManager, AuthState
from services.dashboard.core.config import DashboardConfig, config
from services.dashboard.core.metrics_parser import (
    parse_metric_value,
    parse_prometheus_counter,
)


__all__ = [
    "AuthManager",
    "AuthState",
    "DashboardApiError",
    "DashboardConfig",
    "config",
    "parse_metric_value",
    "parse_prometheus_counter",
]
