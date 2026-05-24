"""Sentry setup helpers for ingestor app."""

from __future__ import annotations

import logging
from types import ModuleType
from typing import Any

from services.ingestor.config import settings


sentry_sdk_module: ModuleType | None = None
aiohttp_integration_cls: Any | None = None
fastapi_integration_cls: Any | None = None
logging_integration_cls: Any | None = None
sqlalchemy_integration_cls: Any | None = None
SENTRY_SDK_AVAILABLE = False


try:
    import sentry_sdk
    from sentry_sdk.integrations.aiohttp import AioHttpIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk_module: ModuleType | None = sentry_sdk
    aiohttp_integration_cls = AioHttpIntegration
    fastapi_integration_cls = FastApiIntegration
    logging_integration_cls = LoggingIntegration
    sqlalchemy_integration_cls = SqlalchemyIntegration
    SENTRY_SDK_AVAILABLE = True
except ImportError:
    pass


logger = logging.getLogger(__name__)


def _sentry_init(**kwargs: Any) -> None:
    """Small indirection for easier unit-testing of sentry initialization."""
    if sentry_sdk_module is not None:
        sentry_sdk_module.init(**kwargs)


def setup_sentry() -> bool:
    """Initialize Sentry SDK when enabled and properly configured.

    Returns:
        True when Sentry was initialized, otherwise False.
    """
    if not settings.sentry_enabled:
        logger.info("sentry_disabled")
        return False
    if not SENTRY_SDK_AVAILABLE:
        logger.warning("sentry_sdk_not_installed")
        return False
    if not settings.sentry_dsn:
        logger.warning("sentry_enabled_without_dsn")
        return False
    if (
        fastapi_integration_cls is None
        or sqlalchemy_integration_cls is None
        or aiohttp_integration_cls is None
        or logging_integration_cls is None
    ):
        logger.warning("sentry_integrations_not_available")
        return False

    integrations: list[Any] = [
        fastapi_integration_cls(transaction_style="endpoint"),
        sqlalchemy_integration_cls(),
        aiohttp_integration_cls(),
        logging_integration_cls(level=logging.INFO, event_level=logging.ERROR),
    ]

    _sentry_init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"{settings.app_name}@{settings.app_version}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        send_default_pii=settings.sentry_send_default_pii,
        integrations=integrations,
    )
    logger.info(
        "sentry_initialized",
        extra={
            "environment": settings.environment,
            "traces_sample_rate": settings.sentry_traces_sample_rate,
        },
    )
    return True
