"""add versioned accepted contract baselines

Revision ID: contract_baselines_01
Revises: dependency_incidents_01
Create Date: 2026-07-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "contract_baselines_01"
down_revision: str | None = "dependency_incidents_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create baseline history/current-candidate storage and backfill existing sources."""
    op.create_table(
        "contract_baselines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("baseline_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("promoted_from_baseline_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_key", sa.String(length=128), nullable=True),
        sa.Column("accepted_by", sa.String(length=128), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.Column("acceptance_note", sa.String(length=512), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("candidate_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("candidate_schema_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "candidate_observation_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("candidate_drift_event_id", sa.Integer(), nullable=True),
        sa.Column("candidate_first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("candidate_last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_contract_baselines_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "version",
            name="uq_contract_baselines_source_version",
        ),
    )
    op.create_index(
        "ix_contract_baselines_active_key",
        "contract_baselines",
        ["active_key"],
        unique=True,
    )
    op.create_index(
        "ix_contract_baselines_baseline_snapshot",
        "contract_baselines",
        ["baseline_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_contract_baselines_source_status",
        "contract_baselines",
        ["source_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_contract_baselines_tenant_status",
        "contract_baselines",
        ["tenant_id", "status"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO contract_baselines (
                source_id,
                tenant_id,
                baseline_snapshot_id,
                version,
                status,
                active_key,
                accepted_by,
                accepted_at,
                candidate_observation_count,
                created_at,
                updated_at
            )
            SELECT
                first_snapshot.source_id,
                source_profiles.tenant_id,
                first_snapshot.snapshot_id,
                1,
                'active',
                'source:' || CAST(first_snapshot.source_id AS VARCHAR),
                'system:migration',
                CURRENT_TIMESTAMP,
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM (
                SELECT source_id, MIN(id) AS snapshot_id
                FROM contract_snapshots
                GROUP BY source_id
            ) AS first_snapshot
            JOIN source_profiles ON source_profiles.id = first_snapshot.source_id
            """
        )
    )


def downgrade() -> None:
    """Remove accepted baseline and candidate state."""
    op.drop_index(
        "ix_contract_baselines_tenant_status", table_name="contract_baselines"
    )
    op.drop_index(
        "ix_contract_baselines_source_status", table_name="contract_baselines"
    )
    op.drop_index(
        "ix_contract_baselines_baseline_snapshot", table_name="contract_baselines"
    )
    op.drop_index(
        "ix_contract_baselines_active_key", table_name="contract_baselines"
    )
    op.drop_table("contract_baselines")
