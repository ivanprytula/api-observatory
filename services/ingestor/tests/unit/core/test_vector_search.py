"""Unit tests for the Pillar 9 AI gateway bridge."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

import services.ingestor.vector_search as vector_search
from services.ingestor.models import Record


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
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


def _build_record() -> Record:
    return Record(
        id=42,
        source="vector.example",
        timestamp=datetime(2026, 4, 23, 12, 0, 0),
        raw_data={"summary": "semantic text", "value": 99},
        tags=["alpha", "beta"],
        processed=True,
    )


def test_build_record_search_document_contains_searchable_text() -> None:
    record = _build_record()

    document = vector_search.build_record_search_document(record)

    assert document["id"] == 42
    assert "source: vector.example" in document["text"]
    assert '"summary": "semantic text"' in document["text"]
    assert document["metadata"]["tags"] == ["alpha", "beta"]


async def test_index_record_documents_calls_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeHttpClient()

    async def _fake_get_http_client() -> _FakeHttpClient:
        return client

    monkeypatch.setattr(vector_search, "get_http_client", _fake_get_http_client)

    result = await vector_search.index_record_documents([_build_record()])

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
