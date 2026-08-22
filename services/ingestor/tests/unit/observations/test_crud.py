from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from services.ingestor.api_schemas.observations import (
    ObservationRequest,
    UpdateObservationRequest,
)
from services.ingestor.models import Observation
from services.ingestor.repositories.observations import (
    create_observation,
    create_observations_batch,
    delete_observation,
    get_observation,
    mark_processed,
    soft_delete_observation,
    update_observation,
    upsert_observation,
)
from services.ingestor.storage.events import claim_pending_events


def _make_result(scalars_all=None, scalar_one=None):
    """Create a mock SQLAlchemy result object."""
    result = MagicMock()
    if scalars_all is not None:
        result.scalars.return_value.all.return_value = scalars_all
    if scalar_one is not None:
        result.scalar_one_or_none.return_value = scalar_one
    return result


def _mock_resolve_source_id(return_value: int = 42):
    return patch(
        "services.ingestor.repositories.observations_crud._resolve_source_id",
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# create_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateObservation:
    """create_observation persists and refreshes the ORM instance."""

    async def test_create_observation_persists_and_returns(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with (
            _mock_resolve_source_id(),
            patch(
                "services.ingestor.repositories.observations_crud.get_tenant_id",
                return_value="tenant-1",
            ),
        ):
            await create_observation(
                mock_session,
                ObservationRequest(
                    source="test-source",
                    timestamp="2024-01-01T00:00:00",
                    data={"key": "value"},
                    tags=[],
                ),
            )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_create_observation_sets_tenant_id(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with (
            _mock_resolve_source_id(),
            patch(
                "services.ingestor.repositories.observations_crud.get_tenant_id",
                return_value="custom-tenant",
            ),
        ):
            result = await create_observation(
                mock_session,
                ObservationRequest(
                    source="src",
                    timestamp="2024-01-01T00:00:00",
                    data={},
                    tags=[],
                ),
            )

        assert result.tenant_id == "custom-tenant"


# ---------------------------------------------------------------------------
# create_observations_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateObservationsBatch:
    """create_observations_batch uses bulk insert."""

    async def test_batch_empty_returns_empty(self) -> None:
        mock_session = MagicMock()
        result = await create_observations_batch(mock_session, [])
        assert result == []
        mock_session.execute.assert_not_called()

    async def test_batch_inserts_multiple(self) -> None:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        mock_session.commit = AsyncMock()

        requests = [
            ObservationRequest(
                source=f"source-{i}",
                timestamp="2024-01-01T00:00:00",
                data={},
                tags=[],
            )
            for i in range(3)
        ]

        with (
            _mock_resolve_source_id(return_value=1),
            patch(
                "services.ingestor.repositories.observations_crud.get_tenant_id",
                return_value="tenant-1",
            ),
        ):
            await create_observations_batch(mock_session, requests)

        assert mock_session.execute.called
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetObservation:
    """get_observation returns the observation or None."""

    async def test_get_observation_found(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1

        mock_session.execute = AsyncMock(
            return_value=_make_result(scalar_one=mock_observation)
        )

        result = await get_observation(mock_session, 1)

        assert result is mock_observation

    async def test_get_observation_not_found(self) -> None:
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_observation(mock_session, 999)

        assert result is None


# ---------------------------------------------------------------------------
# mark_processed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMarkProcessed:
    """mark_processed is idempotent — sets processed_at only once."""

    async def test_mark_processed_sets_flag_and_timestamp(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.processed = False
        mock_observation.processed_at = None

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await mark_processed(mock_session, 1)

        assert result is mock_observation
        assert mock_observation.processed is True
        assert mock_observation.processed_at is not None
        mock_session.commit.assert_called_once()

    async def test_mark_processed_idempotent(self) -> None:
        """Second call does not overwrite processed_at."""
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.processed = True
        mock_observation.processed_at = "2024-01-01T00:00:00"

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await mark_processed(mock_session, 1)

        assert result is mock_observation
        assert mock_observation.processed_at == "2024-01-01T00:00:00"

    async def test_mark_processed_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=None)

        result = await mark_processed(mock_session, 999)

        assert result is None
        mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# update_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateObservation:
    """update_observation performs partial updates."""

    async def test_update_observation_found(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.source_id = 1
        mock_observation.timestamp = "2024-01-01T00:00:00"
        mock_observation.raw_data = {"old": "data"}
        mock_observation.tags = None

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with _mock_resolve_source_id(return_value=42):
            result = await update_observation(
                mock_session,
                1,
                UpdateObservationRequest(source="new-source"),
            )

        assert result is mock_observation
        assert mock_observation.source_id == 42
        assert mock_observation.timestamp == "2024-01-01T00:00:00"  # unchanged

    async def test_update_observation_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=None)

        with _mock_resolve_source_id():
            result = await update_observation(
                mock_session,
                999,
                UpdateObservationRequest(source="new-source"),
            )

        assert result is None
        mock_session.commit.assert_not_called()

    async def test_update_observation_partial(self) -> None:
        """Only provided fields are updated."""
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.source_id = 7
        mock_observation.timestamp = "2024-01-01T00:00:00"
        mock_observation.raw_data = {"key": "val"}
        mock_observation.tags = ["tag1"]

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with _mock_resolve_source_id():
            await update_observation(
                mock_session,
                1,
                UpdateObservationRequest(tags=["tag2", "tag3"]),
            )

        assert mock_observation.tags == ["tag2", "tag3"]
        assert mock_observation.source_id == 7  # unchanged


# ---------------------------------------------------------------------------
# delete_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteObservation:
    """delete_observation hard-deletes the row."""

    async def test_delete_observation_found(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await delete_observation(mock_session, 1)

        assert result is mock_observation
        mock_session.delete.assert_called_once_with(mock_observation)
        mock_session.commit.assert_called_once()

    async def test_delete_observation_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=None)

        result = await delete_observation(mock_session, 999)

        assert result is None
        mock_session.delete.assert_not_called()


# ---------------------------------------------------------------------------
# soft_delete_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSoftDeleteObservation:
    """soft_delete_observation sets deleted_at only if not already deleted."""

    async def test_soft_delete_sets_deleted_at(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.deleted_at = None

        mock_session.get = AsyncMock(return_value=mock_observation)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await soft_delete_observation(mock_session, 1)

        assert result is mock_observation
        assert mock_observation.deleted_at is not None
        mock_session.commit.assert_called_once()

    async def test_soft_delete_already_deleted(self) -> None:
        mock_session = MagicMock()
        mock_observation = MagicMock(spec=Observation)
        mock_observation.id = 1
        mock_observation.deleted_at = "2024-01-01T00:00:00"

        mock_session.get = AsyncMock(return_value=mock_observation)

        result = await soft_delete_observation(mock_session, 1)

        assert result is None
        mock_session.commit.assert_not_called()

    async def test_soft_delete_not_found(self) -> None:
        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=None)

        result = await soft_delete_observation(mock_session, 999)

        assert result is None


# ---------------------------------------------------------------------------
# claim_pending_events
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClaimPendingEvents:
    """claim_pending_events atomically claims a batch."""

    async def test_claim_returns_empty_list_when_no_pending(self) -> None:
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        result = await claim_pending_events(mock_session, 10)

        assert result == []
        mock_session.commit.assert_called_once()

    async def test_claim_sets_status_and_increments_attempts(self) -> None:
        mock_session = MagicMock()
        mock_event = MagicMock()
        mock_event.status = "pending"
        mock_event.processing_attempts = 0

        mock_session.execute = AsyncMock(
            return_value=_make_result(scalars_all=[mock_event])
        )
        mock_session.commit = AsyncMock()

        result = await claim_pending_events(mock_session, 10)

        assert len(result) == 1
        assert mock_event.status == "processing"
        assert mock_event.processing_attempts == 1
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# upsert_observation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpsertObservation:
    """upsert_observation inserts or returns existing on conflict."""

    async def test_upsert_inserts_new(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with (
            _mock_resolve_source_id(return_value=1),
            patch(
                "services.ingestor.repositories.observations_crud.get_tenant_id",
                return_value="tenant-1",
            ),
        ):
            result, created = await upsert_observation(
                mock_session,
                ObservationRequest(
                    source="src",
                    timestamp="2024-01-01T00:00:00",
                    data={"key": "val"},
                    tags=[],
                ),
            )

        assert created is True
        mock_session.add.assert_called_once()

    async def test_upsert_returns_existing_on_conflict(self) -> None:
        mock_session = MagicMock()
        existing = MagicMock(spec=Observation)
        existing.id = 1

        mock_session.flush = AsyncMock(side_effect=IntegrityError("unique", None, None))
        mock_session.rollback = AsyncMock()
        mock_session.execute = AsyncMock(return_value=_make_result(scalar_one=existing))
        mock_session.refresh = AsyncMock()

        with (
            _mock_resolve_source_id(return_value=1),
            patch(
                "services.ingestor.repositories.observations_crud.get_tenant_id",
                return_value="tenant-1",
            ),
        ):
            result, created = await upsert_observation(
                mock_session,
                ObservationRequest(
                    source="src",
                    timestamp="2024-01-01T00:00:00",
                    data={"key": "val"},
                    tags=[],
                ),
            )

        assert created is False
        assert result is existing
        # add() IS called (before flush raises IntegrityError)
        mock_session.add.assert_called_once()
