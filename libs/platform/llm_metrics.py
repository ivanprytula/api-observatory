"""Shared LLM usage telemetry for Prometheus and OpenTelemetry.

Cost estimates use the configured standard Anthropic per-million-token prices.
They exclude caching, batch, and enterprise-discount adjustments, so they are
useful for operational trends but not billing reconciliation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from prometheus_client import Counter


_TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPricing:
    """Standard USD token prices for one model."""

    input_per_million: float
    output_per_million: float


# Update this table when a configured model's provider pricing changes. Unknown
# models still emit token metrics but report zero estimated cost.
MODEL_PRICING_USD: dict[str, ModelPricing] = {
    "claude-haiku-4-5": ModelPricing(input_per_million=1.0, output_per_million=5.0),
    "claude-sonnet-4-5": ModelPricing(input_per_million=3.0, output_per_million=15.0),
}


llm_tokens_total = Counter(
    name="llm_tokens_total",
    documentation="LLM tokens consumed by model and token type.",
    labelnames=["model", "type"],
)
llm_estimated_cost_usd_total = Counter(
    name="llm_estimated_cost_usd_total",
    documentation="Estimated LLM spend in USD using configured standard token prices.",
    labelnames=["model"],
)


def record_llm_usage(*, model: str, response: object) -> None:
    """Record token and cost telemetry from a LangChain raw model response.

    Provider usage metadata is optional. Missing or malformed metadata is
    intentionally ignored so observability never changes a successful agent
    response into a failure.
    """
    usage_metadata = getattr(response, "usage_metadata", None)
    if not isinstance(usage_metadata, Mapping):
        return

    input_tokens = _non_negative_int(usage_metadata.get("input_tokens"))
    output_tokens = _non_negative_int(usage_metadata.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        return

    prompt_tokens = input_tokens or 0
    completion_tokens = output_tokens or 0
    llm_tokens_total.labels(model=model, type="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(model=model, type="completion").inc(completion_tokens)

    estimated_cost = estimate_cost_usd(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    llm_estimated_cost_usd_total.labels(model=model).inc(estimated_cost)
    _set_span_attributes(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost=estimated_cost,
    )


def estimate_cost_usd(
    *, model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Estimate standard token spend in USD, returning zero for unknown models."""
    pricing = MODEL_PRICING_USD.get(model)
    if pricing is None:
        return 0.0
    return (
        prompt_tokens * pricing.input_per_million
        + completion_tokens * pricing.output_per_million
    ) / _TOKENS_PER_MILLION


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _set_span_attributes(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost: float,
) -> None:
    """Attach usage attributes when OpenTelemetry has an active span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.tokens.prompt", prompt_tokens)
        span.set_attribute("llm.tokens.completion", completion_tokens)
        span.set_attribute("llm.cost.estimated_usd", estimated_cost)
