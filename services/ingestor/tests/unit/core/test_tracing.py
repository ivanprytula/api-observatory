"""Regression tests for libs/platform/tracing.get_trace_id.

Post-MVP Phase 0 guard: get_trace_id() must return the active span's trace ID
as a 32-char hex string so structured logs stay correlated with Tempo traces
(services/ingestor/core/logging.py injects it as `trace_id`).
"""

from __future__ import annotations

import pytest

from libs.platform.tracing import get_trace_id


pytestmark = pytest.mark.unit


def test_get_trace_id_is_none_without_active_span() -> None:
    """Outside any span (or without OTel installed) the helper degrades to None."""
    assert get_trace_id() is None


def test_get_trace_id_returns_32_hex_inside_active_span() -> None:
    """Inside an active span the helper returns that span's 32-char hex trace ID."""
    pytest.importorskip("opentelemetry", reason="tracing extra not installed")
    from opentelemetry.sdk.trace import TracerProvider

    # Local provider — avoids mutating the process-global tracer provider,
    # which is one-shot and would leak into other tests.
    tracer = TracerProvider().get_tracer(__name__)
    with tracer.start_as_current_span("regression-guard") as span:
        trace_id = get_trace_id()

        assert trace_id is not None
        assert len(trace_id) == 32
        assert trace_id == format(span.get_span_context().trace_id, "032x")

    assert get_trace_id() is None
