# services/ingestor/core — Entry Point

Purpose: Core utilities and infrastructure modules for the ingestor service: logging, scheduling, multi-tenancy, and background job processing.

Modules:

- `logging.py` — Structured logging setup (JSON format, context-aware fields)
- `scheduler.py` — APScheduler configuration and job registry
- `sentry.py` — Sentry error reporting integration
- `tenant.py` — Multi-tenancy context (ContextVar)
- `background_workers.py` — Background job patterns (in-process queue)

Import convention: `from services.ingestor.core import <module>` (avoid importing internals directly).

Docstring convention (Google-style + pattern name):

```python
async def fetch_with_retry(url: str, max_retries: int = 3) -> str:
    """
    Fetch a URL with exponential backoff retry (Resilience Pattern: Retry).

    Args:
        url: The URL to fetch (must be HTTPS for security)
        max_retries: Maximum retry attempts before raising

    Returns:
        Response body as string

    Raises:
        HttpError: If all retries exhausted
    """
```
