# Pillar 6: AI / LLM Integration

Track: E — Archive and Historical Snapshots

**Tier**: Middle (🟡 partial) → Senior (🟡 LangGraph shipped)
**Project**: The 2025-2030 multiplier
**Implementation**: `services/ingestor/agent/`, `services/ingestor/api/routes/agent.py`

---

## What Is Implemented

| Component                                | File                                  | Status  |
| ---------------------------------------- | ------------------------------------- | ------- |
| LangGraph `StateGraph` — 5 nodes         | `services/ingestor/agent/graph.py`    | ✅ Done |
| Async node implementations               | `services/ingestor/agent/nodes.py`    | ✅ Done |
| `AgentState` TypedDict                   | `services/ingestor/agent/state.py`    | ✅ Done |
| 4 FastAPI agent endpoints                | `services/ingestor/api/routes/agent.py`  | ✅ Done |
| RAG via pgvector (fetch_context node)    | `services/ingestor/vector_search.py`  | ✅ Done |
| OpenAI structured output (classify node) | `services/ingestor/agent/nodes.py`    | ✅ Done |
| Cache HITL checkpointing                 | `compile_with_checkpointer()` factory | ✅ Done |

**Remaining Senior gaps**: RAGAS evaluation pipeline, MCP server, fine-tuning vs RAG analysis.

---

## Middle Tier (🟡)

### OpenAI SDK — Current Async Patterns

The `openai` package v1.0+ replaced the old module-level `openai.ChatCompletion.acreate`
with an instantiated `AsyncOpenAI` client.

**Standard chat completion**:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

async def classify_observation(observation_data: dict) -> str:
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data classifier. Return only the category."},
            {"role": "user", "content": f"Classify this: {observation_data}"},
        ],
        temperature=0,
    )
    return response.choices[0].message.content
```

**Structured output with `parse()`** (enforces Pydantic schema — no JSON-mode hacks):

```python
from openai import AsyncOpenAI
from pydantic import BaseModel

client = AsyncOpenAI()


class ObservationClassification(BaseModel):
    category: str
    confidence: float
    priority: int
    explanation: str


async def classify_structured(observation_data: dict) -> ObservationClassification:
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Classify the observation. Return valid JSON."},
            {"role": "user", "content": str(observation_data)},
        ],
        response_format=ObservationClassification,
    )
    return response.choices[0].message.parsed
```

`client.beta.chat.completions.parse()` validates the response against the Pydantic
model client-side — no manual `model_validate_json()` required.

**Why not `response_format={"type": "json_schema", ...}`?** That older pattern requires
manual parsing and doesn't enforce the schema client-side. Use `.parse()` instead.

**Error handling with tenacity** (as used in `classify_node`):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def classify_with_retry(observation: dict) -> ObservationClassification:
    response = await client.beta.chat.completions.parse(...)
    return response.choices[0].message.parsed
```

Tenacity retries on transient `RateLimitError` / `APIConnectionError` with exponential
backoff — no manual `try/except asyncio.sleep` loops.

---

### RAG Pipeline

**Components**:

1. **Embeddings** — convert text → vector via `text-embedding-3-small`
2. **Vector store** — `pgvector` extension on the existing PostgreSQL instance
3. **Retrieval** — cosine-distance nearest-neighbour search (`<=>` operator)
4. **Generation** — feed retrieved context into OpenAI chat completion

**Actual implementation** in `services/ingestor/vector_search.py`:

```python
from openai import AsyncOpenAI
from sqlalchemy import text

client = AsyncOpenAI()


async def embed_text(text_input: str) -> list[float]:
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text_input,
    )
    return response.data[0].embedding


async def search_record_documents(query: str, top_k: int = 3) -> list[str]:
    """Find top-k most similar stored documents (cosine distance via pgvector)."""
    embedding = await embed_text(query)
    stmt = text(
        "SELECT content FROM scraped_documents "
        "ORDER BY embedding <=> :embedding "
        "LIMIT :top_k"
    )
    # ... execute against async session, return list of content strings
```

The `fetch_context_node` in the LangGraph agent calls `search_record_documents(query, top_k=3)`
and injects the result as `rag_context` into `AgentState` — making it available to the
`classify_node` prompt.

---

### GenAI Tool Proficiency

**GitHub Copilot**: Use for code generation, test scaffolding
**Claude**: Architecture review, complex refactoring
**Cursor / Windsurf**: Multi-file editing across codebase

