"""Indexing and semantic search against the pgvector-backed document store."""

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.inference.api_schemas import DocumentIn, SearchResultItem
from services.inference.embeddings import embed_query, embed_texts
from services.inference.models import IndexedDocument


async def index_documents(
    db: AsyncSession, collection: str, documents: list[DocumentIn]
) -> int:
    """Embed and upsert documents into `collection`.

    Upsert on (collection, external_id): re-indexing the same source record
    (e.g. an Observation that got re-analyzed) updates its embedding in place
    rather than accumulating duplicates.
    """
    if not documents:
        return 0

    vectors = await run_in_threadpool(embed_texts, [doc.text for doc in documents])

    stmt = pg_insert(IndexedDocument).values(
        [
            {
                "collection": collection,
                "external_id": doc.id,
                "text": doc.text,
                "metadata_json": doc.metadata,
                "embedding": vector,
            }
            for doc, vector in zip(documents, vectors, strict=True)
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["collection", "external_id"],
        set_={
            "text": stmt.excluded.text,
            "metadata_json": stmt.excluded.metadata_json,
            "embedding": stmt.excluded.embedding,
        },
    )
    await db.execute(stmt)
    await db.commit()
    return len(documents)


async def search_documents(
    db: AsyncSession,
    collection: str,
    query: str,
    top_k: int,
    filters: dict | None = None,
) -> list[SearchResultItem]:
    """Return the `top_k` documents in `collection` closest to `query` by
    cosine similarity, optionally narrowed by exact metadata containment."""
    query_vector = await run_in_threadpool(embed_query, query)

    distance = IndexedDocument.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(IndexedDocument, distance)
        .where(IndexedDocument.collection == collection)
        .order_by(distance)
        .limit(top_k)
    )
    if filters:
        stmt = stmt.where(IndexedDocument.metadata_json.contains(filters))

    rows = (await db.execute(stmt)).all()

    return [
        SearchResultItem(
            id=doc.external_id,
            text=doc.text,
            score=1.0 - float(distance),
            metadata=doc.metadata_json,
        )
        for doc, distance in rows
    ]
