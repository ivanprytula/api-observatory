# Phase 4 — AI + Vector Database (Embeddings)

**Duration**: 2 weeks
**Goal**: Generate embeddings from scraped data, store in Qdrant, implement semantic search
**Success Metric**: <200ms latency for search, 95%+ relevance (NDCG@5), 10K+ vectors indexed

---

## Core Learning Objective

Understand vector databases, embedding models, similarity search, and LRU caching for ML inference costs.

---

## Interview Questions

### Core Q: "Design Semantic Search Over 1M Documents"

**Expected Answer:**

- Embedding model: OpenAI API (reliable, good quality) or local (Sentence-Transformers, free but CPU-heavy)
- Batch generation: Embed 1K documents at once (cheaper than 1-at-a-time with OpenAI)
- Vector DB: Qdrant (self-hosted, simple REST API) or pgvector (PostgreSQL extension, coupled to DB)
- Indexing: HNSW (Hierarchical Navigable Small World) for fast approximate nearest neighbor search
- Caching: LRU cache on embedding API calls (same text → same embedding, no recompute)
- Query: User query → embed → search Qdrant → return top-K similar documents

**Talking Points:**

- Embedding dimensionality: OpenAI text-embedding-3-small = 1536 dims. Trade-off: more dims = better quality, larger indices.
- Vector DB vs RDBMS: Vector DBs optimize for high-dimensional similarity. Postgres pgvector works but slower at 100K+ vectors.
- Semantic vs keyword search: Semantics finds related meaning (dog + puppy), keywords miss relations. Hybrid (keyword + semantic) often best.

---

### Follow-Up: "Embedding API Costs High. Optimize Without Quality Loss?"

**Expected Answer:**

- LRU cache: Same text always → same embedding. Cache hit saves $0.02 per 1K tokens. Hit ratio 60%+ → savings obvious.
- Batch requests: OpenAI charges per request (not per token), so batch 100 texts in one request (cheaper per text).
- Dimensionality: Use text-embedding-3-small (cheaper, 1536 dims) vs large (more expensive, 3072 dims). Benchmark: small often sufficient.
- Re-embed strategy: Don't re-embed unchanged documents. Only new documents.
- Local model: For cost-sensitive: Sentence-Transformers all-MiniLM-L6-v2 (free, 384 dims, CPU inference, slower).

**Talking Points:**

- Cost budgets: $0.02/1K tokens (OpenAI small). At 10K new docs/month × 500 tokens/doc = $100/month. LRU cache can cut in half.
- Batch efficiency: 1 API call (100 texts) = 1 request charge. Sequential (100 calls) = 100 charges. Use batching via `asyncio.gather()`.

---

### Follow-Up: "Search Returns Irrelevant Results. Debug?"

**Expected Answer:**

- Check embedding quality: Re-embed query + sample documents, compute cosine similarity manually (should be >0.8 for relevant).
- Check Qdrant index: Verify documents indexed (`GET /collections/{name}` → check record count). If 0, data didn't insert.
- Check query preprocessing: Lowercase, remove punctuation? Inconsistent preprocessing = lower scores.
- Threshold tuning: Lower score threshold (default 0.7 → try 0.5) to get more results (recall vs precision trade-off).
- Embedding model quality: Small vs large? Test on sample queries, measure NDCG@5 (normalized discounted cumulative gain).

**Talking Points:**

- Relevant pairs for validation: Create ground-truth (10 queries, hand-label top 10 docs), measure NDCG to detect model degradation.
- Fine-tuning embeddings: For domain-specific (medical records, legal docs), fine-tune Sentence-Transformers on your data for 2–5% improvement.

---

## Real life production example — Production-Ready

### Architecture

```text
Phase 2 scraper outputs: [{ price: 100, description: "...", source: "..." }]
  ↓
Phase 4 embedding pipeline:
  ├─► Batch: Group documents into 100-doc chunks
  ├─► LRU cache check: If text seen before, reuse embedding
  ├─► Call OpenAI API: /v1/embeddings (batch 100 docs)
  ├─► Store in Qdrant: POST /collections/scrapes/points
  └─► Index HNSW: auto-created by Qdrant
  ↓
Query endpoint: POST /api/v1/search
  ├─► User query: "cheap laptop under $500"
  ├─► Embed query (cached)
  ├─► Qdrant search: top 10 similar
  ├─► Return docs + score
```

