from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

import services.ingestor.vector_search as vector_search
from services.ingestor.models import Observation


pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        json: dict[str, Any],
        timeout: int,
    ) -> _FakeResponse:
        self.calls.append(
            {"method": "POST", "url": url, "json": json, "timeout": timeout}
        )
        if url.endswith("/index"):
            return _FakeResponse({"indexed_count": 1, "collection": json["collection"]})
        return _FakeResponse({"results": [], "count": 0, "query": json["query"]})

    async def get(self, url: str, timeout: int) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url, "timeout": timeout})
        return _FakeResponse({"status": "ok", "qdrant_connected": True})


def _build_observation() -> Observation:
    return Observation(
        id=42,
        source="vector.example",
        timestamp=datetime(2026, 4, 23, 12, 0, 0),
        raw_data={"summary": "semantic text", "value": 99},
        tags=["alpha", "beta"],
        processed=True,
    )


def test_build_observation_search_document_contains_searchable_text() -> None:
    observation = _build_observation()

    document = vector_search.build_observation_search_document(observation)

    assert document["id"] == 42
    assert "source: vector.example" in document["text"]
    assert '"summary": "semantic text"' in document["text"]
    assert document["metadata"]["tags"] == ["alpha", "beta"]


async def test_index_observation_documents_calls_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeHttpClient()

    async def _fake_get_http_client() -> _FakeHttpClient:
        return client

    monkeypatch.setattr(vector_search, "get_http_client", _fake_get_http_client)

    result = await vector_search.index_observation_documents([_build_observation()])

    assert result["indexed_count"] == 1
    assert client.calls[0]["url"].endswith("/index")


async def test_get_vector_search_health_calls_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeHttpClient()

    async def _fake_get_http_client() -> _FakeHttpClient:
        return client

    monkeypatch.setattr(vector_search, "get_http_client", _fake_get_http_client)

    result = await vector_search.get_vector_search_health()

    assert result["status"] == "ok"
    assert client.calls[0]["method"] == "GET"


async def test_search_uses_explicit_collection_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeHttpClient()

    async def _fake_get_http_client() -> _FakeHttpClient:
        return client

    monkeypatch.setattr(vector_search, "get_http_client", _fake_get_http_client)

    result = await vector_search.search_observation_documents(
        "slow dependency",
        top_k=3,
        collection="tenant-42",
        filters={"source": "payments"},
    )

    assert result["count"] == 0
    assert client.calls[0]["json"] == {
        "query": "slow dependency",
        "top_k": 3,
        "collection": "tenant-42",
        "filters": {"source": "payments"},
    }


@pytest.mark.parametrize(
    ("operation", "args"),
    [
        ("index", ([_build_observation()],)),
        ("search", ("dependency", 1)),
        ("health", ()),
    ],
)
async def test_gateway_non_object_responses_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    args: tuple[Any, ...],
) -> None:
    client = _FakeHttpClient()

    async def _fake_get_http_client() -> _FakeHttpClient:
        return client

    monkeypatch.setattr(vector_search, "get_http_client", _fake_get_http_client)
    monkeypatch.setattr(
        vector_search.inference_resilience,
        "call",
        AsyncMock(return_value=_FakeResponse([])),
    )

    functions = {
        "index": vector_search.index_observation_documents,
        "search": vector_search.search_observation_documents,
        "health": vector_search.get_vector_search_health,
    }
    with pytest.raises(ValueError, match="non-object"):
        await functions[operation](*args)
