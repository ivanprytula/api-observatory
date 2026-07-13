# MVP and MVP+ Usage

This project has two operating modes while the platform is being stabilized.

## MVP Mode

Use this mode during active feature stabilization. It favors speed and predictable local feedback.

### Runtime profile

- Start the local stack with Docker Compose.
- Keep schema setup simple with startup bootstrap behavior.
- Focus on source-registry, probe loop, scorecards, and drift slices.

### Test gate

```bash
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest services/ingestor/tests/integration/test_source_registry_api.py -q
```

## MVP+ Mode

Use this mode after MVP is shipped and release hardening begins.

### Runtime profile

- Keep the same app surface and services.
- Enable migration-first schema workflow.
- Require stronger release validation and operational checks.

### Test gate

```bash
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```

## When to switch

Switch from MVP to MVP+ when all are true:

1. Core vertical slices are stable under daily development.
2. API behavior is locked for release candidates.
3. You are ready to enforce migration-first database changes.
