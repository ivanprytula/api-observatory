"""FastAPI application entry point (async stack)."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from libs.platform.auth import set_security_audit_emitter
from libs.platform.http_timeout import RequestTimeoutMiddleware
from libs.platform.tracing import setup_tracing
from libs.version import get_contracts_version, get_version_payload
from services.ingestor.auth import (
    casbin_guard,
)
from services.ingestor.cache import get_redis_client
from services.ingestor.config import settings
from services.ingestor.constants import APP_DESCRIPTION, HEALTH_RATE_LIMIT
from services.ingestor.core.background_workers import (
    BackgroundTaskStatus,
    BackgroundWorkerPool,
)
from services.ingestor.core.bootstrap import bootstrap_initial_admin
from services.ingestor.core.logging import set_cid, setup_logging
from services.ingestor.core.scheduler import JobScheduler
from services.ingestor.core.sentry import setup_sentry
from services.ingestor.core.tenant import TenantMiddleware
from services.ingestor.database import AsyncSessionLocal, engine, get_db
from services.ingestor.events import publish_event_bytes
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
    retention_observations_archived_total,
    retention_observations_deleted_total,
    retention_runs_total,
)
from services.ingestor.notification_outbox_publisher import (
    notification_outbox_publisher_enabled,
    run_notification_outbox_publisher,
)
from services.ingestor.notifications import notify_background_task_failed
from services.ingestor.rate_limiting import limiter
from services.ingestor.rate_limiting_token_bucket import enforce_v1_token_bucket
from services.ingestor.routers import ws as ws_router
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
    if weak_jwt_secret or not jwt_secret_from_env:
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
_notification_outbox_publisher_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager.

    Encapsulates startup and shutdown logic:
    1. Initialize distributed tracing (OTel) first
    2. Initialize external services (Cache, Broker, MongoDB) — fail-open
    3. Start the opt-in notification outbox publisher
    4. Initialize and start job scheduler
    5. Yield to run application, then shut resources down in reverse order

    All external service failures are non-fatal and logged as warnings.
    """
    global _background_workers, _notification_outbox_publisher_task, _scheduler

    # ========================================================================
    # STARTUP
    # ========================================================================

    setup_sentry()

    # NOTE: setup_tracing() runs at module level (after the add_middleware
    # calls) — by lifespan time Starlette has already built the middleware
    # stack, so FastAPIInstrumentor would never enter the request path.

    logger.info("startup", extra={"event": "application_started"})
    _validate_production_security_settings()

    # Wire optional platform-level security audit sink from the service layer.
    set_security_audit_emitter(emit_security_audit_event)

    # Initialize external services (Cache, Broker, MongoDB)
    await initialize_external_services()

    # Bootstrap initial admin user on first startup (idempotent; skip if admin exists)
    try:
        async with AsyncSessionLocal() as session:
            await bootstrap_initial_admin(session)
    except Exception as exc:
        logger.warning(
            "initial_admin_bootstrap_failed",
            extra={"error": str(exc)},
        )

    if notification_outbox_publisher_enabled():
        _notification_outbox_publisher_task = asyncio.create_task(
            run_notification_outbox_publisher(
                AsyncSessionLocal,
                publish_event_bytes,
            ),
            name="notification-outbox-publisher",
        )
        logger.info("notification_outbox_publisher_started")

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
                on_task_failed=_notify_background_task_failure,
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

    # Initialize the LangGraph incident-triage agent (Phase 3) — fail-open,
    # same as everything else in this lifespan: if Anthropic isn't
    # configured or the `ai` extra isn't installed, the agent stays
    # disabled and drift detection works exactly as before.
    try:
        from services.ingestor.agent.runner import start_agent_checkpointer

        await start_agent_checkpointer()
    except Exception as e:
        logger.warning("agent_checkpointer_startup_failed", extra={"error": str(e)})

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

    if _notification_outbox_publisher_task:
        _notification_outbox_publisher_task.cancel()
        try:
            await _notification_outbox_publisher_task
        except asyncio.CancelledError:
            pass
        finally:
            _notification_outbox_publisher_task = None
        logger.info("notification_outbox_publisher_stopped")

    # Stop background workers
    if _background_workers:
        try:
            await _background_workers.stop()
        except Exception as e:
            logger.warning(
                "background_workers_shutdown_error",
                extra={"error": str(e)},
            )

    # Stop the incident-triage agent's checkpointer pool
    try:
        from services.ingestor.agent.runner import stop_agent_checkpointer

        await stop_agent_checkpointer()
    except Exception as e:
        logger.warning("agent_checkpointer_shutdown_error", extra={"error": str(e)})

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
        "name": "source-registry",
        "description": (
            "CRUD management for external API source profiles. "
            "Centralizes reliability metadata (SLA targets, quota, cost) "
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
    {
        "name": "agent",
        "description": (
            "LangGraph incident-triage agent. Auto-triggered by critical/breaking "
            "drift events (see contract-drift); classifies severity, retrieves "
            "similar prior incidents via RAG, drafts a root-cause analysis, then "
            "pauses for human review before notifying. Resume a paused run via "
            "POST /runs/{run_id}/resume."
        ),
    },
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    servers=[
        {"url": url.strip()}
        for url in settings.openapi_servers.split(",")
        if url.strip()
    ],
    description=APP_DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
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
app.add_middleware(
    RequestTimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds
)

# Init distributed tracing last so the OTel middleware wraps the whole stack:
# CorrelationIdMiddleware's request_start/request_end logs then run inside the
# server span and pick up trace_id. Must happen before the app starts serving
# (middleware cannot be added once Starlette builds its stack).
if settings.otel_enabled:
    setup_tracing(
        app,
        endpoint=settings.otel_exporter_otlp_endpoint,
        service_name=settings.otel_service_name,
    )

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
        app.include_router(
            importlib.import_module(f"services.ingestor.routers.{_name}").router,
            dependencies=dependencies,
        )
    except ModuleNotFoundError as exc:
        logger.warning(
            "router_unavailable",
            extra={"router": _name, "missing_module": str(exc)},
        )


if settings.websocket_enabled:
    app.include_router(ws_router.router)


# ---------------------------------------------------------------------------
# OpenAPI authentication contract
# ---------------------------------------------------------------------------
_PUBLIC_V1_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/register",
        "/api/v1/auth/token",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }
)
_AUTH_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["detail"],
    "properties": {"detail": {}},
}
_UNAUTHORIZED_RESPONSE: dict[str, Any] = {
    "description": "Missing, expired, or invalid bearer token.",
    "content": {"application/json": {"schema": _AUTH_ERROR_SCHEMA}},
}
_FORBIDDEN_RESPONSE: dict[str, Any] = {
    "description": "Authenticated caller lacks permission for this operation.",
    "content": {"application/json": {"schema": _AUTH_ERROR_SCHEMA}},
}


