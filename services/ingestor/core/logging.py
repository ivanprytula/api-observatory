"""Environment-aware structured logging setup — runs once at app startup.

Uses structlog with a stdlib bridge (ProcessorFormatter) so all existing
``logging.getLogger(__name__)`` call sites remain unchanged.

Development:
- structlog ConsoleRenderer (human-readable, coloured)
- Console + rotating file handler (logs/app.log)

Production:
- structlog JSONRenderer (one-line structured JSON per event)
- Console only (JSON) — no local file writes
"""

from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.stdlib import ProcessorFormatter

from services.ingestor.config import settings


def _get_trace_id() -> str | None:
    """Return the current OTel trace ID, or None if not in a trace."""
    try:
        from libs.platform.tracing import get_trace_id

        return get_trace_id()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Context variable for request correlation ID (cid)
# ─────────────────────────────────────────────────────────────────────────────
# Stores the unique request ID (cid) during request handling.
request_cid: ContextVar[str | None] = ContextVar("request_cid", default=None)


def get_cid() -> str | None:
    """Get the current request's correlation ID, or None outside a request."""
    return request_cid.get()


def set_cid(cid: str) -> None:
    """Set the correlation ID for the current request context."""
    request_cid.set(cid)


# ─────────────────────────────────────────────────────────────────────────────
# Stdlib LogObservation attributes excluded from "extra" field forwarding
# ─────────────────────────────────────────────────────────────────────────────
_STDLIB_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# structlog processors
# ─────────────────────────────────────────────────────────────────────────────


def _extract_extra(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Forward ``extra={}`` fields from stdlib LogObservation into event_dict.

    When stdlib code calls ``logger.info("msg", extra={"key": "val"})``,
    the extra keys are attributes on the LogObservation.  This processor copies
    them into the structlog event_dict so renderers can include them.
    """
    observation: logging.LogObservation | None = event_dict.get("_observation")  # type: ignore[assignment]
    if observation is None:
        return event_dict
    for key, value in observation.__dict__.items():
        if key not in _STDLIB_ATTRS and not key.startswith("_"):
            event_dict.setdefault(key, value)
    return event_dict


def _inject_context(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Inject request correlation ID and OTel trace ID into event_dict."""
    cid = get_cid()
    if cid:
        event_dict["cid"] = cid
    trace_id = _get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def setup_logging() -> logging.Logger:
    """Configure structlog and wire it to stdlib logging.

    Uses ``structlog.stdlib.ProcessorFormatter`` as the stdlib handler's
    formatter so every ``logging.getLogger(__name__)`` call site works
    unchanged while output passes through the structlog processor chain.

    Dev:   structlog ConsoleRenderer — coloured, human-readable.
    Prod:  structlog JSONRenderer — one JSON object per line to stdout.

    Also applies a RotatingFileHandler (dev only) and silences noisy
    dependency loggers via per-env settings.

    Returns:
        The root ``logging.Logger`` (already configured).
    """
    configured = str(settings.log_level or "INFO").upper()
    root_level = getattr(logging, configured, logging.INFO)

    use_json = settings.log_format == "json" or settings.environment == "production"

    # Shared processors run for both stdlib-bridged and native structlog calls.
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_context,
        _extract_extra,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer()
    )

    # ProcessorFormatter bridges stdlib LogObservations through structlog processors.
    formatter = ProcessorFormatter(
        processors=[ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared_processors,
    )

    # ── stdlib root logger ──────────────────────────────────────────────────
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.setLevel(root_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if not use_json:
        log_dir = Path(os.environ.get("LOG_DIR", "/tmp/logs"))  # nosec B108
        log_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # ── structlog global configuration ──────────────────────────────────────
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.render_to_log_kwargs,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # ── silence noisy dependency libraries ──────────────────────────────────
    if settings.log_sqlalchemy_level:
        dep_level = getattr(
            logging,
            str(settings.log_sqlalchemy_level).upper(),
            logging.WARNING,
        )
        logging.getLogger("sqlalchemy").setLevel(dep_level)
        logging.getLogger("sqlalchemy.engine").setLevel(dep_level)

    if settings.log_httpx_level:
        dep_level = getattr(
            logging, str(settings.log_httpx_level).upper(), logging.WARNING
        )
        logging.getLogger("httpx").setLevel(dep_level)

    if settings.log_asyncio_level:
        dep_level = getattr(
            logging, str(settings.log_asyncio_level).upper(), logging.WARNING
        )
        logging.getLogger("asyncio").setLevel(dep_level)

    return root_logger
