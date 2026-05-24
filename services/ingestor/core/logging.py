"""Environment-aware logging setup — runs once at app startup.

Development:
- Human-readable format with IDE-clickable source info (pathname:lineno:funcName)
- Console output + rotating file handler (logs/app.log)

Production:
- Minimal JSON (message + context fields only)
- No source location metadata (reduces noise in aggregation systems)

Provides:
- Global log level control via LOG_LEVEL env var
- Per-call log level control (logger.debug(), logger.info(), etc.)
- Correlation ID auto-injection via ContextVar
- Dependency lib logging control (sqlalchemy, httpx, asyncio, etc.)
"""

import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from pythonjsonlogger.json import JsonFormatter

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
# Formatters: Development (human-readable) vs Production (minimal JSON)
# ─────────────────────────────────────────────────────────────────────────────
class DevelopmentFormatter(logging.Formatter):
    """Human-readable format with IDE-clickable source info.

    Format: YYYY-MM-DD HH:MM:SS | LEVEL | pathname:lineno:funcName | [cid] msg extra_dict

    Example:
    2026-04-15 10:30:45 | INFO | app/routers/records.py:45:create_record | [abc-123]
    record created {'user': 'alice', 'record_id': 42}

    The pathname:lineno:funcName part is clickable in most IDEs (VS Code, PyCharm, etc.)
    allowing Ctrl+Click to jump directly to the source line.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable with IDE-clickable link,
        using project-root-relative path.
        """
        from pathlib import Path

        # Timestamp
        timestamp = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")

        # Level (right-padded for alignment)
        level_name = record.levelname.ljust(8)

        # Compute project root (directory containing this file)
        project_root = Path(__file__).parent.parent.parent.resolve()
        try:
            abs_path = Path(record.pathname).resolve()
            rel_path = abs_path.relative_to(project_root)
        except Exception:
            rel_path = Path(record.pathname).name  # fallback: just filename

        # Source location as IDE-clickable format (relative to project root)
        source_link = f"{rel_path}:{record.lineno}:{record.funcName}"

        # Correlation ID and trace ID if available
        cid = get_cid()
        cid_str = f"[{cid}]" if cid else ""
        trace_id = _get_trace_id()
        trace_str = f"[trace:{trace_id[:8]}]" if trace_id else ""

        # Message
        message = record.getMessage()

        # Extra fields (formatted as dict if present)
        extra_dict = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "taskName",
            }
        }
        extra_str = f" {extra_dict}" if extra_dict else ""

        prefix = " ".join(filter(None, [cid_str, trace_str]))
        prefix_str = f"{prefix} " if prefix else ""
        return f"{timestamp} | {level_name} | {source_link} | {prefix_str}{message}{extra_str}"


class ProductionJsonFormatter(JsonFormatter):
    """Minimal JSON formatter for centralized log aggregation.

    Includes only essential fields:
    - message: The log message
    - cid: Correlation ID (for request tracing)
    - Extra fields from the log call

    Does NOT include source location metadata (lineno, funcName, pathname)
    to reduce noise in aggregated logs viewed via Sentry/ELK/VictoriaMetrics.
    """

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add minimal fields: message + auto-injected cid only."""
        super().add_fields(log_data, record, message_dict)

        # Inject service name for log aggregator filters
        log_data.setdefault("service", "ingestor")

        # Auto-inject correlation ID and trace ID if available
        cid = get_cid()
        if cid:
            log_data["cid"] = cid
        trace_id = _get_trace_id()
        if trace_id:
            log_data["trace_id"] = trace_id


def setup_logging() -> logging.Logger:
    """Initialize environment-aware logging for the application.

    Call once at app startup (in lifespan hook).

    Development:
    - Human-readable format to console
    - RotatingFileHandler for logs/app.log (10MB per file, 5 backups)
    - Includes source location for IDE navigation

    Production:
    - Minimal JSON to stdout (ready for log aggregation)
    - No source location metadata (reduces noise)

    Configures:
    - Root logger level from LOG_LEVEL (default: INFO)
    - Dependency lib levels from environment (LOG_SQLALCHEMY_LEVEL, etc.)

    Returns:
        The root logger, configured and ready to use.
    """
    root_logger = logging.getLogger()

    # Remove any existing handlers to avoid duplication on reload
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set root logger level from settings (default: INFO)
    configured = str(settings.log_level or "INFO").upper()
    root_level = getattr(logging, configured, logging.INFO)
    root_logger.setLevel(root_level)

    # Environment-aware formatter and handler setup
    if settings.log_format == "json" or settings.environment == "production":
        # Production or explicit JSON: minimal JSON to stdout
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ProductionJsonFormatter())
        root_logger.addHandler(handler)
    else:
        # Development: human-readable + file rotation
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(DevelopmentFormatter())
        root_logger.addHandler(console_handler)

        # File handler with rotation (10MB per file, keep 5 backups)
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(DevelopmentFormatter())
        root_logger.addHandler(file_handler)

    # Configure dependency library loggers to reduce noise
    # These are set to WARNING by default; override via env vars
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

    # Return root logger for use in app
    return root_logger
