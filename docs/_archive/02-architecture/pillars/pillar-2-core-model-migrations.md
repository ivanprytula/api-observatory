# Pillar 2: Core Data Model & Migrations — Implementation Guide

Track: C — Architecture and Platform Strategy

## Status: ✅ Complete (v1.0 Foundation)

This guide documents the implementation of the Core Data Model & Migrations pillar, ensuring data model correctness and migration hygiene.

---

## Deliverables

### 1. ✅ Data Model Finalized

**File**: [ingestor/models.py](../../services/ingestor/models.py)

- [x] `Record` model with TimestampMixin (soft-delete support)
- [x] `ProcessedEvent` model with Kafka metadata and idempotency tracking
- [x] All columns defined with correct types (JSON, Boolean, DateTime, String)
- [x] Indexes defined inline via `__table_args__`
- [x] Unique constraints defined (`uq_records_source_timestamp`)

### 2. ✅ Alembic Migrations Complete

**Directory**: [alembic/versions/](../../alembic/versions/)

- [x] **Migration 1**: Initial schema (records, processed_events tables)
- [x] **Migration 2**: Partial index on `(source, deleted_at IS NULL)`
- [x] **Migration 3**: Indexes on timestamp, processed columns
- [x] **Migration 4**: Add processed_at column to observations
- [x] **Migration 5**: Unique constraint on (source, timestamp) + DLQ indexes
- [x] **Migration 6**: Materialized views + monthly range partitioning on observations_archive

**Key Features**:

- Online migrations (no downtime)
- Materialized views for analytics dashboards
- Monthly partitioned archive table for data retention
- pgvector extension for future ML features

### 3. ✅ Test Infrastructure for Migrations

**File**: [tests/conftest.py](../../tests/conftest.py)

- [x] `apply_migrations()` fixture (session-scoped, PostgreSQL only)
  - Runs `alembic upgrade head` before tests
  - Runs `alembic downgrade base` after tests
  - Preserves migrated schema (materialized views, partitions)
- [x] `_clear_observations()` helper (TRUNCATE CASCADE for Postgres, DELETE for SQLite)
- [x] `db` fixture uses truncate-only cleanup (non-destructive)
- [x] **Fixed**: SessionLocal unbound error in `postgresql_async_session_isolated` fixture

### 4. ✅ Migration Verification CI Job

**File**: [CI workflow](../../.github/workflows/ci.yml)

Validates:

- Fresh migrations from scratch (base → head)
- All schema objects created (views, partitions, extensions)
- Migration idempotency (downgrade → upgrade)
- Constraint enforcement (unique, primary key violations caught)
- Works across PostgreSQL 15, 16, 17

**Test Coverage**:

```bash
✓ Fresh migrations (base -> head)
✓ pgvector extension installed
✓ Materialized views created (observations_hourly_stats)
✓ Partitioned table created (observations_archive with monthly partitions)
✓ Migration idempotency verified
✓ Constraint enforcement (unique, not null)
✓ Table inserts successful
```

### 5. ✅ Data Retention & Archival Policy

**File**: Data Retention and Archival guide

- [x] Three-tier retention strategy (Hot/Warm/Cold)
- [x] Archival jobs defined (Tier 1→2, Tier 2→3, soft-delete cleanup)
- [x] Soft-delete grace period (90 days before hard delete)
- [x] Cold storage export strategy (S3/GCS with object expiration)
- [x] GDPR / compliance considerations
- [x] Query filtering patterns (exclude deleted_at IS NULL by default)

### 6. ✅ Schema Integrity Tests

**File**: [tests/integration/schema/test_schema_integrity.py](../../tests/integration/schema/test_schema_integrity.py)

**Test Classes**:

- `TestRecordsTableIndexes`: Verify all indexes exist (active_source, timestamp, processed)
- `TestRecordsTableConstraints`: Verify unique constraint on (source, timestamp)
- `TestProcessedEventsTableIndexes`: Verify idempotency_key, status, offset indexes
- `TestProcessedEventsConstraints`: Verify idempotency_key uniqueness
- `TestMaterializedViews`: Verify observations_hourly_stats view exists and is queryable
- `TestPartitionedTables`: Verify observations_archive partitions created
- `TestSoftDeleteColumns`: Verify created_at, updated_at, deleted_at on all tables
- `TestExtensions`: Verify pgvector extension

**Command**:

```bash
pytest tests/integration/schema/ -v --tb=short
```

### 7. ✅ Index Optimization & Hotspot Analysis

**File**: Index Optimization guide

**Key Findings**:

