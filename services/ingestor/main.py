"""FastAPI application entry point (async stack)."""

from __future__ import annotations

import importlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import HTMLResponse, JSONResponse

from libs.platform.auth import set_security_audit_emitter
from libs.platform.tracing import setup_tracing
from libs.version import get_contracts_version, get_version_payload
from services.ingestor.auth import (
    connect_session_store,
    disconnect_session_store,
    verify_docs_credentials,
)
from services.ingestor.config import settings
from services.ingestor.constants import HEALTH_RATE_LIMIT
from services.ingestor.core.background_workers import BackgroundWorkerPool
from services.ingestor.core.logging import set_cid, setup_logging
from services.ingestor.core.scheduler import JobScheduler
from services.ingestor.core.sentry import setup_sentry
from services.ingestor.core.tenant import TenantMiddleware
from services.ingestor.database import AsyncSessionLocal, engine, get_db
from services.ingestor.fetch import close_http_client

# from services.ingestor.fetch_aiohttp import close_http_session
from services.ingestor.jobs_registry import register_jobs, register_source_probe_jobs
from services.ingestor.metrics import (  # noqa: F401 — imported to register metrics at startup
    background_jobs_active,
    background_jobs_in_queue,
    background_jobs_processed_total,
    background_jobs_submitted_total,
    batch_size_histogram,
    enrich_duration_seconds,
    job_duration_seconds,
    job_executions_total,
    observations_created_total,
    observations_upsert_conflicts_total,
)
from services.ingestor.notifications import notify_background_task_failed
from services.ingestor.rate_limiting import limiter
from services.ingestor.routers import ws as ws_router


try:
    from services.ingestor.routers import mongo_analytics
except ModuleNotFoundError:
    mongo_analytics = None  # ty:ignore[invalid-assignment]
from services.ingestor.security.audit import emit_security_audit_event
from services.ingestor.services_lifecycle import (
    cleanup_external_services,
    initialize_external_services,
)


