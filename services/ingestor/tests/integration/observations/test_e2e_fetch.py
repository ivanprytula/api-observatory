from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from services.ingestor.fetch import close_all_http_clients, fetch_from_external_api


pytestmark = [pytest.mark.e2e, pytest.mark.live]


@pytest.fixture(autouse=True)
async def _cleanup_http_clients() -> AsyncIterator[None]:
    yield
    await close_all_http_clients()


async def test_jsonplaceholder_is_reachable() -> None:
    """Verify the optional public demonstration endpoint when requested manually."""
    result = await fetch_from_external_api(
        "https://jsonplaceholder.typicode.com/posts/1",
        simulate_failures=False,
    )

    assert result["id"] == 1
    assert "title" in result
