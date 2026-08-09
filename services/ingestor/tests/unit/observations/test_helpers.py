"""Unit tests for observations repository helpers and user management.

Pure helpers (_encode_cursor, _decode_cursor, _apply_tenant_filter) and
user/tenant management functions with mocked sessions.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.models import Tenant, User, UserTenant
from services.ingestor.repositories.observations import (
    _apply_tenant_filter,
    _decode_cursor,
    _encode_cursor,
    add_tenant_to_user,
    create_observations_batch_naive,
    create_user,
    get_observations,
    get_observations_by_date_range,
    get_observations_cursor_paginated,
    get_user_by_id,
    get_user_by_username,
    has_tenant_access,
    update_user_role,
)


# ---------------------------------------------------------------------------
# _encode_cursor / _decode_cursor
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCursorEncoding:
    def test_encode_round_trip(self) -> None:
        ts = datetime(2025, 1, 1, 12, 0, 0)
        cursor = _encode_cursor(42, ts)
        result = _decode_cursor(cursor)
        assert result is not None
        obs_id, decoded_ts = result
        assert obs_id == 42
        assert decoded_ts == ts

    def test_encode_without_timestamp(self) -> None:
        cursor = _encode_cursor(42, None)
        result = _decode_cursor(cursor)
        assert result is not None
        obs_id, decoded_ts = result
        assert obs_id == 42
        assert decoded_ts is None

    def test_decode_none_returns_none(self) -> None:
        assert _decode_cursor(None) is None

    def test_decode_empty_string_returns_none(self) -> None:
        assert _decode_cursor("") is None

    def test_decode_invalid_base64_returns_none(self) -> None:
        assert _decode_cursor("not-valid-base64!@#") is None

    def test_decode_invalid_json_returns_none(self) -> None:
        cursor = base64.b64encode(b"not json").decode("ascii")
        assert _decode_cursor(cursor) is None

    def test_encode_produces_valid_base64_json(self) -> None:
        cursor = _encode_cursor(1, datetime(2025, 6, 15, 10, 30))
        raw = base64.b64decode(cursor).decode("utf-8")
        data = json.loads(raw)
        assert data["id"] == 1
        assert data["timestamp"] == "2025-06-15T10:30:00"


# ---------------------------------------------------------------------------
# _apply_tenant_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyTenantFilter:
    def test_admin_bypass_no_filter(self) -> None:
        query = MagicMock()
        with (
            patch(
                "services.ingestor.repositories.observations.get_user_role",
                return_value="admin",
            ),
            patch(
                "services.ingestor.repositories.observations.get_tenant_id",
                return_value=42,
            ),
        ):
            result_query, filtered = _apply_tenant_filter(query)
        assert result_query is query
        assert filtered is False

    def test_non_admin_with_tenant_applies_filter(self) -> None:
        query = MagicMock()
        query.where = MagicMock(return_value=query)
        with (
            patch(
                "services.ingestor.repositories.observations.get_user_role",
                return_value="viewer",
            ),
            patch(
                "services.ingestor.repositories.observations.get_tenant_id",
                return_value=42,
            ),
        ):
            result_query, filtered = _apply_tenant_filter(query)

        query.where.assert_called_once()
        assert result_query is query
        assert filtered is True

    def test_non_admin_without_tenant_filters_to_global_only(self) -> None:
        query = MagicMock()
        query.where = MagicMock(return_value=query)
        with (
            patch(
                "services.ingestor.repositories.observations.get_user_role",
                return_value="viewer",
            ),
            patch(
                "services.ingestor.repositories.observations.get_tenant_id",
                return_value=None,
            ),
        ):
            result_query, filtered = _apply_tenant_filter(query)

        query.where.assert_called_once()
        assert result_query is query
        assert filtered is True


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetUserByUsername:
    async def test_returns_user_when_found(self) -> None:
        mock_session = MagicMock()
        user = MagicMock(spec=User)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        mock_session.execute = AsyncMock(return_value=result)

        found = await get_user_by_username(mock_session, "alice")
        assert found is user

    async def test_returns_none_when_not_found(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=result)

        found = await get_user_by_username(mock_session, "ghost")
        assert found is None


@pytest.mark.unit
class TestGetUserById:
    async def test_returns_user_when_found(self) -> None:
        mock_session = MagicMock()
        user = MagicMock(spec=User)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        mock_session.execute = AsyncMock(return_value=result)

        found = await get_user_by_id(mock_session, 1)
        assert found is user

    async def test_returns_none_when_not_found(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=result)

        found = await get_user_by_id(mock_session, 999)
        assert found is None


@pytest.mark.unit
class TestUpdateUserRole:
    async def test_updates_and_commits(self) -> None:
        mock_session = MagicMock()
        user = MagicMock(spec=User)
        user.role = "viewer"
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch(
            "services.ingestor.repositories.observations.get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            result = await update_user_role(mock_session, "alice", "admin")

        assert result is user
        assert user.role == "admin"
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(user)

    async def test_returns_none_when_user_not_found(self) -> None:
        mock_session = MagicMock()
        with patch(
            "services.ingestor.repositories.observations.get_user_by_username",
            new=AsyncMock(return_value=None),
        ):
            result = await update_user_role(mock_session, "ghost", "admin")
        assert result is None


@pytest.mark.unit
class TestCreateUser:
    async def test_auto_provisions_tenant_when_none(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        tenant_id = 1
        user_id = 2

        def _track_add(obj):
            if isinstance(obj, Tenant):
                obj.id = tenant_id
            elif isinstance(obj, User):
                obj.id = user_id

        mock_session.add.side_effect = _track_add

        user = await create_user(
            mock_session,
            username="alice",
            email="alice@x.com",
            password_hash="hash123",
        )

        assert user.tenant_id == tenant_id
        assert user.role == "viewer"
        mock_session.commit.assert_awaited_once()

    async def test_uses_explicit_tenant_id(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        user = await create_user(
            mock_session,
            username="bob",
            email="bob@x.com",
            password_hash="hash456",
            role="admin",
            tenant_id=99,
        )

        assert user.tenant_id == 99
        assert user.role == "admin"
        mock_session.commit.assert_awaited_once()


@pytest.mark.unit
class TestHasTenantAccess:
    async def test_returns_true_when_access_exists(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=MagicMock())
        mock_session.execute = AsyncMock(return_value=result)

        assert await has_tenant_access(mock_session, 1, 42) is True

    async def test_returns_false_when_no_access(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=result)

        assert await has_tenant_access(mock_session, 1, 99) is False


@pytest.mark.unit
class TestAddTenantToUser:
    async def test_successful_insert(self) -> None:
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await add_tenant_to_user(mock_session, 1, 42)
        assert isinstance(result, UserTenant)

    async def test_integrity_error_returns_existing(self) -> None:
        mock_session = MagicMock()
        existing = MagicMock(spec=UserTenant)
        existing.deleted_at = None
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=existing)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError("dup", None, None))
        mock_session.rollback = AsyncMock()
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.refresh = AsyncMock()

        res = await add_tenant_to_user(mock_session, 1, 42)
        assert res is existing
        assert existing.deleted_at is None

    async def test_integrity_error_reactivates_deleted(self) -> None:
        mock_session = MagicMock()
        existing = MagicMock(spec=UserTenant)
        existing.deleted_at = datetime(2025, 1, 1)
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=existing)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(
            side_effect=[IntegrityError("dup", None, None), None]
        )
        mock_session.rollback = AsyncMock()
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.refresh = AsyncMock()

        res = await add_tenant_to_user(mock_session, 1, 42)
        assert res is existing
        assert existing.deleted_at is None
        mock_session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# create_observations_batch_naive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateObservationsBatchNaive:
    async def test_empty_returns_empty(self) -> None:
        result = await create_observations_batch_naive(MagicMock(), [])
        assert result == []

    async def test_inserts_and_refreshes_each(self) -> None:
        mock_session = MagicMock()
        mock_session.add_all = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.tenant_id = None

        with patch(
            "services.ingestor.repositories.observations.get_tenant_id",
            return_value=42,
        ):
            reqs = [
                ObservationRequest(
                    source="s1", timestamp="2024-01-01T00:00:00", data={}, tags=[]
                ),
                ObservationRequest(
                    source="s2", timestamp="2024-01-01T00:01:00", data={}, tags=[]
                ),
            ]
            results = await create_observations_batch_naive(mock_session, reqs)

        assert len(results) == 2
        mock_session.add_all.assert_called_once()
        assert mock_session.refresh.await_count == 2


# ---------------------------------------------------------------------------
# get_observations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetObservations:
    async def test_returns_paginated_results(self) -> None:
        mock_session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5
        data_result = MagicMock()
        obs_list = [MagicMock(), MagicMock()]
        data_result.scalars.return_value.all.return_value = obs_list
        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            return count_result if call_count["n"] == 1 else data_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            observations, total = await get_observations(
                mock_session, skip=0, limit=10, source="api"
            )

        assert len(observations) == 2
        assert total == 5

    async def test_no_source_filter(self) -> None:
        mock_session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, data_result])

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            observations, total = await get_observations(mock_session)

        assert observations == []
        assert total == 0


# ---------------------------------------------------------------------------
# get_observations_cursor_paginated
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetObservationsCursorPaginated:
    async def test_first_page_no_cursor(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        mock_session.execute = AsyncMock(return_value=result)

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            (
                observations,
                next_cursor,
                has_more,
            ) = await get_observations_cursor_paginated(mock_session, limit=5)

        assert len(observations) == 2
        assert has_more is False
        assert next_cursor is None

    async def test_fewer_than_limit_no_next_cursor(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [MagicMock()]
        mock_session.execute = AsyncMock(return_value=result)

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            (
                observations,
                next_cursor,
                has_more,
            ) = await get_observations_cursor_paginated(mock_session, limit=10)

        assert has_more is False
        assert next_cursor is None

    async def test_cursor_decodes_and_filters(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        cursor = _encode_cursor(42, datetime(2025, 1, 1, 12, 0, 0))

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            (
                observations,
                next_cursor,
                has_more,
            ) = await get_observations_cursor_paginated(
                mock_session, cursor=cursor, limit=10
            )

        assert observations == []


# ---------------------------------------------------------------------------
# get_observations_by_date_range
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetObservationsByDateRange:
    async def test_returns_filtered_list(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        obs_list = [MagicMock(), MagicMock()]
        result.scalars.return_value.all.return_value = obs_list
        mock_session.execute = AsyncMock(return_value=result)

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 2)

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            observations = await get_observations_by_date_range(
                mock_session, start=start, end=end, source="api"
            )

        assert len(observations) == 2

    async def test_no_source_filter(self) -> None:
        mock_session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        with patch(
            "services.ingestor.repositories.observations.get_user_role",
            return_value="admin",
        ):
            observations = await get_observations_by_date_range(
                mock_session, datetime(2025, 1, 1), datetime(2025, 1, 2)
            )

        assert observations == []
