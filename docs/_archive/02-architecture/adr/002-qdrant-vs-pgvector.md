# ADR 002: Vector Store — Qdrant vs pgvector

Track: C — Architecture and Platform Strategy

**Status**: Accepted (Qdrant primary, pgvector secondary for comparison)
**Date**: April 18, 2026
**Related ADRs**: ADR 001: Kafka vs RabbitMQ | ADR 003: HTMX vs React
**Context**: Data Zoo needs semantic search over 100K+ documents. Phase 4 introduces AI gateway; Phase 5 adds database alternatives.

---

## Decision

**Use Qdrant as the primary vector store for Phase 3–6.**
**Add pgvector extension in Phase 5 as a comparison case study.**

---

## Options Considered

### Option A: Qdrant (Dedicated Vector DB)

- **Pros:**
  - Purpose-built for vector search (optimized indexes, HNSW algorithm)
  - Standalone service (independent from PostgreSQL)
  - Fast similarity search (<100ms for 100K vectors)
  - Web UI for exploration
  - RESTful API (no SQL learning curve)
  - Scales independently of relational data
- **Cons:**
  - Additional service to manage
  - Separate backup/consistency concerns
  - Two data stores to keep in sync

### Option B: pgvector (PostgreSQL extension)

- **Pros:**
  - Single data store (vectors + relational data together)
  - Simpler backup strategy (one database)
  - ACID transactions across relational + vector data
  - SQL-based (`SELECT ... ORDER BY embedding <-> query_embedding`)
  - Lower operational complexity
- **Cons:**
  - Slower than dedicated vector DBs at scale (>100K vectors)
  - Indexes less efficient than HNSW (uses IVFFlat + HNSW in PG 15+)
  - Doesn't teach you about specialized vector indexes
  - Tightly couples blob storage with relational data

### Option C: Weaviate

- **Pros:**
  - GraphQL API (modern)
  - Hybrid search (vectors + text filters)
  - Built-in multi-tenancy
- **Cons:**
  - Higher resource footprint
  - Less battle-tested than Qdrant for single-node setups
  - GraphQL adds learning curve

---

## Rationale

Primary: Qdrant (Phase 3–6)

1. **Separation of Concerns**: Vector search is conceptually different from relational queries. Dedicated tools teach better architecture.
2. **Performance**: HNSW indexes are state-of-the-art; teaches you what production vector DBs look like (OpenSearch, Elasticsearch, Pinecone).
3. **Scalability**: Independent scaling of semantic search doesn't impact PostgreSQL performance.
4. **Learning**: You learn two distinct data models (relational + vector), a real-world skill.

Secondary: pgvector (Phase 5, comparison study)

1. **Trade-offs**: Demonstrates YAGNI — sometimes PostgreSQL is enough.
2. **Simplicity**: If you have <50K vectors, pgvector is simpler operationally.
3. **Interview Value**: "When would you use pgvector vs a dedicated vector DB?" is a great question.

---

## Consequences

### Positive

- Qdrant teaches modern vector DB architecture
- Phase 5 comparison makes trade-offs explicit
- Two approaches let you measure latency vs complexity
- Decision is justified by data, not opinion

### Negative

- More services in docker-compose.yml
- Eventual consistency between PostgreSQL and Qdrant (requires careful sync)
- Operational complexity: two databases to monitor

---

## Implementation

**Phase 3**: Deploy Qdrant

```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"  # REST API
    - "6334:6334"  # gRPC API
  environment:
    - QDRANT_STORAGE_PATH=/qdrant/storage
```

**Phase 3**: Python client

```python
from qdrant_client import AsyncQdrantClient

client = AsyncQdrantClient(url="http://qdrant:6333")
await client.upsert(
    collection_name="documents",
    points=[Point(id=1, vector=[...], payload={"source": "hn"})]
)
results = await client.search(
    collection_name="documents",
    query_vector=[...],
    limit=10
)
```

**Phase 5**: Add pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE document_embeddings (
    id SERIAL PRIMARY KEY,
    embedding vector(384),  -- all-MiniLM-L6-v2 output
    source TEXT,
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
);

SELECT source FROM document_embeddings
ORDER BY embedding <-> query_vector
LIMIT 10;
```

Then measure: Qdrant (Qdrant service) vs pgvector (PostgreSQL) at scale.

---

## Alternatives Reconsidered

**Weaviate instead of Qdrant**: Would be valid, but Qdrant is lighter-weight and faster for this use case.

**pgvector only (no Qdrant)**: Would simplify operations but miss learning about specialized vector indexes and independent scaling.

---

## Review Notes

- Phase 5 benchmark will compare query latency (Qdrant vs pgvector) on 100K vectors
- Sync strategy: Processor publishes embedding event → both services subscribe (eventual consistency)
- Fallback: If Qdrant down, analytics can degrade to pgvector search
