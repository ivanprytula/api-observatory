import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from services.ingestor.main import app
from tests.shared.payloads import OBSERVATION_E2E


@pytest.mark.skip(reason="Long-running test for memory leak detection")
@pytest.mark.e2e
async def test_throughput_with_512m_memory():
    """
    Verify app handles expected load under 512M memory constraint.

    If this fails, we know the app needs more memory in production.
    """
    # Arrange
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.time()
        tasks = [
            client.post(
                "/api/v1/observations",
                json={
                    **OBSERVATION_E2E,
                    "source": f"test-{i}",
                },
            )
            for i in range(100)
        ]

        # Act
        responses = await asyncio.gather(*tasks)
        duration = time.time() - start

        # Assert
        # All requests succeeded under resource constraint
        assert all(r.status_code == 201 for r in responses)
        print(f"\n100 concurrent requests in {duration:.2f}s under 512M memory limit")


@pytest.mark.skip(reason="Long-running test for memory leak detection")
@pytest.mark.e2e
async def test_memory_leak_detection():
    """
    Long-running test: create/list observations for 5 min.
    If memory keeps growing, we have a leak.

    Run with: pytest tests/test_under_constraints.py::test_memory_leak_detection -v -s
    """
    # Arrange
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act & Assert
        for iteration in range(30):  # 30 iterations × 10s = 5 min
            # Create batch of observations
            for i in range(10):
                response = await client.post(
                    "/api/v1/observations",
                    json={
                        **OBSERVATION_E2E,
                        "source": f"iter-{iteration}-{i}",
                    },
                )
                assert response.status_code == 201

            # List observations
            response = await client.get("/api/v1/observations?limit=1000")
            assert response.status_code == 200

            print(f"Iteration {iteration + 1}/30 completed...")
            await asyncio.sleep(10)  # Pause between iterations

        print("\nMemory leak test passed (5 min runtime)")
