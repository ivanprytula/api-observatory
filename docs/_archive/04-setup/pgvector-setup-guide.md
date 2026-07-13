# PostgreSQL + pgvector Setup Guide

Track: B — Engineering Execution


## Overview

This project uses PostgreSQL 17 with the pgvector extension for Phase 5 (vector similarity + Qdrant comparison).

**pgvector** is automatically installed in the Docker PostgreSQL image. No manual installation is required for new developers.

---

## Quick Start (0 to Deploy)

### Prerequisites

- Docker + Docker Compose
- Python 3.14+ (for local development)
- `uv` package manager (installed via `pip install uv`)

### Step 1: Start PostgreSQL with pgvector

```bash
# Start the database service (builds custom image with pgvector pre-installed)
docker compose up -d db

# Verify database is healthy
docker compose exec db pg_isready -U postgres
```

The custom PostgreSQL image is built from `infra/database/Dockerfile` and automatically:

- Installs pgvector extension (v0.7.4)
- Runs initialization scripts from `infra/database/init.sql` (creates vector extension on startup)

### Step 2: Apply Alembic Migrations

```bash
# Install dependencies
uv sync

# Run migrations (creates tables, materialized views, partitions)
uv run alembic upgrade head
```

Migrations automatically create the pgvector extension if not already present (`CREATE EXTENSION IF NOT EXISTS vector`).

---

## Architecture: pgvector Setup

### 1. Custom PostgreSQL Image

**File**: `infra/database/Dockerfile`

See `infra/database/Dockerfile` for the pgvector build.

**Why**: Pre-compiling pgvector in the Docker image avoids runtime installation overhead and compilation errors.

### 2. Initialization Script

**File**: `infra/database/init.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

**Why**: PostgreSQL runs all SQL files in `/docker-entrypoint-initdb.d/` on first container start. This ensures extensions are created before Alembic migrations run.

### 3. Docker Compose Configuration

**File**: `docker-compose.yml`

```yaml
db:
  build:
    context: ./infra/database
    dockerfile: Dockerfile
  volumes:
    - ./infra/database/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
```

**Why**:

- `build:` uses custom image with pgvector pre-compiled
- Mounting init.sql ensures extensions exist on container startup

### 4. Alembic Migration

**File**: `alembic/versions/20260421_000001_phase5_advanced_sql_cqrs.py`

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Create materialized views, partitioned tables, etc.
```

**Why**: `IF NOT EXISTS` makes migration idempotent (safe to run multiple times).

---

## Troubleshooting

### Issue: `FeatureNotSupported: extension "vector" is not available`

**Cause**: Running migrations against standard postgres:17 image (without pgvector).

**Solution**: Rebuild the database service with custom image:

```bash
# Rebuild the database service (see infra/database/Dockerfile)
docker compose down db
docker compose up -d db --build
```

### Issue: Extension already exists after migration

**Cause**: init.sql runs during container startup, then Alembic migration also creates extension.

**Resolution**: Not an issue! Both use `CREATE EXTENSION IF NOT EXISTS`, which is safe for idempotent operations.

---

## Performance & Optimization

### pgvector Version

- **Current**: v0.7.4 (stable, released 2024-Q1)
- **Update**: Edit `infra/database/Dockerfile` line `git clone --branch v0.7.4 ...`

### Vector Similarity Indexes

For production queries on large embedding tables, create HNSW or IVFFlat indexes:

```sql
-- HNSW index (better for similarity search)
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);

-- IVFFlat index (faster but less accurate)
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

See [pgvector docs](https://github.com/pgvector/pgvector#indexes) for details.

---

## Phase 5 Features Using pgvector

### 1. Vector Embeddings Storage

Store embeddings for documents/records:

```python
class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    embedding: Mapped[Vector] = mapped_column(Vector(1536))  # OpenAI Ada
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
```

### 2. Vector Similarity Search

Query for similar embeddings:

```python
async def find_similar_documents(db: AsyncSession, query_embedding: list[float], limit: int = 5):
    result = await db.execute(
        text("""
        SELECT document_id, 1 - (embedding <=> :embedding) AS similarity
        FROM document_embeddings
        ORDER BY embedding <=> :embedding
        LIMIT :limit
        """),
        {"embedding": query_embedding, "limit": limit}
    )
    return result.fetchall()
```

### 3. Comparison with Qdrant

- **pgvector**: Embedded in PostgreSQL, simple setup, good for small-to-medium scale
- **Qdrant**: Dedicated vector DB, better for high-scale, specialized vector operations

Phase 5 implements both to demonstrate trade-offs (see ADR 002: qdrant-vs-pgvector.md).

---

## References

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [pgvector Documentation](https://github.com/pgvector/pgvector#usage)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)
- [Alembic Migration Guide](https://alembic.sqlalchemy.org/)
