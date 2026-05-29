"""AI gateway bridge for observation indexing and semantic search."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from services.ingestor.config import settings
from services.ingestor.fetch import get_http_client
from services.ingestor.models import Observation


def build_observation_search_document(observation: Observation) -> dict[str, Any]:
    """Convert one observation into the AI gateway indexing payload."""
    raw_data_json = json.dumps(observation.raw_data, sort_keys=True, default=str)
    tags_text = ", ".join(observation.tags) if observation.tags else ""

    text_parts = [
        f"source: {observation.source}",
        f"timestamp: {observation.timestamp.isoformat()}",
        f"tags: {tags_text}",
        f"data: {raw_data_json}",
    ]

    return {
        "id": observation.id,
        "text": "\n".join(text_parts),
        "metadata": {
            "source": observation.source,
            "timestamp": observation.timestamp.isoformat(),
            "tags": observation.tags,
            "processed": observation.processed,
        },
    }


async def index_observation_documents(
    observations: Sequence[Observation],
    collection: str | None = None,
) -> dict[str, Any]:
    """Send observation documents to the AI gateway indexing endpoint."""
    collection_name = collection or settings.vector_search_collection
    client = await get_http_client()
    response = await client.post(
        f"{settings.inference_url.rstrip('/')}/index",
        json={
            "collection": collection_name,
            "documents": [
                build_observation_search_document(observation)
                for observation in observations
            ],
        },
        timeout=settings.vector_search_http_timeout_seconds,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("AI gateway returned a non-object index response")
    return body


async def search_observation_documents(
    query: str,
    top_k: int,
    collection: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Query the AI gateway semantic-search endpoint for indexed observations."""
    collection_name = collection or settings.vector_search_collection
    client = await get_http_client()
    response = await client.post(
        f"{settings.inference_url.rstrip('/')}/search",
        json={
            "query": query,
            "top_k": top_k,
            "collection": collection_name,
            "filters": filters,
        },
        timeout=settings.vector_search_http_timeout_seconds,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("AI gateway returned a non-object search response")
    return body


async def get_vector_search_health() -> dict[str, Any]:
    """Read AI gateway health for the product-facing bridge."""
    client = await get_http_client()
    response = await client.get(
        f"{settings.inference_url.rstrip('/')}/health",
        timeout=settings.vector_search_http_timeout_seconds,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("AI gateway returned a non-object health response")
    return body