# Type alias for database dependency
type DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Structured JSON logging (setup once at app initialization)
# ---------------------------------------------------------------------------
# setup_logging() configures the root logger; get a named logger for this module
_setup_logging = setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request correlation ID middleware
# ---------------------------------------------------------------------------
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts or generates request correlation ID (cid).

    For each request:
    - Extract cid from X-Correlation-ID header if present
    - Otherwise generate a new UUID
    - Store in context (available via get_cid() for the request lifetime)
    Auto-injects cid into all log messages within this request.
    """

    async def dispatch(self, request: Request, call_next):
        """Extract/generate cid and set in context before handling request."""
        # Try to get cid from X-Correlation-ID header; fallback to new UUID
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        set_cid(cid)

        logger.info(
            "request_start",
            extra={
                "cid": cid,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
            },
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request_end",
            extra={
                "cid": cid,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Correlation-ID"] = cid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Baseline browser hardening headers.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )

        # HSTS only makes sense when traffic is served over HTTPS.
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


def _validate_production_security_settings() -> None:
    """Fail fast on weak default secrets in production-like environments."""
    if settings.environment.lower() not in {"production", "prod"}:
        return

    weak_jwt_secret = len(settings.jwt_secret) < 32
    jwt_secret_from_env = bool(os.environ.get("JWT_SECRET"))
    weak_docs_password = bool(settings.docs_password) and settings.docs_password in {
        "changeme",
        "admin",
        "password",
    }

    if weak_jwt_secret or weak_docs_password or not jwt_secret_from_env:
        raise RuntimeError(
            "Weak default secrets detected in production environment. "
            "Set strong values via environment variables or a secrets manager."
        )


# ---------------------------------------------------------------------------
# Lifespan: startup and shutdown events (e.g. for resource management)
# ---------------------------------------------------------------------------
# Global scheduler instance (initialized in lifespan startup)
_scheduler: JobScheduler | None = None
_background_workers: BackgroundWorkerPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager.

    Encapsulates startup and shutdown logic:
    1. Initialize distributed tracing (OTel) first
    2. Initialize external services (Cache, Broker, MongoDB) — fail-open
    3. Initialize and start job scheduler
    4. Yield to run application
    5. Shutdown in reverse order: scheduler, external services, HTTP clients, DB

    All external service failures are non-fatal and logged as warnings.
    """
    global _background_workers, _scheduler

    # ========================================================================
    # STARTUP
    # ========================================================================

    # Init distributed tracing first (trace_id available for all subsequent logs)
    setup_sentry()

    # Init distributed tracing (trace_id available for all subsequent logs)
    if settings.otel_enabled:
        setup_tracing(
            app,
            endpoint=settings.otel_exporter_otlp_endpoint,
            service_name=settings.otel_service_name,
        )

    logger.info("startup", extra={"event": "application_started"})
    _validate_production_security_settings()

    # Initialize session store (always-on, not gated by cache_enabled)
    try:
        await connect_session_store(settings.cache_url)
    except Exception as e:
        logger.warning("session_store_startup_failed", extra={"error": str(e)})

    # Wire optional platform-level security audit sink from the service layer.
    set_security_audit_emitter(emit_security_audit_event)

    # Initialize external services (Cache, Broker, MongoDB)
    await initialize_external_services()

    # Initialize job scheduler and register all jobs
    _scheduler = JobScheduler()
    register_jobs(_scheduler)
    try:
        async with AsyncSessionLocal() as session:
            registered_probe_jobs = await register_source_probe_jobs(
                _scheduler, session
            )
        logger.info(
            "source_probe_job_registration_complete",
            extra={"registered_probe_jobs": registered_probe_jobs},
        )
    except Exception as e:
        logger.warning(
            "source_probe_job_registration_failed",
            extra={"error": str(e)},
        )

    # Initialize in-process background worker pool (Pillar 5 prototype)
    if settings.background_workers_enabled:
        try:
            _background_workers = BackgroundWorkerPool(
                worker_count=settings.background_worker_count,
                queue_size=settings.background_worker_queue_size,
                max_tracked_tasks=settings.background_max_tracked_tasks,
                on_task_failed=lambda task: notify_background_task_failed(
                    task_id=task.task_id,
                    batch_size=task.batch_size,
                    error=task.error or "unknown",
                ),
            )
            await _background_workers.start()
            importlib.import_module(
                "services.ingestor.routers.background_processing"
            ).set_worker_pool(_background_workers)
            logger.info(
                "background_workers_started",
                extra={
                    "worker_count": settings.background_worker_count,
                    "queue_size": settings.background_worker_queue_size,
                },
            )
        except Exception as e:
            logger.warning(
                "background_workers_startup_failed",
                extra={"error": str(e)},
            )
    else:
        importlib.import_module(
            "services.ingestor.routers.background_processing"
        ).set_worker_pool(None)

    # Start scheduler (only if there are enabled jobs)
    try:
        await _scheduler.start(AsyncSessionLocal)
        # Inject scheduler into health router for health check endpoints
        from services.ingestor.routers import health_ingestion_jobs as health_router

        health_router.set_scheduler(_scheduler)

        # Inject scheduler into source_registry so newly registered sources
        # can get a probe job scheduled immediately (not just at next restart)
        from services.ingestor.routers import source_registry as source_registry_router

        source_registry_router.set_scheduler(_scheduler)
        logger.info(
            "scheduler_started",
            extra={"job_count": len(_scheduler._jobs)},
        )
    except Exception as e:
        logger.warning(
            "scheduler_startup_failed",
            extra={"error": str(e)},
        )
        # Non-fatal: app continues without scheduled jobs

    yield

    # ========================================================================
    # SHUTDOWN
    # ========================================================================

    # Stop scheduler first (cancel any running jobs)
    if _scheduler:
        try:
            await _scheduler.stop()
        except Exception as e:
            logger.warning(
                "scheduler_shutdown_error",
                extra={"error": str(e)},
            )

    # Stop background workers
    if _background_workers:
        try:
            await _background_workers.stop()
        except Exception as e:
            logger.warning(
                "background_workers_shutdown_error",
                extra={"error": str(e)},
            )

    # Cleanup session store
    await disconnect_session_store()

    # Clear platform-level hook during shutdown/reload.
    set_security_audit_emitter(None)

    # Cleanup external services (Cache, Broker, MongoDB)
    await cleanup_external_services()

    # Cleanup HTTP clients
    await close_http_client()  # httpx client
    # await close_http_session()  # aiohttp session

    # Cleanup database connections
    await engine.dispose()
    logger.info("shutdown", extra={"event": "application_shutdown_complete"})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# OpenAPI tag group descriptions
_OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "observations",
        "description": (
            "Core CRUD for pipeline observations. Write endpoints (POST, PATCH, DELETE) "
            "require a valid session cookie or bearer token. Rate-limited at 1 000 req/min per IP."
        ),
    },
    {
        "name": "observations-v2 — advanced rate limiting",
        "description": (
            "Extended observation endpoints demonstrating token-bucket and "
            "sliding-window rate limiting, "
            "stateless JWT auth, cursor pagination, concurrent enrichment, idempotent upsert, "
            "and the N+1 query demo."
        ),
    },
    {
        "name": "auth",
        "description": (
            "User registration, JWT issuance, session login/logout, and profile. "
            "Login is rate-limited to reduce brute-force risk."
        ),
    },
    {
        "name": "analytics",
        "description": "Aggregated analytics queries over the observations table (read-only).",
    },
    {
        "name": "scraper",
        "description": (
            "On-demand web scraper that fetches external URLs and stores "
            "results as observations."
        ),
    },
    {
        "name": "vector-search",
        "description": "Semantic indexing and querying against vectorized observations.",
    },
    {
        "name": "websocket",
        "description": "Real-time WebSocket feed of observation-created events.",
    },
    {
        "name": "health",
        "description": "Liveness/readiness probes and scheduled-job status.",
    },
    {
        "name": "background",
        "description": "Background worker pool management - submit batches and poll task status.",
    },
    {
        "name": "notifications",
        "description": "Notification dispatch endpoints for email, webhook, and Slack channels.",
    },
    {
        "name": "mongo-analytics",
        "description": "Analytics endpoints backed by MongoDB aggregation pipelines.",
    },
    {
        "name": "source-registry",
        "description": (
            "CRUD management for external API source profiles. "
            "Centralises reliability metadata (SLA targets, quota, cost) "
            "and auth policy per source. Includes live health probes."
        ),
    },
    {
        "name": "contract-drift",
        "description": (
            "Schema contract snapshots and drift detection per source. "
            "Tracks compatibility score and emits drift events when payload "
            "contracts change."
        ),
    },
    {
        "name": "insights",
        "description": (
            "Insight feeds derived from source reliability and drift signals. "
            "Provides anomaly, trend, and recommendation views for operations teams."
        ),
    },
    {
        "name": "subscriptions",
        "description": (
            "Subscription and delivery controls for alert routing, suppression, "
            "and dispatch validation."
        ),
    },
    {
        "name": "reporting",
        "description": (
            "Business intelligence rollups, cohort comparison, dashboard presets, "
            "and export jobs for analytics consumers."
        ),
    },
    {
        "name": "etl",
        "description": (
            "Polars-first ETL preview tooling with pandas compatibility and an "
            "intentional guardrail against premature Dask adoption."
        ),
    },
    {
        "name": "api-keys",
        "description": (
            "Tenant-aware API key lifecycle management with scoped permissions, "
            "expiry, and revocation support."
        ),
    },
    {
        "name": "abuse-detection",
        "description": (
            "Automated and manual abuse signal management. Detects noisy sources "
            "and suspicious API key usage patterns with configurable severity thresholds."
        ),
    },
]

