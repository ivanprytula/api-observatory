"""Tests for provider-agnostic LLM usage telemetry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from libs.platform.llm_metrics import (
    estimate_cost_usd,
    llm_estimated_cost_usd_total,
    llm_tokens_total,
    record_llm_usage,
)


pytestmark = pytest.mark.unit


def test_record_llm_usage_records_tokens_and_estimated_cost() -> None:
    model = "claude-haiku-4-5"
    prompt = llm_tokens_total.labels(model=model, type="prompt")._value.get()
    completion = llm_tokens_total.labels(model=model, type="completion")._value.get()
    cost = llm_estimated_cost_usd_total.labels(model=model)._value.get()

    record_llm_usage(
        model=model,
        response=SimpleNamespace(
            usage_metadata={"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        ),
    )

    assert (
        llm_tokens_total.labels(model=model, type="prompt")._value.get()
        == prompt + 1_000_000
    )
    assert (
        llm_tokens_total.labels(model=model, type="completion")._value.get()
        == completion + 1_000_000
    )
    assert llm_estimated_cost_usd_total.labels(model=model)._value.get() == cost + 6.0


def test_record_llm_usage_ignores_absent_usage_metadata() -> None:
    model = "claude-sonnet-4-5"
    prompt = llm_tokens_total.labels(model=model, type="prompt")._value.get()

    record_llm_usage(model=model, response=SimpleNamespace(usage_metadata=None))

    assert llm_tokens_total.labels(model=model, type="prompt")._value.get() == prompt
    assert (
        estimate_cost_usd(
            model="unknown-model", prompt_tokens=100, completion_tokens=100
        )
        == 0.0
    )
