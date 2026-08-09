# ADR 017: Versioned Accepted Contract Baselines

## Status

Accepted (2026-07-29).

## Context

Contract observations were compared only with the immediately preceding snapshot. A transiently
missing field could therefore produce a removal followed by an inverse addition when it returned.
Gradual changes could also become the new comparison point one poll at a time, even though no
operator had accepted them as known-good behavior.

The observatory needs a stable answer to "what contract do we currently trust?" without requiring
formal JSON Schema inference. Required-versus-optional inference remains a separate decision; this
record also owns observed JSON value-type and bounded array-shape normalization used by baseline
comparison.

## Decision

Maintain one active, versioned baseline for each source in `contract_baselines`:

- The first valid observation establishes version 1 with a system audit actor.
- Later observations are structurally compared with the active baseline snapshot, never merely
  with the previous poll.
- A changed structure becomes a candidate. Three consecutive observations of the same structural
  fingerprint are required before one drift event is emitted.
- Returning to the accepted structure clears an unconfirmed candidate and does not emit an inverse
  "added back" event.
- A confirmed candidate emits at most one drift event for its active baseline.
- A `writer`, `tenant_admin`, or `admin` can explicitly accept the current candidate. Acceptance
  creates the next baseline version and retains the replaced baseline as superseded history with
  actor, timestamp, and note.
- Tenant identities can inspect or accept baselines only for their active tenant. Administrators
  retain cross-tenant access.

Raw payload fingerprints remain attached to individual snapshots. Candidate confirmation uses a
separate value-independent structural fingerprint so normal value changes do not reset the count.

Observed type comparison follows these rules:

- An absent key and a present key with `null` are distinct. Absence is a removal; a concrete value
  changing to or from `null` is a type/nullability change.
- JSON integer and fractional observations both normalize to `number`. A serialization change such
  as `1` to `1.0` therefore does not create drift.
- Boolean remains a separate type and is checked before Python's numeric types.

Observed arrays follow bounded union-of-elements analysis:

- The array field remains typed as `array`; element paths use wildcard notation such as
  `items[].id`.
- The first 20 elements of each array are inspected. Their paths and runtime types are unioned, so
  a field present in any inspected object element is part of that observation's structure.
- Heterogeneous element types form a sorted type union such as `null|number|string`.
- An empty array is inconclusive about its element structure. It does not imply removal of nested
  paths already present in the accepted baseline.
- Elements beyond the inspection cap remain in the stored raw snapshot but do not influence drift
  comparison.

## Consequences

### Positive

- Transient deviations can recover without generating paired removal/addition alerts.
- Slow changes cannot silently redefine the accepted contract through previous-snapshot chaining.
- Baseline promotion is explicit, tenant-scoped, and auditable.
- Drift incidents and optional agent runs receive only confirmed structural signals.

### Negative

- Real changes are reported after three matching observations rather than after one poll.
- Operators must accept legitimate changes before they become the comparison baseline.
- Baseline lifecycle storage and an additional migration are required.
- Array evidence beyond the first 20 elements is intentionally ignored, so late heterogeneous
  shapes can remain undetected.

## API and Proof

- Read active state: `GET /api/v1/contracts/sources/{source_id}/baseline`.
- Accept current candidate: `POST /api/v1/contracts/sources/{source_id}/baseline/accept`.
- Persistence and comparison behavior:
  [`contract_drift.py`](../../../services/ingestor/repositories/contract_drift.py).
- Migration:
  [`b771ac41bc8f_add_contract_baselines.py`](../../../alembic/versions/b771ac41bc8f_add_contract_baselines.py).
- Focused behavior tests:
  [`test_contract_drift_api.py`](../../../services/ingestor/tests/integration/test_contract_drift_api.py).

## Rollback

Application rollback remains compatible because existing snapshot and drift-event columns are not
removed. Database downgrade removes baseline history and returns the older previous-snapshot
comparison behavior; do not downgrade after operators begin relying on accepted-baseline audit
history without first exporting that history.