- ⚠️ `ix_records_processed` (boolean column) has poor selectivity — low cardinality
- 📌 Missing composite index: `ix_records_unprocessed_by_source_timestamp` (Recommended)
  - Reduces scan from 95K to 5K rows for unprocessed records query
- 📌 Missing composite index: `ix_events_pending_by_topic` (Recommended)
  - Filters pending events by topic efficiently

**Recommendations**:

1. Add partial index on unprocessed records by source & timestamp
2. Add partial index on pending events by topic
3. Monitor index usage with `pg_stat_statements`
4. Benchmark before/after to validate improvements

---

## Implementation Checklist

### Data Model

- [x] Models defined with SQLAlchemy 2.0 syntax (`Mapped`, `mapped_column`)
- [x] Indexes defined inline with `__table_args__`
- [x] Unique constraints with descriptive names
- [x] Soft-delete mixin (`TimestampMixin`) applied to all versioned tables
- [x] Enums for status fields (e.g., `pending`, `processing`, `completed`, `failed`, `dead_letter`)

### Migrations

- [x] All migrations follow naming convention: `YYYYMMDD_HHMMSS_HASH_slug.py`
- [x] Each migration has `upgrade()` and `downgrade()` functions
- [x] Data operations (inserts/deletes) in migrations are optional (prefer app-level)
- [x] Migrations are idempotent (safe to re-run)
- [x] Downgrade removes only what upgrade created (e.g., no `DROP TABLE IF EXISTS` on partial drops)

### Testing

- [x] Migration tests run in CI on PostgreSQL 15, 16, 17
- [x] Schema integrity tests verify all indexes and constraints
- [x] Unique constraint violations tested
- [x] Soft-delete columns verified on all tables
- [x] Materialized views and partitions validated

### Documentation

- [x] Data retention policy documented (3 tiers, archival jobs, grace periods)
- [x] Index hotspots identified and recommendations provided
- [x] Query patterns documented (common filters, ranges)
- [x] Migration runbook provided for operators

---

## Quick Start

### Run All Pillar 2 Validations

```bash
# 1. Run migration verification in CI (GitHub Actions)
#    Triggered on PR: validates migrations across PostgreSQL 15/16/17
gh workflow run ci.yml

# 2. Run schema integrity tests locally
pytest tests/integration/schema/ -v

# 3. Inspect current migrations
uv run alembic current
uv run alembic history

# 4. Preview next migration (without applying)
uv run alembic upgrade --sql head
```

### Common Operations

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "add_column_X"

# Apply migrations to production database
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Verify schema matches models
uv run alembic check
```

---

## Known Limitations & Future Work

### Limitations (v1.0)

1. **No sharding on observations table** — single-instance deployment only
   - Future: Implement list partitioning by source hash for horizontal scaling
2. **Manual archival jobs** — not yet scheduled
   - Future: Integrate APScheduler + Celery for automated tier migration
3. **No query-time soft-delete filtering** — CRUD layer must apply filters
   - Future: Implement database views (`v_active_records`) for automatic filtering
4. **Limited index optimization** — baseline indexes present, hotspot mitigations pending
   - Future: Add recommended composite indexes after benchmarking

### Planned Enhancements (Phase 1, Week 1–2)

- [ ] Create migration for recommended composite indexes
- [ ] Implement archival jobs (ingestor/jobs/)
- [ ] Add scheduler integration (APScheduler)
- [ ] Create database views for soft-delete filtering
- [ ] Benchmark query performance before/after index optimization

---

## Success Criteria (Pillar 2 Completion)

- [x] All models defined with correct relationships and constraints
- [x] Migrations tested across PostgreSQL versions
- [x] Schema objects (views, partitions, extensions) verified
- [x] Soft-delete pattern documented and enforced
- [x] Data retention policy defined (3-tier strategy)
- [x] Index optimization recommendations provided
- [x] Tests verify schema integrity (indexes, constraints, objects)

---

## Related Pillars

- **Pillar 1 — Tests & CI Stabilization**: Migration tests in the main CI workflow (`ci.yml`)
- **Pillar 3 — Reliable Ingestion**: Uses models/constraints for idempotency
- **Pillar 4 — Observability**: Materialized view for hourly stats dashboard
- **Pillar 5 — Background Processing**: Archive jobs run as scheduled tasks

---

## References

- [SQLAlchemy 2.0 ORM Mapped API](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html)
- [Alembic Migrations](https://alembic.sqlalchemy.org/)
- [PostgreSQL Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [Soft Delete Pattern](https://en.wikipedia.org/wiki/Soft_delete)
