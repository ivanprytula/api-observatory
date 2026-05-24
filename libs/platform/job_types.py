"""Job type definitions for scheduling.

Separated into its own module to avoid circular imports between
scheduler.py and handlers.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


@dataclass
class JobHealthMetrics:
    """Health metrics for a scheduled job."""

    last_run_at: datetime | None = None
    last_run_duration_seconds: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    last_error: str | None = None

    @property
    def success_rate(self) -> float:
        """Return success rate [0.0, 1.0]. Returns 1.0 if no runs yet."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    @property
    def is_healthy(self) -> bool:
        """Return True if no recent errors and success rate > 80%."""
        return self.last_error is None and self.success_rate >= 0.8


@dataclass
class Job:
    """Job definition for scheduled execution.

    Attributes:
        name: Unique job identifier.
        handler: Async callable (coroutine function) that performs the work.
        trigger: APScheduler trigger (CronTrigger, IntervalTrigger, etc).
        max_retries: Max retry attempts on failure (default 3).
        timeout_seconds: Job timeout; if exceeded, job is cancelled (default None).
        tags: Metadata tags (e.g., "critical", "high_volume") for monitoring.
    """

    name: str
    handler: Callable[..., Any]
    trigger: CronTrigger | IntervalTrigger | None
    max_retries: int = 3
    timeout_seconds: int | None = None
    tags: set[str] = field(default_factory=set)
    _health: JobHealthMetrics = field(default_factory=JobHealthMetrics, init=False)

    @property
    def health(self) -> JobHealthMetrics:
        """Read-only access to job health metrics."""
        return self._health
