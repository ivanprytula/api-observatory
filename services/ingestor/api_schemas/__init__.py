"""API schema modules grouped by bounded context."""

from . import (
    contract_drift,
    etl,
    insights,
    observations,
    reporting,
    source_registry,
    subscriptions,
)


__all__ = [
    "contract_drift",
    "etl",
    "insights",
    "observations",
    "reporting",
    "source_registry",
    "subscriptions",
]