---

## Senior Tier (🟡 — LangGraph agent shipped)

### LangGraph StateGraph — Implemented Architecture

Location: `services/ingestor/agent/`

#### Agent State

```python
# services/ingestor/agent/state.py
from typing import TypedDict
from services.ingestor.api_schemas.records import RecordClassification


class AgentState(TypedDict):
    record_id: int
    record: dict              # source, raw_data, tags, timestamp
    rag_context: str          # retrieved from pgvector (fetch_context_node)
    classification: RecordClassification | None   # set by classify_node
    analysis_depth: str       # "standard" | "deep"
    result: str               # final formatted output
    error: str | None
```

#### Graph Structure

```text
START
  │
  ▼
fetch_context ──► classify ──► _should_deep_analyze?
                                        │
                    ┌───────────────────┤
                    │                   │
                    ▼ (standard)        ▼ (priority≥4 OR category=="unknown")
               format_result       deep_analyze
                    │                   │
                    └─────────┬─────────┘
                              ▼
                           publish
                              │
                              ▼
                             END
```

#### Conditional Edge

```python
def _should_deep_analyze(state: AgentState) -> str:
    c = state.get("classification")
    if c and (c.priority >= 4 or c.category == "unknown"):
        return "deep_analyze"
    return "format_result"
```

#### Lazy Compilation Pattern

```python
# services/ingestor/agent/graph.py

# Module-level agents: no checkpointer (safe to import in tests — no Cache needed)
record_enrichment_agent = _graph.compile()
record_enrichment_agent_hitl = _graph.compile(interrupt_before=["publish"])


def compile_with_checkpointer() -> tuple:
    """Production factory: creates Cache-persisted agents on demand."""
    from langgraph.checkpoint.cache.aio import AsyncCacheSaver  # v0.4.1 nested namespace
    saver = AsyncCacheSaver(settings.cache_url)
    return (
        _graph.compile(checkpointer=saver),
        _graph.compile(checkpointer=saver, interrupt_before=["publish"]),
    )
```

**Why lazy compilation?** Module-level agents don't hold Cache connections. Tests can
`import` the module without a running Cache. Production callers use `compile_with_checkpointer()`
to get a Cache-backed agent with persistent thread state.

#### classify_node — Structured Output + Tenacity Retry

```python
# services/ingestor/agent/nodes.py
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

client = AsyncOpenAI()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def classify_node(state: AgentState) -> AgentState:
    prompt = (
        f"Record: {state['record']}\n"
        f"Context: {state['rag_context']}\n"
        "Classify this record."
    )
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a data classifier."},
            {"role": "user", "content": prompt},
        ],
        response_format=RecordClassification,
    )
    state["classification"] = response.choices[0].message.parsed
    return state
```

---

### HITL Pattern (Human-in-the-Loop)

```python
# Compile with interrupt_before=["publish"] — pauses before publish node
agent_hitl = _graph.compile(interrupt_before=["publish"])

# Start run — returns with hitl_paused=True
state = await agent_hitl.ainvoke(initial_state, config={"configurable": {"thread_id": run_id}})

# Human reviews classification ...

# Resume: approve → publish continues; reject → publish skipped
await agent_hitl.ainvoke(None, config={"configurable": {"thread_id": run_id}})
```

The `thread_id` is the key to Cache checkpointer state — all mid-graph state is persisted
across the pause/resume boundary.

---

### FastAPI Agent Endpoints

Location: `services/ingestor/api/routes/agent.py`

| Method | Path                         | Description                                     |
| ------ | ---------------------------- | ----------------------------------------------- |
| `POST` | `/enrich/{record_id}`        | Full run (no pause); returns `AgentRunResponse` |
| `POST` | `/enrich/{record_id}/review` | Run with HITL pause before publish              |
| `POST` | `/enrich/{record_id}/resume` | Resume paused run (`approve: bool`)             |
| `POST` | `/enrich/{record_id}/stream` | `StreamingResponse` — yields events as SSE      |

---

### AsyncCacheSaver — Import Path Note

`langgraph-checkpoint-cache` v0.4.1 uses a *nested namespace*:

```python
# ✅ Correct (v0.4.1+)
from langgraph.checkpoint.cache.aio import AsyncCacheSaver

# ❌ Wrong (older path — no longer exists)
from langgraph.checkpoint.cache import AsyncCacheSaver
```

