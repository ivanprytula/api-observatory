"""Inference service settings — reads from environment/`.env` only.

Kept separate from `services.ingestor.config` deliberately: this is an
independently-deployable service and must not import ingestor's settings
module (would couple deployment/config lifecycles across services).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dedicated Postgres instance (port 5433, db "api_obs_inference") — not shared with
    # the ingestor's "api_obs_ingestor" database. See ADR-015.
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5433/api_obs_inference"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # fastembed model — BAAI/bge-small-en-v1.5 is fastembed's own default:
    # small (~130MB), CPU-fast via ONNX Runtime, 384-dim embeddings. Swap via
    # env var, not code, if a different model is needed; embedding_dim must
    # match the model's output.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    log_level: str = "INFO"

    request_timeout_seconds: int = Field(default=30, ge=1, le=300)

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "api-obs-inference"


settings = Settings()
