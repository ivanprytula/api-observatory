# Backup and Restore

Step-by-step guide for local and S3-backed backup and restore operations.

---

## Prerequisites

- Docker Compose stack running (`just up` at minimum)
- For S3 operations: `aws` CLI installed and `AWS_ENDPOINT_URL` set for Floci or real AWS credentials for production

---

## Local backup

```bash
# Writes to ./backups/postgres/ and ./backups/mongodb/
just backup
# or directly:
bash infra/scripts/backup.sh
```

Files created:

```text
backups/
  postgres/pg_data_pipeline_<YYYYMMDD_HHMMSS>.sql.gz
  mongodb/mongo_data_zoo_<YYYYMMDD_HHMMSS>.archive.gz
```

Backups older than `BACKUP_RETENTION_DAYS` (default: 7) are automatically deleted.

---

## S3 backup (Floci / AWS)

```bash
# Upload only (no local copy kept)
BACKUP_STORAGE=s3 \
  BACKUP_S3_BUCKET=data-pipeline-backups \
  AWS_ENDPOINT_URL=http://127.0.0.1:4566 \
  bash infra/scripts/backup.sh

# Both local and S3
just backup-both
```

Verify upload:

```bash
aws --endpoint-url http://127.0.0.1:4566 s3 ls s3://data-pipeline-backups/backups/postgres/
```

---

## Local restore

### PostgreSQL

```bash
# Interactive (lists available backups, prompts for file)
bash infra/scripts/restore.sh postgres

# Non-interactive
bash infra/scripts/restore.sh postgres backups/postgres/pg_data_pipeline_<timestamp>.sql.gz
```

### MongoDB

```bash
bash infra/scripts/restore.sh mongodb backups/mongodb/mongo_data_zoo_<timestamp>.archive.gz
```

---

## S3 restore

```bash
# PostgreSQL from S3
just restore-s3-postgres s3://data-pipeline-backups/backups/postgres/pg_data_pipeline_<timestamp>.sql.gz

# MongoDB from S3
just restore-s3-mongodb s3://data-pipeline-backups/backups/mongodb/mongo_data_zoo_<timestamp>.archive.gz

# Or directly with Floci endpoint
AWS_ENDPOINT_URL=http://127.0.0.1:4566 \
  bash infra/scripts/restore.sh postgres --from-s3 s3://data-pipeline-backups/backups/postgres/pg_data_pipeline_20260101_120000.sql.gz
```

The script downloads to `/tmp`, restores, then deletes the temp file.

---

## Verify restore

```bash
# Count observations after restore
docker compose exec db psql -U postgres -d data_pipeline \
  -c "SELECT COUNT(*) FROM observations;"

# Run migrations to confirm schema is current
just migrate
```

---

## Automation (cron example)

```cron
# Daily at 02:00 — backup to both local and S3
0 2 * * * cd /path/to/project && BACKUP_STORAGE=both BACKUP_S3_BUCKET=data-pipeline-backups bash infra/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## Environment variables reference

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `BACKUP_STORAGE` | `local` | `local`, `s3`, or `both` |
| `BACKUP_S3_BUCKET` | *(required for S3)* | S3 bucket name |
| `BACKUP_S3_PREFIX` | `backups/` | Key prefix within the bucket |
| `AWS_ENDPOINT_URL` | *(empty = real AWS)* | Override for Floci: `http://127.0.0.1:4566` |
| `BACKUP_RETENTION_DAYS` | `7` | Days to keep local backup files |
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_DB` | `data_pipeline` | Database name |
