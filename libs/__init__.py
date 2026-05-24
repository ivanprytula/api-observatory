"""Shared libraries for the data-pipeline-async monorepo.

Two namespaces:
- libs.platform  — infrastructure cross-cuts (logging, tracing, retry, circuit-breaker)
- libs.contracts — data contracts shared across service boundaries (schemas, events, DTOs)

Rules:
- Any service may import from libs.*
- libs.* must NOT import from any service (ingestor, services/*)
- libs.platform must NOT import from libs.contracts (no domain coupling)
- libs.contracts may import from libs.platform only for logging helpers
"""
