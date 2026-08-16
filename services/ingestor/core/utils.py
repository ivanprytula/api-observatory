"""Shared datetime and URL utilities for the ingestor service."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import ParseResult, urlparse, urlunparse


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def redact_url_password(url: str) -> str:
    """Replace the password component of a URL with ``***``.

    Args:
        url: A URL that may contain credentials (e.g. ``redis://:secret@host:port/0``).

    Returns:
        The URL with any password replaced by ``***``. If no password is present
        the original URL is returned unchanged.
    """
    parsed: ParseResult = urlparse(url)
    if not parsed.password:
        return url
    redacted = parsed._replace(
        netloc=f"{parsed.username or ''}:***@{parsed.hostname or ''}"
    )
    if parsed.port:
        redacted = redacted._replace(netloc=f"{redacted.netloc}:{parsed.port}")
    return urlunparse(redacted)
