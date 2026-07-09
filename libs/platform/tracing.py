"""OpenTelemetry distributed tracing setup.

Wires the TracerProvider with an OTLP gRPC exporter (Jaeger all-in-one or
any OTLP collector) and auto-instruments FastAPI.

Usage (from app/main.py lifespan):

    from services.ingestor.core.tracing import setup_tracing
    setup_tracing(
        app,
        endpoint=settings.otel_exporter_otlp_endpoint,
        service_name=settings.otel_service_name,
    )

The module degrades gracefully: if OTel packages are missing or the endpoint
is unreachable at startup, a warning is logged and the app starts without tracing.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_initialized = False


def _suppress_tzlocal_output() -> None:
    """Suppress tzlocal's diagnostic print statements during OTel init.

    tzlocal outputs timezone detection info via print() during tracer provider
    initialization. Setting TZ env var prevents runtime detection.
    """
    # tzlocal checks these env vars; setting them prevents runtime detection
    os.environ.setdefault("TZ", os.environ.get("TZ", "UTC"))


def setup_tracing(
    app: FastAPI,
    endpoint: str,
    service_name: str,
) -> None:
    """Initialize the OTLP TracerProvider and auto-instrument FastAPI.

    Idempotent — safe to call multiple times (subsequent calls are no-ops).

    Args:
        app: The FastAPI application instance to instrument.
        endpoint: OTLP gRPC endpoint URL (e.g., http://jaeger:4317).
        service_name: Name shown in the Jaeger service dropdown.
    """
    global _initialized
    if _initialized:
        return

    # Suppress tzlocal output before importing OTel (which triggers tzlocal)
    _suppress_tzlocal_output()

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(enable_commenter=True)

        _initialized = True
        logger.info(
            "otel_tracing_initialized",
            extra={"endpoint": endpoint, "service": service_name},
        )
    except ImportError as exc:
        logger.warning(
            "otel_tracing_unavailable",
            extra={"error": str(exc), "hint": "Install opentelemetry-sdk packages"},
        )
    except Exception as exc:
        logger.warning(
            "otel_tracing_setup_failed",
            extra={"error": str(exc)},
        )


def get_trace_id() -> str | None:
    """Return the current OTel trace ID as a 32-char hex string.

    Returns None when:
    - OTel is not installed
    - There is no active span in the current context
    - The span context is invalid (e.g., no-op tracer)

    Used by log formatters to inject trace_id into structured log output
    so log observations can be correlated with Jaeger traces.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except ImportError, AttributeError, TypeError, ValueError:
        return None
    return None
