"""Pydantic request/response schemas for the inference service.

Wire contract is fixed by `services.ingestor.vector_search` (the existing
caller) — see `POST /index` and `POST /search` there for the exact shapes
this service must accept and return.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentIn(BaseModel):
    id: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    collection: str
    documents: list[DocumentIn]


class IndexResponse(BaseModel):
    collection: str
    indexed: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    collection: str
    filters: dict[str, Any] | None = None


class SearchResultItem(BaseModel):
    id: int
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    collection: str
    results: list[SearchResultItem]
