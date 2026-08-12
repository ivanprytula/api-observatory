# Data Retention & Archival Strategy

Track: C — Architecture and Platform Strategy

## Overview

This document defines the data retention and archival policy for the Data Pipeline platform. The strategy balances operational needs (recent data performance), compliance (audit trails), and cost efficiency (archival storage).

---

## Retention Tiers

### Tier 1: Active Observations (0–30 days)

- **Purpose**: Fast queries, real-time dashboards, API responses
- **Storage**: Main `observations` table (hot tier, optimized for OLTP queries)
- **Indexes**: All active indexes (partial indexes on `deleted_at IS NULL`)
- **Backups**: Full hourly snapshots, kept for 7 days
- **SLA**: P50 <50ms, P99 <500ms

### Tier 2: Warm Archive (30–90 days)

- **Purpose**: Historical analysis, compliance lookups
- **Storage**: Partitioned `observations_archive` table (range-partitioned by month)
- **Indexes**: Limited indexes (timestamp range lookups only)
- **Backups**: Daily snapshots, kept for 30 days
- **Query Pattern**: Batch/analytical queries only
- **SLA**: P50 <1s, P99 <10s

### Tier 3: Cold Archive (90+ days)

- **Purpose**: Regulatory compliance, long-term audit trail
- **Storage**: Cold storage (S3/GCS with object expiration policy)
- **Indexes**: None (sequential scans only)
- **Backups**: Single daily snapshot, kept for 7 days
- **Query Pattern**: Rare compliance audits (typically 1–2x per year)
- **SLA**: Availability is secondary; focus on cost optimization

---

## Archival Jobs & Automation

### Job 1: Daily Tier 1 → Tier 2 Migration (runs 02:00 UTC)

**Purpose**: Move observations older than 30 days from `observations` → `observations_archive`

**Logic**:

```sql
-- Nightly job: move observations older than 30 days to archive table
INSERT INTO observations_archive (id, source, timestamp, raw_data, tags, processed, processed_at, created_at, updated_at, deleted_at)
SELECT id, source, timestamp, raw_data, tags, processed, processed_at, created_at, updated_at, deleted_at
FROM observations
WHERE created_at < NOW() - INTERVAL '30 days'
  AND deleted_at IS NULL  -- Only archive non-deleted observations
ON CONFLICT (id, timestamp) DO NOTHING;  -- Idempotent

-- Delete from hot tier
DELETE FROM observations
WHERE created_at < NOW() - INTERVAL '30 days'
  AND deleted_at IS NULL;
```

**Frequency**: Nightly at 02:00 UTC
**Duration**: <5min (indexed on `created_at`)
**Idempotency**: ON CONFLICT DO NOTHING ensures safe re-runs

### Job 2: Weekly Tier 2 → Tier 3 Backup Export (runs Sundays 01:00 UTC)

**Purpose**: Export observations older than 90 days to cold storage (S3/GCS)

**Logic**:

```bash
# Pseudo-code: export observations older than 90 days
psql -d data_pipeline -c "
  COPY (
    SELECT * FROM observations_archive
    WHERE timestamp < NOW() - INTERVAL '90 days'
  ) TO STDOUT FORMAT CSV HEADER
" | gzip | aws s3 cp - "s3://data-pipeline-archive/$(date +%Y-%m-%d).csv.gz"

# Delete from warm tier after successful export
psql -d data_pipeline -c "
  DELETE FROM observations_archive
  WHERE timestamp < NOW() - INTERVAL '90 days'
"
```

**Frequency**: Weekly (Sundays at 01:00 UTC)
**Retention in S3**: Object expiration policy (e.g., delete after 7 years for compliance)
**Monitoring**: Alert if export fails or takes >30min

### Job 3: Soft-Deleted Observations Cleanup (runs daily 03:00 UTC)

**Purpose**: Physically remove soft-deleted observations after grace period

**Logic**:

```sql
-- Remove soft-deleted observations older than 90 days
DELETE FROM observations
WHERE deleted_at IS NOT NULL
  AND deleted_at < NOW() - INTERVAL '90 days';

DELETE FROM observations_archive
WHERE deleted_at IS NOT NULL
  AND deleted_at < NOW() - INTERVAL '90 days';
```