# If docs_username/docs_password are configured, disable default docs
# (they'll be handled by protected endpoints below)
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    servers=[
        {"url": url.strip()}
        for url in settings.openapi_servers.split(",")
        if url.strip()
    ],
    description=(
        "Async data pipeline platform built on FastAPI, SQLAlchemy 2.0, and asyncpg.\n\n"
        "The API now spans authenticated observation ingestion, advanced rate-limiting demos, "
        "analytics, scraping, vector search, background processing, notifications, "
        "Mongo-backed aggregations, agent workflows, source registry management, "
        "contract drift detection, operational insights, subscriptions, reporting, "
        "ETL previews, tenant-aware API keys, WebSocket event streaming, and health probes.\n\n"
        "Current security controls include session and JWT authentication, tenant-aware "
        "API keys with scoped permissions and revocation, protected API docs, baseline "
        "security headers, and rate limiting on sensitive endpoints.\n\n"
        "**Representative endpoints:**\n"
        "- `POST /api/v1/observations` — core observation creation w/ fixed-window rate limiting\n"
        "- `POST /api/v2/observations/token-bucket` — burst-tolerant token-bucket limiter\n"
        "- `POST /api/v2/observations/sliding-window` — exact sliding-window limiter\n"
        "- `POST /api/v1/api-keys` — issue scoped tenant API keys\n"
        "- `GET /api/v1/source-registry` — manage external source profiles\n"
        "- `GET /api/v1/contract-drift/events` — inspect compatibility drift signals\n"
        "- `GET /api/v1/insights` — retrieve operational recommendations and anomalies\n"
        "- `GET /ws/observations` — subscribe to real-time observation events"
    ),
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
    docs_url=None if settings.docs_username else "/docs",
    redoc_url=None if settings.docs_username else "/redoc",
    openapi_url=None if settings.docs_username else "/openapi.json",
)

# Attach limiter to app (required by slowapi)
app.state.limiter = limiter

# Prometheus: register /metrics endpoint and instrument all HTTP routes.
# Must be called at module level (not inside lifespan) so the route is
# registered immediately — ASGITransport in tests does not trigger lifespan.
Instrumentator().instrument(app).expose(app, include_in_schema=False, tags=["ops"])


# Add rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded (429 Too Many Requests)."""
    logger.warning("rate_limit_exceeded", extra={"path": request.url.path})
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )
    if hasattr(request.state, "view_rate_limit"):
        response = request.app.state.limiter._inject_headers(
            response, request.state.view_rate_limit
        )
    return response


# ---------------------------------------------------------------------------
# Protected Documentation Endpoints (if auth is configured)
# ---------------------------------------------------------------------------
if settings.docs_username and settings.docs_password:
    """If docs auth is configured, protect Swagger UI, ReDoc, and OpenAPI schema."""

    @app.get(
        "/docs",
        include_in_schema=False,
        dependencies=[Depends(verify_docs_credentials)],
    )
    async def get_swagger_ui() -> HTMLResponse:
        """Protected Swagger UI endpoint."""
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{settings.app_name} - Swagger UI",
        )

    @app.get(
        "/redoc",
        include_in_schema=False,
        dependencies=[Depends(verify_docs_credentials)],
    )
    async def get_redoc() -> HTMLResponse:
        """Protected ReDoc endpoint."""
        return get_redoc_html(
            openapi_url="/openapi.json",
            title=f"{settings.app_name} - ReDoc",
        )

    @app.get(
        "/openapi.json",
        include_in_schema=False,
        dependencies=[Depends(verify_docs_credentials)],
    )
    async def get_openapi_schema() -> dict:
        """Protected OpenAPI schema endpoint."""
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=settings.app_name,
            version=settings.app_version,
            description=app.description,
            routes=app.routes,
        )
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    logger.info(
        "docs_auth_enabled",
        extra={"docs_endpoints": ["/docs", "/redoc", "/openapi.json"]},
    )


