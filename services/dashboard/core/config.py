"""Dashboard configuration — framework-agnostic settings.

Read from environment variables or sensible defaults.
No Streamlit or other UI framework dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DashboardConfig:
    """Immutable configuration for the dashboard and its API client."""

    ingestor_url: str = field(
        default_factory=lambda: os.environ.get(
            "INGESTOR_URL", "http://localhost:8000"
        ).rstrip("/")
    )
    refresh_interval: int = field(
        default_factory=lambda: int(os.environ.get("DASHBOARD_REFRESH_INTERVAL", "30"))
    )
    max_stream_messages: int = field(
        default_factory=lambda: int(
            os.environ.get("DASHBOARD_MAX_STREAM_MESSAGES", "50")
        )
    )
    request_timeout: float = field(
        default_factory=lambda: float(
            os.environ.get("DASHBOARD_REQUEST_TIMEOUT", "5.0")
        )
    )
    probe_timeout: float = field(
        default_factory=lambda: float(os.environ.get("DASHBOARD_PROBE_TIMEOUT", "10.0"))
    )
    agent_timeout: float = field(
        default_factory=lambda: float(os.environ.get("DASHBOARD_AGENT_TIMEOUT", "60.0"))
    )
    stream_timeout: float = field(
        default_factory=lambda: float(
            os.environ.get("DASHBOARD_STREAM_TIMEOUT", "120.0")
        )
    )

    @property
    def api_base_url(self) -> str:
        return self.ingestor_url


# Module-level singleton — safe to import from any framework.
config = DashboardConfig()

# Shared reference for modules doing from-import during cold-start.
_CONFIG_SINGLETON = config
