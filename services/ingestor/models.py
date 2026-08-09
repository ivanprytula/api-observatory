"""ORM models (async stack — identical structure to sync, different Base)."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.utils import _utcnow
from services.ingestor.database import Base


class TimestampMixin:
    """Adds created_at, updated_at, and deleted_at to any model.

    - created_at: set once on INSERT, never changes
    - updated_at: set on INSERT and refreshed on every UPDATE
    - deleted_at: NULL until soft-deleted; non-NULL means logically deleted
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProcessedEvent(Base, TimestampMixin):
    """Tracks consumed Kafka events with processing state and idempotency.

    Industry pattern: Event persistence with status tracking enables:
    - Replay from failures (track offset)
    - Deduplication (idempotency_key prevents double-processing)
    - DLQ routing (failed events send to dead_letter_queue)
    - Audit trail (complete lifecycle visible in database)
    """

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("ix_events_idempotency_key", "idempotency_key", unique=True),
        Index("ix_events_status", "status"),
        Index("ix_events_kafka_offset", "kafka_offset"),
        Index("ix_events_dead_letter_queue", "dead_letter_queue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Kafka metadata
    kafka_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    kafka_partition: Mapped[int] = mapped_column(Integer, nullable=False)
    kafka_offset: Mapped[int] = mapped_column(Integer, nullable=False)

    # Event deduplication (industry standard: idempotency keys prevent double-processing)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # Event payload storage
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g., "observation.created"
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Processing state tracking
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )  # pending → processing → completed | failed | dead_letter
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Error tracking for failed events
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Dead letter queue indicator
    dead_letter_queue: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    dlq_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps from TimestampMixin: created_at, updated_at, deleted_at
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OutboxEvent(Base, TimestampMixin):
    """Transactional outbox event for reliable publish-after-commit workflows."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_published_at", "published_at"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_events_tenant_id", "tenant_id"),
        Index("ix_outbox_events_idempotency_key", "idempotency_key", unique=True),
        Index(
            "ix_outbox_events_publish_due",
            "published_at",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)


class InboxConsumption(Base, TimestampMixin):
    """Inbox deduplication observation keyed by (consumer_name, message_id)."""

    __tablename__ = "inbox_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "consumer_name",
            "message_id",
            name="uq_inbox_consumptions_consumer_message",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', "
            "'completed_with_dead_letters', 'dead_letter')",
            name="ck_inbox_consumptions_status",
        ),
        Index("ix_inbox_consumptions_consumer_name", "consumer_name"),
        Index("ix_inbox_consumptions_processed_at", "processed_at"),
        Index(
            "ix_inbox_consumptions_claim",
            "status",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="processing", nullable=False
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationDelivery(Base, TimestampMixin):
    """Durable per-channel delivery, retry, and terminal outcome state."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "channel",
            name="uq_notification_deliveries_message_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'retry_scheduled', "
            "'delivered', 'dead_letter')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 3",
            name="ck_notification_deliveries_attempt_count",
        ),
        Index(
            "ix_notification_deliveries_retry_due",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        Index(
            "ix_notification_deliveries_tenant_created",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_notification_deliveries_source_created",
            "source_id",
            "created_at",
        ),
        Index("ix_notification_deliveries_incident_id", "incident_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inbox_consumption_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    incident_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"
    __table_args__ = (
        Index(
            "ix_observations_active_source",
            "source",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_observations_timestamp", "timestamp"),
        Index("ix_observations_processed", "processed"),
        UniqueConstraint(
            "source", "timestamp", name="uq_observations_source_timestamp"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Observation id={self.id} source={self.source!r}>"


class ObservationArchive(Base):
    """Warm-tier copy of an observation removed from the hot table."""

    __tablename__ = "observations_archive"
    __table_args__ = (
        Index("ix_observations_archive_timestamp", "timestamp"),
        Index("ix_observations_archive_archived_at", "archived_at"),
        Index("ix_observations_archive_tenant_id", "tenant_id"),
    )

    # The original ID remains the primary key, making copy verification idempotent.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )


class Tenant(Base, TimestampMixin):
    """Minimal tenant for multi-tenancy.

    MVP scope: one personal tenant per user, auto-provisioned on registration.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        Index("ix_tenants_name", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} name={self.name!r}>"


class User(Base, TimestampMixin):
    """Basic user model for authentication and RBAC role assignment.

    This is intentionally minimal for the current pillar scope:
    - identity fields (username, email)
    - credential field (password_hash)
    - coarse role field (viewer/writer/tenant_admin/admin)
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_role", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


class UserTenant(Base, TimestampMixin):
    """Junction table for many-to-many user-to-tenant mapping.

    Used primarily for the 'Active Tenant Context' pattern, allowing a
    tenant_admin to securely impersonate any of their assigned tenants.
    """

    __tablename__ = "user_tenants"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<UserTenant user_id={self.user_id} tenant_id={self.tenant_id}>"


class SourceProfile(Base, TimestampMixin):
    """Registry entry for an external API / data source being ingested.

    Centralises reliability metadata (SLA targets, quota, cost) and
    auth policy per source so all ingestion workers can share a single
    source of truth without hard-coding connection details.
    """

    __tablename__ = "source_profiles"
    __table_args__ = (
        Index("ix_source_profiles_name", "name", unique=True),
        Index(
            "ix_source_profiles_active",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_source_profiles_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    health_check_path: Mapped[str] = mapped_column(
        String(255), default="/health", nullable=False
    )
    probe_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_threshold_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    incident_failure_threshold: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False
    )
    incident_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, default=900, nullable=False
    )
    # Timestamps from TimestampMixin: created_at, updated_at, deleted_at

    def __repr__(self) -> str:
        return f"<SourceProfile id={self.id} name={self.name!r}>"


class DependencyIncident(Base, TimestampMixin):
    """Tenant-scoped lifecycle for an actionable dependency failure.

    ``active_key`` is populated while an incident is open or acknowledged and
    cleared on resolution. Its unique index makes concurrent duplicate opens
    fail safely while allowing a later incident with the same fingerprint.
    """

    __tablename__ = "dependency_incidents"
    __table_args__ = (
        Index("ix_dependency_incidents_tenant_status", "tenant_id", "status"),
        Index("ix_dependency_incidents_source_status", "source_id", "status"),
        Index("ix_dependency_incidents_last_seen_at", "last_seen_at"),
        Index("ix_dependency_incidents_active_key", "active_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    guidance: Mapped[str] = mapped_column(String(2048), nullable=False)
    trigger_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<DependencyIncident id={self.id} source_id={self.source_id} "
            f"trigger_type={self.trigger_type!r} status={self.status!r}>"
        )


class ContractSnapshot(Base, TimestampMixin):
    """Schema snapshot for a source payload contract at a point in time."""

    __tablename__ = "contract_snapshots"
    __table_args__ = (
        Index("ix_contract_snapshots_source_id", "source_id"),
        Index("ix_contract_snapshots_fingerprint", "schema_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    compatibility_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0
    )
    snapshot_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ContractSnapshot id={self.id} source_id={self.source_id} "
            f"fingerprint={self.schema_fingerprint[:8]}...>"
        )


class ContractBaseline(Base, TimestampMixin):
    """Versioned accepted contract baseline and its current candidate state."""

    __tablename__ = "contract_baselines"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "version",
            name="uq_contract_baselines_source_version",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_contract_baselines_status",
        ),
        Index("ix_contract_baselines_source_status", "source_id", "status"),
        Index("ix_contract_baselines_tenant_status", "tenant_id", "status"),
        Index("ix_contract_baselines_baseline_snapshot", "baseline_snapshot_id"),
        Index("ix_contract_baselines_active_key", "active_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    promoted_from_baseline_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    accepted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    acceptance_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidate_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_schema_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    candidate_observation_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    candidate_drift_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    candidate_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<ContractBaseline id={self.id} source_id={self.source_id} "
            f"version={self.version} status={self.status!r}>"
        )


class DriftEvent(Base, TimestampMixin):
    """Confirmed schema drift from an accepted baseline to a candidate snapshot."""

    __tablename__ = "drift_events"
    __table_args__ = (
        Index("ix_drift_events_source_id", "source_id"),
        Index("ix_drift_events_event_type", "event_type"),
        Index("ix_drift_events_severity", "severity"),
        Index("ix_drift_events_current_snapshot_id", "current_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    added_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    removed_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    type_changed_fields: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    compatibility_score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DriftEvent id={self.id} source_id={self.source_id} "
            f"event_type={self.event_type!r} severity={self.severity!r}>"
        )


class AgentRun(Base, TimestampMixin):
    """AI triage run for an incident-worthy Observation, with human-in-the-loop review.

    Domain-specific analysis output (root cause / severity / recommended action)
    plus a reviewer audit trail — replaces the generic sentiment-oriented
    ObservationClassification schema for incidents raised from drift events.

    Status lifecycle: pending -> running -> awaiting_review -> approved | rejected
    (or -> failed at any point).
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_observation_id", "observation_id"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    root_cause_hypothesis: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    severity_assessment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AgentRun id={self.id} observation_id={self.observation_id} "
            f"status={self.status!r}>"
        )


class ApiKey(Base, TimestampMixin):
    """Tenant-scoped API key with fine-grained permission scopes.

    Key storage pattern (never store plaintext):
    - key_prefix: first 8 hex chars of the random key — used for O(1) DB lookup.
    - key_hash: SHA-256 of the full raw key — used for constant-time verification.

    Scopes are stored as a JSON list of strings, e.g.:
    ``["observations:read", "observations:write", "sources:read"]``

    The full raw key is returned only once (at creation time) and never stored.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_prefix", "key_prefix"),
        Index("ix_api_keys_tenant_id", "tenant_id"),
        Index("ix_api_keys_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ApiKey id={self.id} prefix={self.key_prefix!r} "
            f"tenant_id={self.tenant_id} active={self.is_active}>"
        )


class SecurityAuditEvent(Base):
    """Append-only security audit stream with tamper-evident hash chaining.

    Rows are immutable by convention: insert-only from the application layer.
    Each event stores the previous event hash and its own hash so downstream
    verifiers can detect gaps or mutation.
    """

    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_created_at", "created_at"),
        Index("ix_security_audit_events_event_type", "event_type"),
        Index("ix_security_audit_events_tenant_id", "tenant_id"),
        Index("ix_security_audit_events_actor_type", "actor_type"),
        Index("ix_security_audit_events_actor_id", "actor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prev_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityAuditEvent id={self.id} event_type={self.event_type!r} "
            f"decision={self.decision!r}>"
        )


class AbuseSignal(Base, TimestampMixin):
    """Mutable observation of a detected abuse pattern.

    Captures both automated detector findings and manually raised signals.
    Unlike SecurityAuditEvent (append-only, hash-chained), AbuseSignal is
    a mutable operational observation: it can be resolved, annotated, and queried
    for open/closed state.

    Signal lifecycle: open → resolved (set resolved_at + resolved_by).
    """

    __tablename__ = "abuse_signals"
    __table_args__ = (
        Index("ix_abuse_signals_signal_type", "signal_type"),
        Index("ix_abuse_signals_actor", "actor_type", "actor_id"),
        Index("ix_abuse_signals_severity", "severity"),
        Index("ix_abuse_signals_tenant_id", "tenant_id"),
        Index("ix_abuse_signals_resolved_at", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Classification
    signal_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # noisy_source | suspicious_key | burst_abuse | credential_stuffing | ip_rotation
    actor_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # api_key | source_id | ip_address | tenant_id
    actor_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # the key prefix, source name, IP, or tenant ID
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # low | medium | high | critical
    detection_rule: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # quota_exceeded | auth_failure_spike | multi_ip_key | error_rate_spike | rapid_enumeration

    # Machine-readable evidence (counts, thresholds, window)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Action taken by the detector or operator
    action_taken: Mapped[str] = mapped_column(
        String(32), nullable=False, default="logged"
    )  # logged | rate_limited | blocked | alerted

    # Context
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Resolution lifecycle
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AbuseSignal id={self.id} signal_type={self.signal_type!r} "
            f"actor={self.actor_type}:{self.actor_id!r} severity={self.severity!r}>"
        )


class ProviderHealthSample(Base, TimestampMixin):
    """Single health probe result for an API provider / source.

    Each row represents one real or synthetic probe: the call succeeded or
    failed, how long it took, and optional context (HTTP status, region).
    The scorecard compute layer aggregates these rows to derive uptime %,
    p50/p95 latency, and error-budget burn rate.
    """

    __tablename__ = "provider_health_samples"
    __table_args__ = (
        Index("ix_phs_source_id", "source_id"),
        Index("ix_phs_sampled_at", "sampled_at"),
        Index("ix_phs_source_sampled", "source_id", "sampled_at"),
        Index("ix_phs_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ProviderHealthSample id={self.id} source_id={self.source_id} "
            f"sampled_at={self.sampled_at!r} success={self.is_success}>"
        )
