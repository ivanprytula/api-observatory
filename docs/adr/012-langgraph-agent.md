# ADR 012: LangGraph Record Enrichment Agent

Track: C — Architecture and Platform Strategy


## Status
Accepted

## Context
We are implementing a LangGraph stateful agent for record enrichment with conditional routing, a human-in-the-loop (HITL) review step, and RAG capabilities. We need to handle production LLM concerns such as cost per token, rate limits, latency, and content policies.

## Decision
1. **Dual-Model Approach for Cost/Token Optimization**:
   - `classify_node` uses `gpt-4o-mini` (significantly cheaper) for routing decisions.
   - `deep_analyze_node` uses `gpt-4o` only for high-priority (≥ 4) or "unknown" category records.

2. **Rate Limits & Resilience**:
   - We will handle OpenAI TPM/RPM limits by adding retries with exponential backoff using `tenacity`.

3. **Latency Management**:
   - The RAG step adds ~100ms.
   - Classification adds ~500ms.
   - Deep analysis adds ~1-2s.
   - These latencies are acceptable for background enrichment but not for the inline request path.

4. **Content Policy & Structured Outputs**:
   - We use structured output via `response_format=RecordClassification` to constrain the output shape and reduce the hallucination surface.

5. **Model Selection Rationale**:
   - "Mini" models are well-suited for routing decisions and simpler classifications.
   - "Full" models are reserved for high-stakes, deep analysis to balance cost and quality.
   - RAG + Prompt Engineering is currently preferred over Fine-tuning, as it allows rapid iteration and context-specific enrichment without maintaining custom models.

## Consequences
- The system naturally optimizes for cost while preserving quality for complex/high-priority records.
- Latency is appropriately managed by running the enrichment out-of-band for long-running analyses.
- The use of `tenacity` provides robustness against transient OpenAI API errors.
