"""App settings (async stack)."""

import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.ingestor.constants import (
    BACKGROUND_MAX_TRACKED_TASKS_DEFAULT,
    BACKGROUND_WORKER_COUNT_DEFAULT,
    BACKGROUND_WORKER_QUEUE_SIZE_DEFAULT,
    NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT,
    SCRAPER_HTTP_TIMEOUT_SECONDS_DEFAULT,
    VECTOR_SEARCH_DEFAULT_COLLECTION,
    VECTOR_SEARCH_HTTP_TIMEOUT_SECONDS_DEFAULT,
)


class Settings(BaseSettings):
    """Application configuration.

    Reads from .env (local dev) or environment variables (CI/prod).
    Order of precedence: environment > .env > defaults
    """

    # Database — asyncpg DSN uses postgresql+asyncpg://
    # REQUIRED: Must be set via DATABASE_URL environment variable
    # ============ Database ============
    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/data_pipeline",
        description="PostgreSQL connection string (asyncpg driver)",
    )

    # Connection pool settings
    # Adjust based on expected load and PostgreSQL max_connections
    # Formula: (max_connections / instances) to avoid "too many connections" errors
    db_pool_size: int = 5  # Number of connections to keep open
    db_max_overflow: int = 10  # Extra connections beyond pool_size when demand spikes
    db_pool_timeout: int = 30  # Seconds to wait for available connection before raising an error  # noqa: E501
    db_pool_recycle: int = 1800  # Recycle connections after 30 min (avoid stale)

    # Echo SQL statements for debugging (disable in production)
    db_echo: bool = Field(
        default=False,
        description="Enable SQL query logging",
    )

    # ============ App ============
    app_name: str = Field(
        default="Data Pipeline API (async)",
        description="Application name",
    )
    app_version: str = Field(
        default="1.0.0",
        description="Application version",
    )
    environment: str = Field(
        default="development",
        description="Execution environment: development, testing, staging, production",
    )

    log_level: str = Field(
        default="INFO",
        description="Global logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    trusted_hosts: str = Field(
        default="localhost,127.0.0.1,[::1],test,ingestor,ingestor:8000",
        description=(
            "Comma-separated allowed Host header values for TrustedHostMiddleware. "
            "Use '*' only in controlled development environments."
        ),
    )

    log_format: str = Field(
        default="text",
        description="Logging format: text or json",
    )

    # Dependency library logging levels (reduce noise from verbose libs)
    log_sqlalchemy_level: str | None = Field(
        default=None,
        description="SQLAlchemy logging level (default: WARNING if not set)",
    )

    log_httpx_level: str | None = Field(
        default=None,
        description="HTTPX logging level (default: WARNING if not set)",
    )

    log_asyncio_level: str | None = Field(
        default=None,
        description="Asyncio logging level (default: WARNING if not set)",
    )

    # ============ Documentation Auth ============
    docs_username: str | None = Field(
        default=None,
        description="Username for docs authentication. If None, docs are public. Set to enable.",
    )

    docs_password: str | None = Field(
        default=None,
        description="Password for docs authentication. If None, docs are public. Set to enable.",
    )

    # ============ API Auth — v1 (Token + Session) ============
    api_v1_bearer_token: str | None = Field(
        default=None,
        description="Simple bearer token for v1 endpoints. "
        " If set, endpoints require Authorization: Bearer <token>",
    )

    token_expiry_hours: int = Field(
        default=24,
        description="Token expiration time in hours (for session tokens)",
    )

    # ============ API Auth — v2 (JWT) ============
    jwt_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(48),
        description="Secret key for JWT signing. Set JWT_SECRET via env/secrets manager for stable tokens across restarts.",  # noqa: E501
    )

    jwt_previous_secrets: str = Field(
        default="",
        description=(
            "Comma-separated previous JWT signing secrets accepted for token verification "
            "during rotation windows. New tokens are always signed with JWT_SECRET."
        ),
    )

    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm (HS256, RS256, etc.)",
    )

    jwt_expiry_minutes: int = Field(
        default=30,
        description="JWT access token expiration in minutes",
    )

    jwt_refresh_ttl_days: int = Field(
        default=7,
        description="Refresh token time-to-live in days",
    )

    # ============ Internal Service Auth (M2M) ============
    internal_jwt_secret: str | None = Field(
        default=None,
        description=(
            "Shared secret for service-to-service JWT signing. "
            "Required on internal-only routes. "
            "Set via INTERNAL_JWT_SECRET env variable or Secrets Manager."
        ),
    )

    # ============ Cache Backend ============
    cache_url: str = Field(
        default="redis://localhost:6379/0",
        description="Cache backend connection URL",
    )

    cache_enabled: bool = Field(
        default=False,
        description="Enable cache backend. Disabled by default (tests use fakeredis)",
    )

    # ============ Event Broker / Redpanda ============
    broker_url: str = Field(
        default="localhost:9092",
        description="Broker bootstrap servers (comma-separated). Override with BROKER_URL.",
    )

    broker_enabled: bool = Field(
        default=False,
        description="Enable broker event publishing. Disabled by default (safe for tests w/o broker).",  # noqa: E501
    )

    broker_strangler_adapter_enabled: bool = Field(
        default=False,
        description=(
            "Enable strangler adapter path for broker publishing. "
            "When False, the legacy direct producer path is used."
        ),
    )

    # ============ MongoDB ============
    mongo_url: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URL",
    )

    mongo_db_name: str = Field(
        default="datazoo",
        description="MongoDB database name",
    )

    mongo_enabled: bool = Field(
        default=False,
        description="Enable MongoDB storage. Disabled by default (safe for tests w/o MongoDB).",
    )

    # ============ OpenTelemetry ============
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry distributed tracing. Disabled by default.",
    )

    otel_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP gRPC endpoint for trace export (e.g., http://jaeger:4317).",
    )

    otel_service_name: str = Field(
        default="ingestor",
        description="Service name shown in Jaeger / OTel collector UI.",
    )

    # ============ Sentry (error tracking) ============
    sentry_dsn: str | None = Field(
        default=None,
        description="Sentry DSN for application error tracking.",
    )

    sentry_enabled: bool = Field(
        default=False,
        description="Enable Sentry SDK initialization.",
    )

    sentry_traces_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sentry performance trace sampling rate (0.0-1.0).",
    )

    sentry_profiles_sample_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sentry profiling sample rate (0.0-1.0).",
    )

    sentry_send_default_pii: bool = Field(
        default=False,
        description="Whether Sentry should send default PII context.",
    )

    # ============ Background workers (Pillar 5) ============
    background_workers_enabled: bool = Field(
        default=False,
        description="Enable in-process background worker queue for large batch ingestion.",
    )

    background_worker_count: int = Field(
        default=BACKGROUND_WORKER_COUNT_DEFAULT,
        ge=1,
        le=32,
        description="Number of async worker tasks consuming the in-process queue.",
    )

    background_worker_queue_size: int = Field(
        default=BACKGROUND_WORKER_QUEUE_SIZE_DEFAULT,
        ge=1,
        le=10000,
        description="Maximum number of queued background jobs before rejecting new submissions.",
    )

    background_max_tracked_tasks: int = Field(
        default=BACKGROUND_MAX_TRACKED_TASKS_DEFAULT,
        ge=10,
        le=50000,
        description="Maximum completed task statuses kept in memory for status lookups.",
    )

    # ============ Notifications & emailing (Pillar 8) ============
    notifications_enabled: bool = Field(
        default=False,
        description="Enable notification dispatching for operational events.",
    )

    notification_default_channels: str = Field(
        default="slack,telegram",
        description="Comma-separated default channels: slack, telegram, webhook, email.",
    )

    notification_http_timeout_seconds: int = Field(
        default=NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=60,
        description="HTTP timeout (seconds) for notification provider calls.",
    )

    # Slack incoming webhook
    notification_slack_webhook_url: str | None = Field(
        default=None,
        description="Slack incoming webhook URL for channel alerts.",
    )

    # Telegram bot alerts
    notification_telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram bot token for chat notifications.",
    )
    notification_telegram_chat_id: str | None = Field(
        default=None,
        description="Telegram chat ID for target channel/group/user.",
    )

    # Generic webhook integration (can be Jira automation/webhooks)
    notification_webhook_url: str | None = Field(
        default=None,
        description="Generic webhook destination for alert payloads.",
    )

    # Transactional email provider (Resend API)
    notification_email_provider: str = Field(
        default="resend",
        description="Transactional email provider. Currently supported: resend.",
    )
    notification_resend_api_key: str | None = Field(
        default=None,
        description="Resend API key for email delivery.",
    )
    notification_email_from: str | None = Field(
        default=None,
        description="Sender email address for notification emails.",
    )
    notification_email_to: str | None = Field(
        default=None,
        description="Comma-separated recipient emails for operational alerts.",
    )

    # ============ Embeddings & vector search (Pillar 9) ============
    inference_url: str = Field(
        default="http://localhost:8001",
        description="Base URL for the inference service that handles embeddings/semantic search.",
    )

    vector_search_collection: str = Field(
        default=VECTOR_SEARCH_DEFAULT_COLLECTION,
        description="Default inference collection used for semantic observation search.",
    )

    vector_search_http_timeout_seconds: int = Field(
        default=VECTOR_SEARCH_HTTP_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=60,
        description="HTTP timeout (seconds) for AI gateway index and search requests.",
    )
    scraper_timeout: int = Field(
        default=SCRAPER_HTTP_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=300,
        description="Timeout (seconds) for HTTP scrapers.",
    )

    # ============ OpenAPI / Swagger ============
    openapi_servers: str = Field(
        default="http://127.0.0.1:8000,https://127.0.0.1/api",
        description=(
            "Comma-separated OpenAPI server URLs for Swagger UI. "
            "Set OPENAPI_SERVERS to override. "
            "Default: http://127.0.0.1:8000 (direct HTTP) and "
            "https://127.0.0.1/api (edge proxy HTTPS)."
        ),
    )

    # ============ LLM Integration (Phase 2) ============
    openai_enabled: bool = Field(
        default=False,
        description="Enable OpenAI-based observation analysis. Requires OPENAI_API_KEY.",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for observation analysis.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use for analysis.",
    )
    openai_model_deep: str = Field(
        default="gpt-4o",
        description="OpenAI model to use for deep analysis.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",  # Load from .env (local dev)
        env_file_encoding="utf-8",
        case_sensitive=False,  # DATABASE_URL and database_url both work
        extra="ignore",  # Ignore unknown env vars
    )


# Singleton instance
settings = Settings()
