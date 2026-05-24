"""API schema modules grouped by bounded context."""

from . import (
    contract_drift,
    etl,
    insights,
    records,
    reporting,
    source_registry,
    subscriptions,
)


__all__ = [
    "contract_drift",
    "etl",
    "insights",
    "records",
    "reporting",
    "source_registry",
    "subscriptions",
]
