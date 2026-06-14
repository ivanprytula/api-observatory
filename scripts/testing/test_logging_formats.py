"""Demo script to show development vs production logging formats.

Usage:
    uv run python scripts/testing/test_logging_formats.py

Shows side-by-side comparison of:
- Development format: human-readable with IDE-clickable source info + rotating file handler
- Production format: minimal JSON for log aggregation (Sentry/ELK/VictoriaMetrics)
"""

import json
import logging
import sys
from io import StringIO
from pathlib import Path


# Add repo root to path so we can import ingestor
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ingestor.config import settings
from services.ingestor.core.logging import set_cid, setup_logging


def separator(title: str) -> None:
    """Print a visual separator."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def demo_environment(environment: str, description: str) -> None:
    """Demo logging in a specific environment."""
    separator(f"{environment.upper()} ENVIRONMENT — {description}")

    # Clear existing handlers and logger state
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set environment
    settings.environment = environment
    settings.log_level = "DEBUG"

    # Get fresh logger with new setup
    logger = setup_logging()

    # Generate correlation ID for this demo
    cid = "demo-cid-550e8400-e29b-41d4-a716-446655440000"
    set_cid(cid)

    # Demo: Various log levels with extra data
    print(f"Correlation ID: {cid}\n")
    print("Sample log calls and their output:\n")

    log_examples = [
        (
            "debug",
            {"user": "alice", "request_id": 123},
            "debug message with user context",
        ),
        (
            "info",
            {"action": "record_created", "record_id": 42},
            "info message about event",
        ),
        (
            "warning",
            {"retry_count": 3, "url": "https://api.example.com"},
            "warning with retry info",
        ),
        (
            "error",
            {"error_code": "DB_CONNECTION_FAILED"},
            "error message with error code",
        ),
    ]

    for level_name, extra_data, message in log_examples:
        print(f"Code: logger.{level_name}({message!r}, extra={extra_data})")
        logger_method = getattr(logger, level_name)
        logger_method(message, extra=extra_data)
        print()

    # Show file output for development
    if environment == "development":
        log_file = Path("logs/app.log")
        if log_file.exists():
            print("\n" + "-" * 80)
            print("File output (logs/app.log) — last 20 lines:")
            print("-" * 80 + "\n")
            with open(log_file) as f:
                lines = f.readlines()[-20:]
                for line in lines:
                    print(line.rstrip())


def demo_json_structure() -> None:
    """Show the actual JSON structure in production."""
    separator("PRODUCTION JSON STRUCTURE — What log aggregation systems see")

    # Capture JSON output in production mode
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.environment = "production"
    settings.log_level = "INFO"

    # Redirect stdout to capture JSON
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    logger = setup_logging()
    set_cid("demo-cid-12345")

    logger.info(
        "record_created", extra={"record_id": 42, "user_id": 99, "duration_ms": 150}
    )
    logger.warning(
        "high_latency", extra={"endpoint": "/api/records", "duration_ms": 5200}
    )

    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    # Parse and display each JSON line
    print("Each line is valid JSON for direct import into log aggregation systems:\n")
    for i, line in enumerate(output.strip().split("\n"), 1):
        if line:
            try:
                parsed = json.loads(line)
                print(f"Log #{i}:")
                print(json.dumps(parsed, indent=2))
                print()
            except json.JSONDecodeError:
                print(f"Log #{i} (raw):\n{line}\n")


def main() -> None:
    """Run all demos."""
    print("\n" + "█" * 80)
    print("█ LOGGING FORMAT DEMO: Development vs Production")
    print("█" * 80)

    # Remove any existing logs for clean demo
    log_file = Path("logs/app.log")
    if log_file.exists():
        log_file.unlink()

    demo_environment(
        "development",
        "Human-readable console + rotating file handler with IDE-clickable links",
    )

    demo_environment(
        "production",
        "Minimal JSON to stdout (ready for Sentry/ELK/VictoriaMetrics)",
    )

    demo_json_structure()

    separator("DEMO COMPLETE")
    print("\nKey observations:\n")
    print("1. DEVELOPMENT format:")
    print("   ✓ Human-readable with ISO timestamps")
    print("   ✓ IDE-clickable format: pathname:lineno:funcName")
    print("   ✓ Extra fields shown as dict suffix")
    print("   ✓ Logged to console AND logs/app.log (10MB rotate, 5 backups)")
    print()
    print("2. PRODUCTION format:")
    print("   ✓ Minimal JSON fields (message + extra context + cid)")
    print("   ✓ No source location metadata (reduces noise in aggregated logs)")
    print("   ✓ Easy to parse and index in log aggregation systems")
    print("   ✓ Ready for Sentry, ELK, Datadog, VictoriaMetrics, OpenSearch")
    print()
    print("3. Control via environment variables:")
    print("   • ENVIRONMENT: 'development' or 'production'")
    print("   • LOG_LEVEL: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'")
    print("   • LOG_SQLALCHEMY_LEVEL: Optional SQLAlchemy logger level")
    print("   • LOG_HTTPX_LEVEL: Optional HTTPX logger level")
    print("   • LOG_ASYNCIO_LEVEL: Optional asyncio logger level")
    print()


if __name__ == "__main__":
    main()