**Frequency**: Daily at 03:00 UTC
**Grace Period**: 90 days (allows recovery from accidental deletes)
**Idempotency**: Safe to run multiple times

---

## Soft-Delete Behavior

### Design Pattern

All tables with `deleted_at` column follow a "soft delete" pattern:

- **Logical deletion**: Set `deleted_at = NOW()` instead of removing the row
- **Audit trail**: Complete lifecycle remains queryable
- **Recovery**: Undelete by setting `deleted_at = NULL`
- **Compliance**: Audit logs always include deleted records

### Query Filtering

By default, queries should **exclude soft-deleted observations**:

```python
# CRUD layer pattern (ingestor/crud.py)
async def get_observations(db: AsyncSession, limit: int = 100) -> list[Observation]:
    """Fetch active (non-deleted) observations."""
    result = await db.execute(
        select(Observation)
        .where(Observation.deleted_at == None)  # Soft-delete filter
        .limit(limit)
    )
    return result.scalars().all()

async def get_all_observations_including_deleted(db: AsyncSession) -> list[Observation]:
    """Fetch all observations, including soft-deleted (admin only)."""
    result = await db.execute(select(Record))
    return result.scalars().all()
```

### Database View for Active Observations

For convenience, create a view that filters automatically:

```sql
CREATE VIEW v_active_observations AS
SELECT * FROM observations
WHERE deleted_at IS NULL;

CREATE VIEW v_active_processed_events AS
SELECT * FROM processed_events
WHERE deleted_at IS NULL;
```

---

## Implementation Checklist

- [ ] **Archive tables created** (✓ in migration `a8f3c2e9d1b4`)
  - `observations_archive` with monthly range partitioning
  - Partial indexes on timestamp for efficient range queries

- [ ] **Migration scripts created**
  - `ingestor/jobs/archive_observations.py` (Tier 1 → 2)
  - `ingestor/jobs/export_cold_storage.py` (Tier 2 → 3)
  - `ingestor/jobs/cleanup_soft_deleted.py` (grace period cleanup)

- [ ] **Scheduler integration**
  - APScheduler or internal job runner with cron-like syntax
  - Health checks / alerting on job failures

- [ ] **Query filters updated**
  - All CRUD functions exclude `deleted_at IS NOT NULL` by default
  - Admin endpoints have "include_deleted" flag

- [ ] **Monitoring & alerting**
  - Track archival job durations and success rates
  - Alert if cold storage export fails

- [ ] **Documentation & runbooks**
  - Operator guide for manual recovery
  - Compliance audit procedures

---

## Data Retention Summary

| Tier | Storage | Duration | SLA | Cost |
|------|---------|----------|-----|------|
| **Hot** | `observations` table | 0–30 days | P99 <500ms | $$$$ (compute/memory) |
| **Warm** | `observations_archive` partitions | 30–90 days | P99 <10s | $$ (compute/storage) |
| **Cold** | S3/GCS with expiration | 90+ years | N/A | $ (storage only) |

---

## Compliance & Audit

### Audit Trail Requirements

- All records (including deleted) must be queryable for 90 days minimum
- Deleted records must retain `deleted_at` timestamp for compliance
- Archive exports must be immutable (no updates after export)
- Access logs required for any query accessing data >30 days old

### GDPR / Data Subject Rights

- **Right to Erasure**: Supported via soft-delete → grace period → hard delete
- **Right to Data Portability**: Export via cold storage jobs
- **Data Retention**: Automatic cleanup after 90-day grace period respects GDPR minimization principle

---

## Future Enhancements

1. **Automated cold storage tiering**: Integrate with cloud storage lifecycle policies
2. **Data compression**: Use columnar format (Parquet) for archive exports
3. **Encryption at rest**: Enable for archived records in S3/GCS
4. **Query federation**: Query cold storage directly via Presto/Trino without loading into DB
5. **Incremental exports**: Export only new/modified records (avoid full scans)
