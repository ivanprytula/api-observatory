"""Inference service — pgvector-backed embeddings indexing and semantic search.

Implements the exact `/index` and `/search` interface that
`services.ingestor.vector_search` already calls (previously pointed at a
service that was never built, so RAG silently fell back to "no context").
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.inference.api_schemas import (
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
)
from services.inference.config import settings
from services.inference.database import get_db
from services.inference.search import index_documents, search_documents


logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("services.inference")

DbDep = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info(
        "inference_startup", extra={"embedding_model": settings.embedding_model_name}
    )
    yield
    logger.info("inference_shutdown")


app = FastAPI(title="API Observatory — Inference", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness — process is up. No dependency checks (see /readyz for that)."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(db: DbDep) -> dict[str, str]:
    """Readiness — can this instance actually serve traffic right now."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/index", response_model=IndexResponse, status_code=201)
async def index_endpoint(payload: IndexRequest, db: DbDep) -> IndexResponse:
    indexed = await index_documents(db, payload.collection, payload.documents)
    return IndexResponse(collection=payload.collection, indexed=indexed)


@app.post("/search", response_model=SearchResponse)
async def search_endpoint(payload: SearchRequest, db: DbDep) -> SearchResponse:
    results = await search_documents(
        db,
        payload.collection,
        payload.query,
        payload.top_k,
        filters=payload.filters,
    )
    return SearchResponse(collection=payload.collection, results=results)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.inference.main:app",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=8001,
    )
