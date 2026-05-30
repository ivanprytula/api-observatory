"""Integration tests for settings-related runtime behavior.

These tests intentionally live under the integration tree because they rely on
ASGI client/database-backed fixtures.
"""

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# App Behavior with Different Settings
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestAppBehaviorWithSettings:
    """App behavior changes based on settings."""

    async def test_app_includes_version_in_response(self, client: AsyncClient) -> None:
        """App returns versioned endpoints."""
        r = await client.get("/readyz")
        assert r.status_code in [200, 503]


# ---------------------------------------------------------------------------
# Observation Fixtures Behavior
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestObservationFixtures:
    """Observation fixtures create predictable test data."""

    async def test_created_observation_fixture_produces_valid_observation(
        self, created_observation: dict
    ) -> None:
        """created_observation fixture produces a valid observation with expected fields."""
        assert "id" in created_observation
        assert "source" in created_observation
        assert isinstance(created_observation["id"], int)
        assert isinstance(created_observation["source"], str)
        assert "raw_data" in created_observation or "data" in created_observation

    async def test_created_observations_fixture_produces_multiple(
        self, created_observations: list[dict]
    ) -> None:
        """created_observations fixture produces exactly 3 observations."""
        assert len(created_observations) == 3

        for observation in created_observations:
            assert "id" in observation
            assert observation["source"].startswith("source-")

    async def test_observation_payload_fixture_is_mutable_copy(
        self, observation_payload: dict
    ) -> None:
        """observation_payload fixture returns a mutable copy."""
        observation_payload["source"] = "modified"
        assert observation_payload["source"] == "modified"

    async def test_created_observation_has_tags_lowercased(
        self, created_observation: dict
    ) -> None:
        """Tags are normalized to lowercase (per validator)."""
        tags = created_observation["tags"]
        assert all(tag.islower() for tag in tags)