# Add correlation ID middleware early (runs before route handlers)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip() for host in settings.trusted_hosts.split(",") if host.strip()
    ],
)
app.add_middleware(TenantMiddleware)
app.add_middleware(CorrelationIdMiddleware)

_ROUTER_MODULES = [
    "auth",
    "observations",
    "observations_v2",
    "scraper",
    "analytics",
    "background_processing",
    "notifications",
    "vector_search",
    "health_ingestion_jobs",
    "source_registry",
    "contract_drift",
    "insights",
    "subscriptions",
    "reporting",
    "scorecards",
    "etl",
    "api_keys",
    "abuse_detection",
]
for _name in _ROUTER_MODULES:
    try:
        app.include_router(
            importlib.import_module(f"services.ingestor.routers.{_name}").router
        )
    except ModuleNotFoundError as exc:
        logger.warning(
            "router_unavailable",
            extra={"router": _name, "missing_module": str(exc)},
        )

if mongo_analytics is not None:
    app.include_router(mongo_analytics.router)

app.include_router(ws_router.router)


# ---------------------------------------------------------------------------
# Health & Readiness Probes
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
@limiter.limit(HEALTH_RATE_LIMIT)
async def health(request: Request) -> dict[str, object]:
    """Liveness probe — process is alive (no DB check).

    Used by Kubernetes to decide whether to restart the container.
    Lightweight and dependency-free by design: does not resolve version
    metadata, since that can be legitimately unavailable (see /version)
    without the process itself being unhealthy.
    Rate-limited to prevent health check DoS attacks.
    """
    return {"status": "healthy"}


@app.get("/readyz", tags=["ops"])
async def readyz(db: DbDep) -> dict[str, object]:
    """Readiness probe — DB and Cache reachable, pod can serve traffic.

    Used by Kubernetes to decide whether to route traffic to this pod.
    Returns 503 if DB or Cache is unreachable. Version metadata is
    best-effort context here, not a readiness criterion — a service with
    unresolved version info can still safely serve traffic (see /version
    for the strict, deliberate version-consensus check).
    """
    from services.ingestor.auth import _session_client as _cache

    checks: dict[str, str] = {}
    failed: list[str] = []

    try:
        await db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = "unreachable"
        failed.append(f"db: {e}")

    try:
        if _cache is not None:
            await _cache.ping()  # ty: ignore[invalid-await]
            checks["cache"] = "ok"
        else:
            checks["cache"] = "not_configured"
    except Exception as e:
        checks["cache"] = "unreachable"
        failed.append(f"cache: {e}")

    svc_version = os.getenv("SERVICE_VERSION") or settings.app_version
    try:
        contracts_version = get_contracts_version()
    except RuntimeError as e:
        logger.warning("contracts_version_unresolved", extra={"error": str(e)})
        contracts_version = "unknown"
    payload = {"contracts": contracts_version, "service": svc_version}

    if failed:
        logger.warning("readyz_failed", extra={"checks": checks, "failed": failed})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", **checks, "version": payload},
        )

    return {"status": "ready", **checks, "version": payload}


@app.get("/version", tags=["ops"])
@limiter.limit(HEALTH_RATE_LIMIT)
async def version(request: Request) -> dict[str, object]:
    """Strict version-consensus check — deliberate, not a liveness/readiness signal.

    Resolves service + contracts version with no fallback. Intended for CI,
    release tooling, or an operator to query across service instances before
    declaring a coordinated rollout, or to detect version drift. Fails loudly
    (500) when version provenance is missing or misconfigured — that failure
    is the point, so it must never be silently swallowed here.
    """
    try:
        return get_version_payload()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    from services.ingestor.core.logging import get_formatter, make_uvicorn_log_config

    log_config = make_uvicorn_log_config(get_formatter()) if get_formatter() else None
    uvicorn.run(
        "services.ingestor.main:app",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=8000,
        reload=True,
        log_config=log_config,
    )