### Implementation Checklist

- [ ] **app/embeddings/embedder.py** — LRU cache + OpenAI API

  ```python
  from functools import lru_cache
  import openai

  EMBEDDING_MODEL = "text-embedding-3-small"
  EMBEDDING_DIM = 1536

  @lru_cache(maxsize=10000)
  def embed_text(text: str) -> list[float]:
      """Cache embeddings by text content."""
      response = openai.Embedding.create(
          input=text,
          model=EMBEDDING_MODEL,
      )
      return response['data'][0]['embedding']

  async def embed_batch(texts: list[str]) -> list[list[float]]:
      """Batch embed (cheaper per text)."""
      response = await openai.AsyncOpenAI().embeddings.create(
          input=texts,
          model=EMBEDDING_MODEL,
      )
      return [e['embedding'] for e in response['data']]
  ```

- [ ] **app/qdrant_client.py** — Qdrant integration

  ```python
  from qdrant_client.async_client import AsyncQdrantClient
  from qdrant_client.models import PointStruct, VectorParams, Distance

  class QdrantService:
      def __init__(self, url: str = "http://qdrant:6333"):
          self.client = AsyncQdrantClient(url=url)
          self.collection_name = "scraped_data"

      async def create_collection(self):
          """Create collection with HNSW indexing."""
          await self.client.recreate_collection(
              collection_name=self.collection_name,
              vectors_config=VectorParams(
                  size=EMBEDDING_DIM,
                  distance=Distance.COSINE,  # Cosine similarity
              ),
          )

      async def upsert_documents(self, documents: list[dict]):
          """Batch insert or update documents with embeddings."""
          points = []
          for i, doc in enumerate(documents):
              embedding = await embed_text(doc['description'])
              points.append(
                  PointStruct(
                      id=i,
                      vector=embedding,
                      payload={
                          'source': doc['source'],
                          'price': doc['price'],
                          'description': doc['description'],
                      },
                  )
              )

          await self.client.upsert(
              collection_name=self.collection_name,
              points=points,
          )

      async def search(self, query: str, limit: int = 10) -> list[dict]:
          """Search by query text."""
          query_embedding = await embed_text(query)
          results = await self.client.search(
              collection_name=self.collection_name,
              query_vector=query_embedding,
              limit=limit,
              score_threshold=0.7,
          )
          return [
              {
                  'score': r.score,
                  **r.payload,
              }
              for r in results
          ]
  ```

- [ ] **app/routers/search.py** — Search endpoint

  ```python
  from fastapi import APIRouter
  from app.schemas import SearchRequest, SearchResponse

  router = APIRouter()
  qdrant = QdrantService()

  @router.post("/api/v1/search")
  async def search(req: SearchRequest) -> list[SearchResponse]:
      """Semantic search over scraped data."""
      results = await qdrant.search(req.query, limit=10)
      return [SearchResponse(**r) for r in results]
  ```

- [ ] **Pydantic schemas**

  ```python
  from pydantic import BaseModel

  class SearchRequest(BaseModel):
      query: str
      limit: int = 10

  class SearchResponse(BaseModel):
      score: float
      source: str
      price: float
      description: str
  ```

- [ ] **docker-compose.yml** addition

  ```yaml
  services:
    qdrant:
      image: qdrant/qdrant:latest
      ports: ["6333:6333"]
      volumes:
        - qdrant_data:/qdrant/storage

  volumes:
    qdrant_data:
  ```

- [ ] **Environment variables**

  ```bash
  OPENAI_API_KEY=sk_...  # Set in .env or GitHub Secrets
  QDRANT_URL=http://qdrant:6333
  ```

- [ ] **Monitoring**

  ```python
  from prometheus_client import Histogram, Counter

  embedding_latency = Histogram('embedding_latency_seconds', 'Embedding generation time')
  embedding_cache_hits = Counter('embedding_cache_hits_total', 'LRU cache hits')
  search_latency = Histogram('search_latency_seconds', 'Search query time')
  search_results_count = Histogram('search_results_count', 'Results returned')
  ```

---

## Weekly Checklist

### Week 1: Embeddings + LRU Cache