def _is_protected_v1_path(path: str) -> bool:
    """Return whether an OpenAPI path is protected by the production v1 boundary."""
    return path.startswith("/api/v1/") and path not in _PUBLIC_V1_AUTH_PATHS


def _openapi_with_auth_contract() -> dict[str, Any]:
    """Generate OpenAPI with the runtime v1 JWT boundary documented uniformly."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description=app.description,
        routes=app.routes,
    )
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    for path, path_item in openapi_schema["paths"].items():
        if not _is_protected_v1_path(path):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            operation["security"] = [{"BearerAuth": []}]
            responses = operation.setdefault("responses", {})
            responses["401"] = deepcopy(_UNAUTHORIZED_RESPONSE)
            responses["403"] = deepcopy(_FORBIDDEN_RESPONSE)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = _openapi_with_auth_contract  # ty: ignore[invalid-assignment]


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
    checks: dict[str, str] = {}
    failed: list[str] = []

    try:
        await db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = "unreachable"
        failed.append(f"db: {e}")

    if not settings.cache_enabled:
        checks["cache"] = "not_configured"
    else:
        try:
            cache_client = get_redis_client()
            if cache_client is not None:
                await cache_client.ping()
                checks["cache"] = "ok"
            else:
                checks["cache"] = "unreachable"
        except Exception as e:
            checks["cache"] = "unreachable"
            failed.append(f"cache: {e}")

    checks["websocket"] = "enabled" if settings.websocket_enabled else "disabled"

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
async def version(request: Request) -> dict[str, str]:
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

    formatter = get_formatter()
    log_config = make_uvicorn_log_config(formatter) if formatter else None
    uvicorn.run(
        "services.ingestor.main:app",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=8000,
        reload=True,
        log_config=log_config,
    )


async def _notify_background_task_failure(task: BackgroundTaskStatus) -> None:
    await notify_background_task_failed(
        task_id=task.task_id,
        batch_size=task.batch_size,
        error=task.error or "unknown",
    )
