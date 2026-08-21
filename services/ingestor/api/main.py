"""API router assembly — mirrors the reference template's api/main.py pattern.

Aggregates all domain routers under a single ``api_router`` so that
``main.py`` only needs one ``include_router`` call.
"""

from __future__ import annotations

import importlib
import logging

from fastapi import APIRouter, Depends

from services.ingestor.core.auth import casbin_guard
from services.ingestor.core.config import settings
from services.ingestor.rate_limiting_token_bucket import enforce_v1_token_bucket


logger = logging.getLogger(__name__)

api_router = APIRouter()

_ROUTER_MODULES = [
    "auth",
    "agent",
    "observations",
    "analytics",
    "background_processing",
    "notifications",
    "vector_search",
    "health_ingestion_jobs",
    "source_registry",
    "contract_drift",
    "insights",
    "incidents",
    "subscriptions",
    "reporting",
    "scorecards",
    "etl",
    "abuse_detection",
]
_ADMIN_PROTECTED_ROUTERS = {
    "background_processing",
    "health_ingestion_jobs",
    "notifications",
    "etl",
}

for _name in _ROUTER_MODULES:
    try:
        dependencies = [] if _name == "auth" else [Depends(enforce_v1_token_bucket)]
        if _name in _ADMIN_PROTECTED_ROUTERS:
            dependencies.append(Depends(casbin_guard("admin")))
        api_router.include_router(
            importlib.import_module(f"services.ingestor.api.routes.{_name}").router,
            dependencies=dependencies,
        )
    except ModuleNotFoundError as exc:
        logger.warning(
            "router_unavailable",
            extra={"router": _name, "missing_module": str(exc)},
        )

if settings.websocket_enabled:
    from services.ingestor.api.routes import ws as ws_router

    api_router.include_router(ws_router.router)

if settings.auth_demo_routes_enabled:
    from services.ingestor.api.routes.observations import demo_router

    api_router.include_router(demo_router)