- [ ] OpenAI API integration (requires key)
- [ ] LRU cache for embeddings (maxsize=10k)
- [ ] Batch embedding function (100 texts at once)
- [ ] Unit tests: mock OpenAI, test cache hit rate
- [ ] Cost calculation: measure API calls, estimate monthly cost
- [ ] Interview Q: "Design semantic search for 1M docs?" → Answer drafted
- [ ] Commits: 6–8 (openai client, caching, batch logic, tests)

### Week 2: Qdrant + Search

- [ ] Qdrant collection creation with HNSW (cosine distance)
- [ ] Upsert documents with embeddings
- [ ] Search endpoint (POST /api/v1/search)
- [ ] Relevance testing: 10 queries, hand-label results, compute NDCG@5
- [ ] E2E: Phase 2 scraper → Phase 4 embedding → search works
- [ ] Performance: <200ms latency on search (measure p99)
- [ ] Interview Q: "Embedding costs high. Optimize?" → Full answer
- [ ] Commits: 5–7 (qdrant setup, search endpoint, relevance testing)
- [ ] Portfolio item + LinkedIn post

---

## Success Metrics

| Metric               | Target   | How to Measure                                                   |
| -------------------- | -------- | ---------------------------------------------------------------- |
| Vectors indexed      | 10K+     | Qdrant `/collections/{name}` → points_count                      |
| Search latency (p99) | <200ms   | Prometheus histogram `search_latency_seconds` p99                |
| Embedding cache hit  | 60%+     | Counter `embedding_cache_hits / total_requests`                  |
| NDCG@5               | 0.80+    | Hand-label 10 queries, compute score (higher = better relevance) |
| Relevance F1         | 0.85+    | Precision × Recall at threshold 0.7                              |
| API cost             | <$100/mo | (new docs/month × avg tokens) × $0.02/1K tokens                  |
| Commit count         | 11–15    | 1 per feature                                                    |

---

## Gotchas + Fixes

### Gotcha 1: "Qdrant Search Returns No Results"

**Symptom**: Query returns empty list despite 1K+ vectors indexed.
**Cause**: Score threshold too high (default 0.7) or embedding model differs (embedding space mismatch).
**Fix**: Lower threshold to 0.5, verify same model for query and documents, check Qdrant logs.

### Gotcha 2: "Embedding Cache Slows Down on Memory"

**Symptom**: After 1M+ cache entries, LRU cache lookup slow.
**Cause**: Python dict lookup not instant on massive sizes (still O(1) but with overhead).
**Fix**: Consider Redis for distributed caching or reduce maxsize. Or use both: local 1K hot, Redis 100K warm.

### Gotcha 3: "OpenAI API Quota Exceeded"

**Symptom**: Requests rate-limited (429), pipeline stalls.
**Cause**: OpenAI account has usage limit (e.g., $10/month free tier).
**Fix**: Upgrade to paid account, set usage limits in OpenAI dashboard. Or batch off-peak hours.

### Gotcha 4: "Results Drift (Different Each Query)"

**Symptom**: Same query returns different top-5 each time (non-deterministic).
**Cause**: Qdrant HNSW search is approximate (not exact), uses randomness in indexing.
**Fix**: Acceptable (HNSW trades exactness for speed). If determinism required, disable HNSW (exact search, slower).

---

## Cleanup (End of Phase 4)

```bash
# Clear embedding cache (if too large)
python -c "from app.embeddings import embed_text; embed_text.cache_clear()"

# Qdrant collection stats
curl http://qdrant:6333/collections/scraped_data
```

---

## Metrics to Monitor Ongoing

- `embedding_latency_seconds`: Alert if p99 > 500ms (indicates API slowness)
- `embedding_cache_hits_total`: Should be 50%+ (if <30%, cache underutilized)
- `search_latency_seconds` p99: Alert if > 500ms
- OpenAI API spend: Track monthly (set alerts in OpenAI dashboard)

---

## Next Phase

**Phase 5: Testing & Observability**
Comprehensive pytest fixtures for Qdrant mocking, chaos testing (Qdrant down, API timeout), load testing with k6. Add tracing (OpenTelemetry) and structured logging.

**Reference**: Phase 4 relevance stable (NDCG > 0.80) = ready for Phase 5.
