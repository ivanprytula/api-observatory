# ADR 012: LangGraph Incident-Triage Agent

Track: C — Architecture and Platform Strategy


## Status
Accepted. Updated 2026-07-11 (Phase 3 of `docs/.plans/ai-augmented-observatory-agent-mcp.md`)
to reflect what was actually built — original version described conditional
routing and OpenAI models that were never implemented; see "What changed"
below.

## Context
`services/ingestor/agent/` implements a LangGraph stateful agent for
incident triage: a linear five-node graph
(`classify_severity` → `retrieve_similar_incidents` → `draft_analysis` →
`human_review` → `notify`), a human-in-the-loop (HITL) pause/resume step
checkpointed to Postgres, and RAG via the Phase 2 `inference` service. Runs
are auto-triggered by critical/breaking `DriftEvent`s (Phase 1's
`_requires_incident_response` gate) — every invocation is already
"high-stakes" by construction, since low-severity drift never reaches the
agent.

## Decision
1. **Dual-Model Approach for Cost/Token Optimization**:
   - `classify_severity` uses `claude-haiku-4-5` (cheap/fast) for the LLM's
     independent severity read — a trust-calibration signal against the
     rule-based classifier, not a routing decision.
   - `draft_analysis` uses `claude-sonnet-4-5` for the actual root-cause/
     recommended-action output. Always deep, not conditional — Phase 1's
     pre-filter already means only critical/breaking incidents reach this
     node, so there's no "unknown/low-priority" case to gate on.

2. **Rate Limits & Resilience**:
   - `ChatAnthropic(..., max_retries=2)` — the Anthropic SDK's own built-in
     retry handling, not a separate `tenacity` dependency (contrary to the
     original version of this ADR).

3. **Latency Management**:
   - Two real LLM calls per run (classify + draft), plus one RAG round trip.
     Runs out-of-band (`asyncio.create_task`, fire-and-forget from
     `contract_drift.py`) — acceptable for background triage, not on any
     request's inline response path.

4. **Structured Outputs**:
   - `ChatAnthropic.with_structured_output(PydanticModel)` — see
     `services/ingestor/agent/schemas.py` (`SeverityClassification`,
     `DraftAnalysis`) — constrains output shape, same rationale as before
     (reduce hallucination surface), different mechanism (LangChain's
     structured-output wrapper instead of OpenAI's
     `beta.chat.completions.parse`).

5. **Durable HITL via LangGraph's checkpointer, not a custom mechanism**:
   - `human_review` calls `interrupt()`; `langgraph-checkpoint-postgres`
     persists graph state to the same `db` Postgres instance already in the
     stack. Resume happens via an independent
     `POST /api/v1/agent/runs/{run_id}/resume` call, potentially in a
     different process — verified live. (Considered PydanticAI+DBOS as an
     alternative; LangGraph's `interrupt()` is the more purpose-built,
     better-documented primitive for exactly this pause/resume-via-API
     pattern, and needed zero new infrastructure beyond the existing
     Postgres.)

## What changed from the original version of this ADR
- **Vendor**: OpenAI (`gpt-4o-mini`/`gpt-4o`) → Anthropic
  (`claude-haiku-4-5`/`claude-sonnet-4-5`) — the user has Anthropic
  credits, not OpenAI, at implementation time.
- **No conditional routing**: the original text described `deep_analyze_node`
  running "only for high-priority (≥ 4) or 'unknown' category records" — a
  branching graph. What's actually built is strictly linear; Phase 1's
  trigger gate already does the "is this worth the deep model" filtering
  upstream of the graph entirely.
- **No `tenacity`**: retries come from the Anthropic SDK's native
  `max_retries`, not a bolted-on retry library.

## Consequences
- The system optimizes for cost via the cheap/fast classify model, while
  `draft_analysis` — the analysis a human actually reviews — always gets the
  deeper model, since every run is already pre-filtered to high stakes.
- Latency is appropriately managed by running triage out-of-band.
- HITL pause/resume is durable across process restarts (Postgres-backed),
  not an in-memory mechanism that would lose state on a redeploy.
