"""MCP server settings — reads from environment/`.env` only.

Kept separate from `services.ingestor.config` deliberately: this is an
independently-deployable process (a stdio MCP server, not a FastAPI app) and
must not import the ingestor's settings module or internals — it only ever
talks to the ingestor over its real HTTP API, the same way any other API
client would.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base URL of the running ingestor API this MCP server calls.
    ingestor_url: str = "http://localhost:8000"

    # Credentials for the dedicated `mcp-service` account (see
    # scripts/register_mcp_service_user.py) — no default password, must be
    # supplied via env/`.env` so it never lands in source control.
    mcp_service_username: str = "mcp-service"
    mcp_service_password: str

    http_timeout_seconds: float = 10.0

    # Mirrors the ingestor's own `jwt_expiry_minutes` (config.py) so this
    # client can compute its own token expiry deadline without decoding the
    # JWT itself (no pyjwt dependency needed here).
    jwt_expiry_minutes: int = 30
    # Re-login this many seconds *before* the computed deadline, not at it —
    # avoids a tool call racing the exact expiry instant.
    token_refresh_skew_seconds: int = 60

    log_level: str = "INFO"


settings = Settings()
