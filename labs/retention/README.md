# Observation Retention Lab

Learning artifact: bounded observation lifecycle (archive old rows to a warm tier, then delete from the hot table).

This code was extracted from the production ingestor (`services/ingestor/jobs/retention.py`) as part of the ACROSS ORM/API alignment. It remains runnable as a standalone lab for experimentation with retention policies.

## Run

```bash
# Dry run — report the next eligible batch without changing data
uv run python labs/retention/run.py --dry-run

# Apply — archive one batch (requires RETENTION_ENABLED=true)
uv run python labs/retention/run.py --apply
```

## Test

```bash
# Unit tests (require a database fixture)
uv run pytest labs/retention/test_retention.py -v

# Integration tests (require PostgreSQL)
uv run pytest labs/retention/test_integration.py -v
```

## What it demonstrates

- Bounded batch processing with a configurable cutoff and batch size
- Distributed lock to prevent concurrent retention runs
- Verify-before-delete: archive rows, verify they exist in the archive, then delete from the hot table
- Idempotency: re-running finds no already-archived hot rows
- Dry-run mode for safe inspection before destructive apply
