"""Unit tests for contract drift repository async DB functions.

Mock-based tests for get_active_contract_baseline, _clear_candidate,
get_source_snapshots, get_source_drift_events, get_compatibility_report,
accept_contract_baseline, and create_contract_snapshot.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.api_schemas.contract_drift import ContractSnapshotCreate
from services.ingestor.constants import (
    CONTRACT_BASELINE_CONFIRMATION_POLLS,
    CONTRACT_COMPATIBILITY_MAX_SCORE,
)
from services.ingestor.models import (
    ContractBaseline,
    ContractSnapshot,
    DriftEvent,
    SourceProfile,
)
from services.ingestor.repositories import contract_drift as cd
from services.ingestor.repositories.incidents import IncidentTransition


def _result_scalar(value):
    """Mock a SQLAlchemy scalar result (for db.scalar)."""
    return value


def _result_scalars_all(items):
    """Mock a SQLAlchemy result with .scalars().all() returning items."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _result_all_rows(rows):
    """Mock a SQLAlchemy result with .all() returning rows (for count subqueries)."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _make_baseline(
    id=1,
    source_id=1,
    tenant_id=42,
    baseline_snapshot_id=10,
    version=1,
    candidate_snapshot_id=None,
    candidate_schema_fingerprint=None,
    candidate_observation_count=0,
    candidate_drift_event_id=None,
    candidate_first_seen_at=None,
    candidate_last_seen_at=None,
):
    b = MagicMock(spec=ContractBaseline)
    b.id = id
    b.source_id = source_id
    b.tenant_id = tenant_id
    b.baseline_snapshot_id = baseline_snapshot_id
    b.version = version
    b.candidate_snapshot_id = candidate_snapshot_id
    b.candidate_schema_fingerprint = candidate_schema_fingerprint
    b.candidate_observation_count = candidate_observation_count
    b.candidate_drift_event_id = candidate_drift_event_id
    b.candidate_first_seen_at = candidate_first_seen_at
    b.candidate_last_seen_at = candidate_last_seen_at
    return b


def _make_snapshot(id=10, source_id=1, payload_schema=None, compatibility_score=100.0):
    s = MagicMock(spec=ContractSnapshot)
    s.id = id
    s.source_id = source_id
    s.payload_schema = payload_schema or {"id": "number"}
    s.compatibility_score = compatibility_score
    return s


# ---------------------------------------------------------------------------
# _clear_candidate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClearCandidate:
    def test_clears_all_candidate_fields(self) -> None:
        baseline = _make_baseline(
            candidate_snapshot_id=10,
            candidate_schema_fingerprint="abc",
            candidate_observation_count=3,
            candidate_drift_event_id=5,
            candidate_first_seen_at=datetime(2025, 1, 1),
            candidate_last_seen_at=datetime(2025, 1, 2),
        )
        cd._clear_candidate(baseline)
        assert baseline.candidate_snapshot_id is None
        assert baseline.candidate_schema_fingerprint is None
        assert baseline.candidate_observation_count == 0
        assert baseline.candidate_drift_event_id is None
        assert baseline.candidate_first_seen_at is None
        assert baseline.candidate_last_seen_at is None


# ---------------------------------------------------------------------------
# get_active_contract_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetActiveContractBaseline:
    async def test_returns_active_baseline(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline()
        mock_db.scalar = AsyncMock(return_value=baseline)

        result = await cd.get_active_contract_baseline(mock_db, source_id=1)

        assert result is baseline

    async def test_returns_none_when_no_baseline(self) -> None:
        mock_db = MagicMock()
        mock_db.scalar = AsyncMock(return_value=None)

        result = await cd.get_active_contract_baseline(mock_db, source_id=1)

        assert result is None

    async def test_with_for_update_calls_scalar_once(self) -> None:
        mock_db = MagicMock()
        mock_db.scalar = AsyncMock(return_value=_make_baseline())

        await cd.get_active_contract_baseline(mock_db, source_id=1, for_update=True)

        mock_db.scalar.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_source_snapshots
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSourceSnapshots:
    async def test_returns_rows_and_total(self) -> None:
        mock_db = MagicMock()
        snaps = [_make_snapshot(id=10, source_id=1), _make_snapshot(id=20, source_id=1)]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                r = MagicMock()
                r.scalar_one.return_value = 2
                return r
            return _make_result_scalars_all(snaps)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        rows, total = await cd.get_source_snapshots(
            mock_db, source_id=1, offset=0, limit=10
        )

        assert len(rows) == 2
        assert total == 2

    async def test_empty_result_returns_empty_and_zero(self) -> None:
        mock_db = MagicMock()

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            r = MagicMock()
            if call_count["n"] == 1:
                r.scalar_one.return_value = 0
                return r
            return _make_result_scalars_all([])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        rows, total = await cd.get_source_snapshots(
            mock_db, source_id=1, offset=0, limit=10
        )
        assert rows == []
        assert total == 0


def _make_result_scalars_all(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


# ---------------------------------------------------------------------------
# get_source_drift_events
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSourceDriftEvents:
    async def test_returns_rows_and_total(self) -> None:
        mock_db = MagicMock()
        events = [MagicMock(spec=DriftEvent), MagicMock(spec=DriftEvent)]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                r = MagicMock()
                r.scalar_one.return_value = 2
                return r
            return _make_result_scalars_all(events)

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        rows, total = await cd.get_source_drift_events(
            mock_db, source_id=1, offset=0, limit=10
        )
        assert len(rows) == 2
        assert total == 2


# ---------------------------------------------------------------------------
# get_compatibility_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCompatibilityReport:
    async def test_no_latest_snapshot_returns_clean(self) -> None:
        mock_db = MagicMock()
        mock_db.scalar = AsyncMock(return_value=None)

        result = await cd.get_compatibility_report(mock_db, source_id=1)

        assert result.latest_snapshot_id is None
        assert result.compatibility_score == CONTRACT_COMPATIBILITY_MAX_SCORE
        assert result.drift_detected is False

    async def test_latest_without_baseline_returns_no_drift(self) -> None:
        mock_db = MagicMock()
        snapshot = _make_snapshot(id=10, source_id=1, payload_schema={"id": "number"})

        call_count = {"n": 0}

        async def scalar_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return snapshot
            return None  # no baseline

        mock_db.scalar = AsyncMock(side_effect=scalar_side_effect)

        result = await cd.get_compatibility_report(mock_db, source_id=1)

        assert result.latest_snapshot_id == 10
        assert result.previous_snapshot_id is None
        assert result.drift_detected is False

    async def test_missing_baseline_snapshot_raises(self) -> None:
        mock_db = MagicMock()
        snapshot = _make_snapshot(id=10, source_id=1, payload_schema={"id": "number"})
        baseline = _make_baseline(baseline_snapshot_id=99, candidate_snapshot_id=None)

        call_count = {"n": 0}

        async def scalar_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return snapshot
            return baseline

        mock_db.scalar = AsyncMock(side_effect=scalar_side_effect)
        mock_db.get = AsyncMock(return_value=None)  # baseline snapshot missing

        with pytest.raises(RuntimeError, match="missing"):
            await cd.get_compatibility_report(mock_db, source_id=1)

    async def test_drift_detected_between_baseline_and_latest(self) -> None:
        mock_db = MagicMock()
        baseline_snapshot = _make_snapshot(
            id=5, source_id=1, payload_schema={"id": "number", "old_field": "string"}
        )
        latest = _make_snapshot(
            id=10, source_id=1, payload_schema={"id": "number", "new_field": "string"}
        )
        baseline = _make_baseline(baseline_snapshot_id=5, candidate_snapshot_id=None)

        call_count = {"n": 0}

        async def scalar_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return latest
            return baseline

        mock_db.scalar = AsyncMock(side_effect=scalar_side_effect)
        mock_db.get = AsyncMock(return_value=baseline_snapshot)

        result = await cd.get_compatibility_report(mock_db, source_id=1)

        assert result.drift_detected is True
        assert result.removed_fields == ["old_field"]
        assert result.added_fields == ["new_field"]
        assert result.event_type == "breaking"


# ---------------------------------------------------------------------------
# accept_contract_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAcceptContractBaseline:
    async def test_no_candidate_raises(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline(candidate_snapshot_id=None)

        with pytest.raises(ValueError, match="No candidate"):
            await cd.accept_contract_baseline(
                mock_db, baseline, actor="admin", acceptance_note="ok"
            )

    async def test_wrong_candidate_raises(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline(candidate_snapshot_id=10)

        with pytest.raises(ValueError, match="not the current contract candidate"):
            await cd.accept_contract_baseline(
                mock_db,
                baseline,
                actor="admin",
                acceptance_note="ok",
                candidate_snapshot_id=99,
            )

    async def test_missing_snapshot_raises(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline(candidate_snapshot_id=10, baseline_snapshot_id=5)
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="unavailable"):
            await cd.accept_contract_baseline(
                mock_db, baseline, actor="admin", acceptance_note="ok"
            )

    async def test_snapshot_tenant_mismatch_raises(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline(
            candidate_snapshot_id=10, baseline_snapshot_id=5, source_id=1, tenant_id=42
        )
        snap = _make_snapshot(id=10, source_id=2)  # different source
        mock_db.get = AsyncMock(return_value=snap)

        with pytest.raises(ValueError, match="unavailable"):
            await cd.accept_contract_baseline(
                mock_db, baseline, actor="admin", acceptance_note="ok"
            )

    async def test_successful_accept_creates_new_baseline(self) -> None:
        mock_db = MagicMock()
        baseline = _make_baseline(
            id=1,
            candidate_snapshot_id=10,
            baseline_snapshot_id=5,
            version=1,
            source_id=1,
            tenant_id=42,
        )
        snap = _make_snapshot(id=10, source_id=1)
        mock_db.get = AsyncMock(return_value=snap)
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await cd.accept_contract_baseline(
            mock_db, baseline, actor="admin", acceptance_note="approved"
        )

        assert result.status == "active"
        assert result.version == 2
        assert result.accepted_by == "admin"
        assert result.accepted_by == "admin"
        assert baseline.status == "superseded"
        assert baseline.active_key is None
        mock_db.add.assert_called()


# ---------------------------------------------------------------------------
# create_contract_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateContractSnapshot:
    async def test_source_not_found_returns_none_none(self) -> None:
        mock_db = MagicMock()
        mock_db.scalar = AsyncMock(return_value=None)

        result, drift = await cd.create_contract_snapshot(
            mock_db,
            ContractSnapshotCreate(source_id=1, payload_schema={"id": "number"}),
        )
        assert result is None
        assert drift is None

    async def test_no_baseline_creates_initial_baseline(self) -> None:
        mock_db = MagicMock()
        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = 42
        source.name = "api"

        snapshot_calls = {"n": 0}

        async def scalar_side_effect(stmt):
            snapshot_calls["n"] += 1
            if snapshot_calls["n"] == 1:
                return source
            return None  # no existing baseline

        mock_db.scalar = AsyncMock(side_effect=scalar_side_effect)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch.object(
            cd, "get_active_contract_baseline", new=AsyncMock(return_value=None)
        ):
            snapshot, drift = await cd.create_contract_snapshot(
                mock_db,
                ContractSnapshotCreate(source_id=1, payload_schema={"id": "number"}),
            )

        assert drift is None
        assert snapshot is not None
        mock_db.commit.assert_called_once()

    async def test_no_drift_clears_candidate(self) -> None:
        mock_db = MagicMock()
        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = 42
        source.name = "api"

        baseline_snapshot = MagicMock(spec=ContractSnapshot)
        baseline_snapshot.payload_schema = {"id": "number", "name": "string"}

        snapshot = MagicMock(spec=ContractSnapshot)
        snapshot.id = 10
        snapshot.source_id = 1
        snapshot.compatibility_score = 100.0

        baseline = _make_baseline(
            candidate_snapshot_id=10,
            candidate_schema_fingerprint="abc",
            candidate_observation_count=3,
            baseline_snapshot_id=5,
        )

        mock_db.scalar = AsyncMock(return_value=source)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.get = AsyncMock(return_value=baseline_snapshot)

        with (
            patch.object(
                cd, "get_active_contract_baseline", new=AsyncMock(return_value=baseline)
            ),
            patch.object(cd, "enqueue_incident_notification_requests", new=AsyncMock()),
            patch.object(cd, "dispatch_incident_transitions", new=AsyncMock()),
        ):
            result_snapshot, drift = await cd.create_contract_snapshot(
                mock_db,
                ContractSnapshotCreate(
                    source_id=1, payload_schema={"id": "number", "name": "string"}
                ),
            )

        assert drift is None
        assert result_snapshot is not None
        mock_db.commit.assert_called_once()

    async def test_breaking_drift_creates_event_and_incident(self) -> None:
        mock_db = MagicMock()
        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = 42
        source.name = "api"

        baseline_snapshot = MagicMock(spec=ContractSnapshot)
        baseline_snapshot.id = 5
        baseline_snapshot.payload_schema = {"id": "number", "old_field": "string"}
        baseline_snapshot.source_id = 1

        snapshot = MagicMock(spec=ContractSnapshot)
        snapshot.id = 10
        snapshot.source_id = 1
        snapshot.compatibility_score = 80.0

        baseline = _make_baseline(
            candidate_snapshot_id=10,
            candidate_schema_fingerprint=cd._structure_fingerprint(
                cd._flatten_schema({"id": "number", "new_field": "string"})
            ),
            candidate_observation_count=CONTRACT_BASELINE_CONFIRMATION_POLLS - 1,
            candidate_drift_event_id=None,
            baseline_snapshot_id=5,
        )

        mock_db.scalar = AsyncMock(return_value=source)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.get = AsyncMock(return_value=baseline_snapshot)

        enqueue_mock = AsyncMock()
        dispatch_mock = AsyncMock()

        with (
            patch.object(
                cd, "get_active_contract_baseline", new=AsyncMock(return_value=baseline)
            ),
            patch.object(
                cd,
                "open_or_update_incident",
                new=AsyncMock(
                    return_value=IncidentTransition(MagicMock(), "opened", True)
                ),
            ),
            patch.object(
                cd, "enqueue_incident_notification_requests", new=enqueue_mock
            ),
            patch.object(cd, "dispatch_incident_transitions", new=dispatch_mock),
            patch.object(cd.pubsub, "publish_drift_event", new=AsyncMock()),
        ):
            result_snapshot, drift = await cd.create_contract_snapshot(
                mock_db,
                ContractSnapshotCreate(
                    source_id=1,
                    payload_schema={"id": "number", "new_field": "string"},
                ),
            )

        assert drift is not None
        assert drift.event_type == "breaking"
        assert drift.severity == "medium"  # score 78 = 100 - 2 - 20
        enqueue_mock.assert_awaited_once()
        dispatch_mock.assert_awaited_once()