---

## Remaining Senior Gaps (🔴)

### RAGAS Evaluation Pipeline

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_recall

results = evaluate(
    dataset=test_dataset,   # questions + ground truth + retrieved context
    metrics=[faithfulness, answer_relevancy, context_recall],
)
# faithfulness: was answer factually supported by retrieved context?
# answer_relevancy: did answer address the question?
# context_recall: was relevant ground-truth info present in retrieved context?
```

Plan: wire RAGAS against the `fetch_context` + `classify` pipeline using a golden
dataset of 20–30 records with known correct classifications.

### MCP Server

Expose the agent endpoints to Claude Desktop via MCP:

```python
# services/mcp_server/server.py
from mcp.server import Server

server = Server("data-pipeline-server")

@server.call_tool()
async def enrich_record(record_id: int) -> str:
    """Run LangGraph enrichment agent on a record."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"http://127.0.0.1:8000/enrich/{record_id}")
    return resp.text
```

---

---

## You Should Be Able To

✅ Call OpenAI API with `AsyncOpenAI` client (v1.0+ pattern)
✅ Use `client.beta.chat.completions.parse()` for structured output with Pydantic
✅ Build RAG pipeline: embed → store in pgvector → retrieve → augment prompt
✅ Build stateful agent with LangGraph `StateGraph` + conditional edges
✅ Implement HITL interrupt/resume pattern via `interrupt_before`
✅ Use lazy compilation to keep tests Cache-free
✅ Apply tenacity retry decorator to LLM nodes
🔴 Measure RAG quality with RAGAS metrics
🔴 Build and expose an MCP server for Claude Desktop
🔴 Design fine-tuning vs RAG vs prompt engineering decision framework

---

---

## References

- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [langgraph-checkpoint-cache](https://pypi.org/project/langgraph-checkpoint-cache/)
- [pgvector](https://github.com/pgvector/pgvector)
- [Tenacity](https://tenacity.readthedocs.io/)
- [MCP Spec](https://modelcontextprotocol.io/)
- [RAGAS](https://ragas.io/)

---

## Checklist — Pillar 6: AI/LLM

### Foundation 🟢

- [ ] Call OpenAI chat completions API: system/user/assistant message roles
  - [ ] Know the difference between `temperature=0` (deterministic) and `temperature=1`
- [ ] Use `client.beta.chat.completions.parse()` for structured output
- [ ] Explain what a token is and why context window limits matter
- [ ] Know what prompt injection is and why it is a security risk

### Middle 🟡

- [x] Implement a RAG pipeline: chunk → embed → store in vector DB → retrieve → augment prompt
  - [x] `fetch_context_node` calls `search_record_documents(query, top_k=3)` via pgvector
  - [ ] Know cosine similarity measures angle between vectors (direction, not magnitude)
  - [ ] Know HNSW index vs IVF-Flat: HNSW = approximate NN, better recall; IVF = partitioning
- [x] Use `AsyncOpenAI` with `client.beta.chat.completions.parse()` (v1.0+ idiomatic)
- [ ] Choose an embedding model: `text-embedding-3-small` vs `sentence-transformers`
- [ ] Explain hallucination and three mitigation strategies

### Senior 🟡

- [x] Design a LangGraph `StateGraph` with conditional routing and HITL interrupt/resume
- [x] Implement lazy compilation pattern for test-safe module-level agents
- [x] Use `AsyncCacheSaver` for cross-request thread state persistence
- [x] Apply tenacity retry decorator to LLM nodes
- [ ] Evaluate RAG quality with RAGAS metrics: faithfulness, answer relevance, context recall
- [ ] Build an MCP server exposing the agent to Claude Desktop
- [ ] Design fine-tuning vs RAG vs prompt engineering decision tree
- [ ] Identify production LLM concerns: cost per token, rate limits, latency, content policy
- [ ] Explain MCP (Model Context Protocol): tools, resources, prompt primitives

### Pre-Interview Refresh ✏️

- [ ] What is RAG and why is it better than fine-tuning for frequently changing data?
- [ ] What is hallucination? Name three mitigation strategies
- [ ] Explain the embed-store-retrieve cycle in three sentences
- [ ] When would you choose `text-embedding-3-small` over `3-large`?
- [ ] What is the difference between `temperature=0` and `temperature=1`?
