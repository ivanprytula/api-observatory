# Code Review Checklist

Additions to the repo code-review checklist:

- **Docstrings**: New functions and methods added to `services/ingestor/` must include a Google-style docstring describing purpose, `Args`, `Returns`, and any applied design pattern (e.g., "Resilience: Circuit Breaker", "Concurrency: Lock-free queue").

Other checklist items (existing rules apply):

- Ensure parameterized DB access (no raw SQL concatenation)
- Avoid hardcoded secrets; use env vars or secret manager
- Follow import boundaries (`libs/` must not import from `services/`)
