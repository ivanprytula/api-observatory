"""libs.platform — shared infrastructure utilities.

Intended contents (migrate from ingestor/core/ in Phase 3):
- logging    : structured JSON logging setup (python-json-logger)
- tracing    : OpenTelemetry span helpers
- retry      : async retry with exponential backoff
- circuit_breaker : async circuit-breaker pattern
- scheduler  : APScheduler lifecycle wrapper
- sentry     : Sentry SDK init helper

Design constraints:
- Zero service-domain knowledge (no Record, no pipeline-specific types)
- No imports from libs.contracts or any service
- All public symbols re-exported here for a stable import surface:
    from libs.platform import retry, circuit_breaker
"""
