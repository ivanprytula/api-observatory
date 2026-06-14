"""Prometheus metrics parsing utilities.

Pure logic, no UI dependencies.
"""

from __future__ import annotations

import contextlib


def parse_prometheus_counter(metrics_text: str, metric_name: str) -> float:
    """Sum all values for a Prometheus counter metric.

    Handles both `metric_total 42` and `metric_total{labels} 42` lines.
    """
    total = 0.0
    prefix = f"{metric_name}_total"
    for line in metrics_text.splitlines():
        if line.startswith(prefix) and not line.startswith(f"{prefix}_"):
            parts = line.split()
            if len(parts) >= 2:
                with contextlib.suppress(ValueError):
                    total += float(parts[-1])
    return total


def parse_metric_value(metrics_text: str, metric_name: str) -> float | None:
    """Extract a single Prometheus gauge/counter value by exact metric name.

    Returns None if the metric is absent or unparseable.
    """
    for line in metrics_text.splitlines():
        if line.startswith(f"{metric_name} "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return float(parts[-1])
                except ValueError:
                    return None
    return None
