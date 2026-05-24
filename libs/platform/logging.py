"""Shared structured JSON logging for all platform services.

Call ``setup_json_logger(service_name)`` once at service startup (inside the
lifespan startup block, or at module level for non-FastAPI scripts).

Every log record emitted to stdout includes:

    timestamp   ISO-8601 (auto)
    level       "INFO" / "WARNING" / ...  (auto)
    service     value of *service_name* argument
    message     first positional arg to logger.info() etc.
    logger      dotted logger name (auto)
    ...         any extra fields from extra={} on the log call

Never call ``logging.basicConfig()`` in services that use this module — it
conflicts with the JSON formatter registered here.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter


class _ServiceJsonFormatter(JsonFormatter):
    """JSON formatter that injects the *service* field into every record."""

    def __init__(self, service_name: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._service_name = service_name

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_data, record, message_dict)
        log_data["service"] = self._service_name
        # Promote `level` to a top-level field for log aggregator filters
        log_data["level"] = record.levelname


def setup_json_logger(service_name: str) -> None:
    """Configure the root logger with a JSON formatter for *service_name*.

    Args:
        service_name: Short identifier emitted in every log record's
            ``service`` field (e.g. ``"processor"``, ``"inference``").

    The log level is taken from the ``LOG_LEVEL`` environment variable
    (default ``"INFO"``).  Valid values: ``DEBUG``, ``INFO``, ``WARNING``,
    ``ERROR``, ``CRITICAL``.
    """
    root_logger = logging.getLogger()

    # Remove existing handlers to avoid duplicate output on hot-reload
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    raw_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, raw_level, logging.INFO)
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    fmt = _ServiceJsonFormatter(
        service_name=service_name,
        fmt="%(timestamp)s %(level)s %(service)s %(name)s %(message)s",
    )
    handler.setFormatter(fmt)
    root_logger.addHandler(handler)

    # Suppress chatty dependency loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
