# Backup and Restore

Step-by-step guide for local and cloud-backed backup and restore operations.

---

## Prerequisites

- Docker Compose stack running (`just up` at minimum)
- For cloud storage operations: `az` CLI installed, or `AZURE_STORAGE_CONNECTION_STRING` set for floci-az emulator

---

## Local backup

```bash
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

## Blob Storage backup (floci-az / Azure)

```bash
# Upload only (no local copy kept)
BACKUP_STORAGE=blob \
  AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:4577/devstoreaccount1" \
  bash infra/scripts/backup.sh

# Both local and Blob Storage
BACKUP_STORAGE=both bash infra/scripts/backup.sh
```

Verify upload:

```bash
az storage blob list \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
  --container-name backups \
  --output table
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

## Blob Storage restore

```bash
# PostgreSQL from Blob Storage
bash infra/scripts/restore.sh postgres --from-blob postgres/pg_data_pipeline_<timestamp>.sql.gz

# MongoDB from Blob Storage
bash infra/scripts/restore.sh mongodb --from-blob mongodb/mongo_data_zoo_<timestamp>.archive.gz
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
# Daily at 02:00 — backup to both local and Blob Storage
0 2 * * * cd /path/to/project && BACKUP_STORAGE=both bash infra/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## Environment variables reference

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `BACKUP_STORAGE` | `local` | `local`, `blob`, or `both` |
| `BACKUP_BLOB_CONTAINER` | `backups` | Blob container name |
| `BACKUP_BLOB_PREFIX` | *(empty)* | Blob name prefix within the container |
| `AZURE_STORAGE_CONNECTION_STRING` | *(required for blob)* | Connection string (emulator or real Azure) |
| `BACKUP_RETENTION_DAYS` | `7` | Days to keep local backup files |
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_DB` | `data_pipeline` | Database name |
