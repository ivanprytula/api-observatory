import pytest
from httpx import AsyncClient

from tests.shared.payloads import OBSERVATION_API


pytestmark = pytest.mark.integration


class TestConnectionPoolBasics:
    async def test_single_request_uses_pool(self, client: AsyncClient) -> None:
        """Verify a single request succeeds (pool is working)."""
        response = await client.post("/api/v1/observations", json=OBSERVATION_API)
        assert response.status_code == 201
        observation = response.json()
        assert observation["id"] is not None
        assert observation["source"] == OBSERVATION_API["source"]

    async def test_sequential_requests_reuse_connections(
        self, client: AsyncClient
    ) -> None:
        """Verify sequential requests work (connection pool reuses)."""
        for i in range(5):
            payload = {**OBSERVATION_API, "source": f"sequential-{i}"}
            response = await client.post("/api/v1/observations", json=payload)
            assert response.status_code == 201
            assert response.json()["id"] is not None

    async def test_read_after_write(self, client: AsyncClient) -> None:
        """Verify read operations work after writes."""
        # Create a observation
        create_resp = await client.post("/api/v1/observations", json=OBSERVATION_API)
        assert create_resp.status_code == 201
        observation_id = create_resp.json()["id"]

        # Read it back
        read_resp = await client.get(f"/api/v1/observations/{observation_id}")
        assert read_resp.status_code == 200
        observation = read_resp.json()
        assert observation["id"] == observation_id
        assert observation["source"] == OBSERVATION_API["source"]

    async def test_delete_operation_uses_pool(self, client: AsyncClient) -> None:
        """Verify delete operations work with pool."""
        # Create a observation
        create_resp = await client.post("/api/v1/observations", json=OBSERVATION_API)
        assert create_resp.status_code == 201
        observation_id = create_resp.json()["id"]

        # Delete it
        delete_resp = await client.delete(f"/api/v1/observations/{observation_id}")
        assert delete_resp.status_code == 204

    async def test_list_with_pagination_uses_pool(self, client: AsyncClient) -> None:
        """Verify pagination queries work within pool constraints."""
        # Create a few observations
        for i in range(3):
            payload = {**OBSERVATION_API, "source": f"paginate-{i}"}
            resp = await client.post("/api/v1/observations", json=payload)
            assert resp.status_code == 201

        # List with pagination
        list_resp = await client.get("/api/v1/observations?skip=0&limit=10")
        assert list_resp.status_code == 200

    async def test_patch_operation_uses_pool(self, client: AsyncClient) -> None:
        """Verify PATCH operations work with pool."""
        # Create a observation
        create_resp = await client.post("/api/v1/observations", json=OBSERVATION_API)
        assert create_resp.status_code == 201
        observation_id = create_resp.json()["id"]

        # Update it with PATCH
        update_payload = {"source": "updated-source"}
        patch_resp = await client.patch(
            f"/api/v1/observations/{observation_id}", json=update_payload
        )
        assert patch_resp.status_code == 200
        updated = patch_resp.json()
        assert updated["source"] == "updated-source"

    async def test_pool_configuration_is_set(self) -> None:
        """Verify pool configuration matches settings."""
        from services.ingestor.core.config import settings

        # Settings should reflect pool size
        assert settings.db_pool_size == 5
        assert settings.db_max_overflow == 10
        assert settings.db_pool_timeout == 30

    async def test_multiple_create_read_sequences(self, client: AsyncClient) -> None:
        """Test alternating creates and reads to verify pool stability."""
        created_ids = []

        # Create 3 observations
        for i in range(3):
            payload = {**OBSERVATION_API, "source": f"mixed-{i}"}
            resp = await client.post("/api/v1/observations", json=payload)
            assert resp.status_code == 201
            created_ids.append(resp.json()["id"])

        # Read all of them back
        for observation_id in created_ids:
            resp = await client.get(f"/api/v1/observations/{observation_id}")
            assert resp.status_code == 200
            assert resp.json()["id"] == observation_id
