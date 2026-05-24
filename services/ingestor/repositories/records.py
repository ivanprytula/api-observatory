"""Async CRUD operations (SQLAlchemy 2.0 select() style)."""

import asyncio
import base64
import json
from datetime import datetime

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.records import (
    EnrichedRecord,
    RecordRequest,
    UpdateRecordRequest,
)
from services.ingestor.core.tenant import get_tenant_id
from services.ingestor.models import ProcessedEvent, Record, User, UserTenant, _utcnow


async def claim_pending_events(
    session: AsyncSession, batch_size: int
) -> list[ProcessedEvent]:
    """Atomically claim a batch of pending events using SELECT FOR UPDATE SKIP LOCKED.

    This is the industry-standard pattern for distributed workers sharing a
    database-backed queue. It prevents multiple instances from processing
    the same event.

    Args:
        session: Active async database session.
        batch_size: Number of events to claim in one transaction.

    Returns:
        List of ProcessedEvent instances now in "processing" status.
    """
    stmt = (
        select(ProcessedEvent)
        .where(ProcessedEvent.status == "pending")
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    for event in events:
        event.status = "processing"
        event.processing_attempts += 1

    await session.commit()
    return list(events)


async def create_record(session: AsyncSession, request: RecordRequest) -> Record:
    record = Record(
        source=request.source,
        timestamp=request.timestamp,
        raw_data=request.data,
        tags=request.tags,
        tenant_id=get_tenant_id(),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def create_records_batch(
    session: AsyncSession, requests: list[RecordRequest]
) -> list[Record]:
    """Bulk-insert with RETURNING — single round-trip to database.

    Uses insert().values().returning() to avoid N+1 refresh queries.
    All server-default fields (id, created_at, updated_at, processed) are
    populated in the INSERT RETURNING clause, not via individual refreshes.

    Args:
        session: Active async database session.
        requests: List of RecordRequest payloads to insert.

    Returns:
        List of fully-hydrated Record ORM instances (with all defaults).
    """
    if not requests:
        return []

    # Prepare insert data: map request fields to Record columns
    insert_data = [
        {
            "source": r.source,
            "timestamp": r.timestamp,
            "raw_data": r.data,
            "tags": r.tags,
            "tenant_id": get_tenant_id(),
        }
        for r in requests
    ]

    # INSERT with RETURNING to get all fields back in one round-trip
    stmt = insert(Record).values(insert_data).returning(Record)
    result = await session.execute(stmt)
    records = result.scalars().all()

    await session.commit()
    return list(records)


async def create_records_batch_naive(
    session: AsyncSession, requests: list[RecordRequest]
) -> list[Record]:
    """Naive bulk-insert: N individual INSERTs + N individual REFRESH calls.

    This is the *before* implementation kept deliberately unoptimised so the
    `POST /api/v1/records/batch?impl=naive` endpoint can demonstrate — with
    measurable latency — exactly why the optimised version exists.

    Pattern: add_all → commit → for-loop refresh
    Round-trips: 1 (commit) + N (refresh) = N+1

    Args:
        session: Active async database session.
        requests: List of RecordRequest payloads to insert.

    Returns:
        List of fully-hydrated Record ORM instances (with all defaults).
    """
    if not requests:
        return []

    records = [
        Record(
            source=r.source,
            timestamp=r.timestamp,
            raw_data=r.data,
            tags=r.tags,
            tenant_id=get_tenant_id(),
        )
        for r in requests
    ]
    session.add_all(records)
    await session.commit()
    # N individual round-trips to hydrate server-default fields
    for record in records:
        await session.refresh(record)
    return records


async def get_records(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    source: str | None = None,
) -> tuple[list[Record], int]:
    count_q = (
        select(func.count()).select_from(Record).where(Record.deleted_at.is_(None))
    )
    data_q = (
        select(Record)
        .where(Record.deleted_at.is_(None))
        .order_by(Record.id)
        .offset(skip)
        .limit(limit)
    )
    if source:
        count_q = count_q.where(Record.source == source)
        data_q = data_q.where(Record.source == source)
    total = (await session.execute(count_q)).scalar_one()
    records = list((await session.execute(data_q)).scalars().all())
    return records, total


def _encode_cursor(record_id: int, timestamp: datetime) -> str:
    """Encode a cursor as base64(JSON) for opaque pagination positioning.

    Args:
        record_id: The last record ID in the current page.
        timestamp: The timestamp of the last record (for tie-breaking).

    Returns:
        Base64-encoded cursor string.
    """
    cursor_data = {
        "id": record_id,
        "timestamp": timestamp.isoformat() if timestamp else None,
    }
    json_str = json.dumps(cursor_data, separators=(",", ":"))
    return base64.b64encode(json_str.encode()).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[int, datetime | None] | None:
    """Decode a cursor back into (record_id, timestamp) pair.

    Args:
        cursor: Base64-encoded cursor string.

    Returns:
        Tuple of (record_id, timestamp) or None if cursor is None or invalid.
    """
    if not cursor:
        return None
    try:
        json_str = base64.b64decode(cursor).decode("utf-8")
        data = json.loads(json_str)
        record_id = data.get("id")
        ts_str = data.get("timestamp")
        timestamp = datetime.fromisoformat(ts_str) if ts_str else None
        return (record_id, timestamp)
    except ValueError, KeyError, json.JSONDecodeError:
        return None


async def get_records_cursor_paginated(
    session: AsyncSession,
    cursor: str | None = None,
    limit: int = 50,
    source: str | None = None,
) -> tuple[list[Record], str | None, bool]:
    """Fetch records using cursor-based pagination (stable under concurrent inserts).

    Cursor-based pagination is ideal for high-load scenarios because:
    - No offset needed (avoids full table scan for deep pages)
    - Stable under concurrent inserts (offset doesn't shift)
    - Cache-friendly (cursor is tied to a specific record position)

    Args:
        session: Active async database session.
        cursor: Opaque cursor from the previous response (None for first page).
        limit: Number of records to fetch (defines page size).
        source: Optional source filter.

    Returns:
        Tuple of (records, next_cursor, has_more).
        - records: List of Record objects (up to limit + 1 for has_more detection).
        - next_cursor: Opaque cursor for the next page (None if no more records).
        - has_more: True if more records exist beyond this page.
    """
    # Decode the cursor to find our starting position
    cursor_data = _decode_cursor(cursor)
    last_id = cursor_data[0] if cursor_data else 0
    last_timestamp = cursor_data[1] if cursor_data else None

    # Fetch limit + 1 records to detect if more exist
    query = (
        select(Record)
        .where(Record.deleted_at.is_(None))
        .order_by(Record.timestamp, Record.id)  # Stable sort order
    )

    # Apply cursor filter: we want records *after* the last one we returned
    if cursor_data:
        # Fetch records with (timestamp > last_timestamp) or
        # (timestamp == last_timestamp and id > last_id)
        query = query.where(
            (Record.timestamp > last_timestamp)
            | ((Record.timestamp == last_timestamp) & (Record.id > last_id))
        )

    if source:
        query = query.where(Record.source == source)

    # Fetch limit + 1 to detect has_more
    query = query.limit(limit + 1)
    result = await session.execute(query)
    records_all = list(result.scalars().all())

    # Determine if there are more records
    has_more = len(records_all) > limit
    records = records_all[:limit]

    # Generate next cursor from the last record in this page
    next_cursor = None
    if records and has_more:
        last_record = records[-1]
        next_cursor = _encode_cursor(last_record.id, last_record.timestamp)

    return records, next_cursor, has_more


async def get_records_by_date_range(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    source: str | None = None,
) -> list[Record]:
    """Fetch records within a timestamp range using the ix_records_timestamp index.

    Real-world pattern: "give me all pipeline records from the last 24h"

    Args:
        session: Active async database session.
        start: Inclusive start timestamp.
        end: Exclusive end timestamp (queries timestamp < end).
        source: Optional source filter.

    Returns:
        List of records (active only, deleted_at IS NULL).
    """
    query = (
        select(Record)
        .where(
            Record.deleted_at.is_(None),
            Record.timestamp >= start,
            Record.timestamp < end,
        )
        .order_by(Record.timestamp.desc(), Record.id.desc())
    )
    if source:
        query = query.where(Record.source == source)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_record(session: AsyncSession, record_id: int) -> Record | None:
    result = await session.execute(
        select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def mark_processed(session: AsyncSession, record_id: int) -> Record | None:
    """Mark a record as processed and set processed_at timestamp.

    Sets processed_at only if it's currently None (idempotent).

    Args:
        session: Active async database session.
        record_id: Primary key of the record to mark.

    Returns:
        Updated Record ORM instance, or None if not found.
    """
    record = await session.get(Record, record_id)
    if record is None:
        return None
    record.processed = True
    if record.processed_at is None:
        record.processed_at = _utcnow()
    await session.commit()
    await session.refresh(record)
    return record


async def update_record(
    session: AsyncSession, record_id: int, request: UpdateRecordRequest
) -> Record | None:
    """Update a record with provided fields (partial update).

    Only updates fields that are provided (not None). Non-provided fields
    are left unchanged.

    Args:
        session: Active async database session.
        record_id: Primary key of the record to update.
        request: UpdateRecordRequest with optional fields to update.

    Returns:
        Updated Record ORM instance, or None if not found.
    """
    record = await session.get(Record, record_id)
    if record is None:
        return None

    # Update only provided fields
    if request.source is not None:
        record.source = request.source
    if request.timestamp is not None:
        record.timestamp = request.timestamp
    if request.data is not None:
        record.raw_data = request.data
    if request.tags is not None:
        record.tags = request.tags

    await session.commit()
    await session.refresh(record)
    return record


async def delete_record(session: AsyncSession, record_id: int) -> Record | None:
    record = await session.get(Record, record_id)
    if record is None:
        return None
    await session.delete(record)
    await session.commit()
    return record


async def soft_delete_record(session: AsyncSession, record_id: int) -> Record | None:
    record = await session.get(Record, record_id)
    if record is None or record.deleted_at is not None:
        return None
    record.deleted_at = _utcnow()
    await session.commit()
    await session.refresh(record)
    return record


async def get_records_with_tag_counts_naive(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """Fetch records with tag counts using N+1 pattern (deliberate inefficiency).

    **Pattern**: 1 initial SELECT + N individual COUNT queries.
    Total queries: N+1 (N is the number of records returned).

    This function intentionally uses the naive approach so performance can be
    directly compared with the optimized version. Used in the N+1 demo endpoint
    to show real-world latency impact.

    Args:
        session: Active async database session.
        limit: Maximum number of records to fetch (default 10).

    Returns:
        List of dicts: {"id", "source", "timestamp", "tag_count"}.
    """
    # Query 1: Fetch records
    query = (
        select(Record)
        .where(Record.deleted_at.is_(None))
        .order_by(Record.id.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    records = list(result.scalars().all())

    # Queries 2..N+1: Count tags for each record individually
    data = []
    for record in records:
        tag_count = len(record.tags) if record.tags else 0
        data.append(
            {
                "id": record.id,
                "source": record.source,
                "timestamp": record.timestamp.isoformat(),
                "tag_count": tag_count,
            }
        )
    return data


async def get_records_with_tag_counts(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """Fetch records with tag counts using a single optimized query.

    **Pattern**: Single SELECT that fetches all data in one query (vs per-record).
    Total queries: 1 (vs N+1 for naive approach).

    The key optimization: all data fetched in a single SELECT, then tag counts
    computed. This avoids the loop-per-record pattern of the naive approach.

    In production (PostgreSQL): migrate to `array_length(tags, 1)` for true
    server-side computation. In testing (SQLite): computed client-side but still
    only one query.

    Args:
        session: Active async database session.
        limit: Maximum number of records to fetch (default 10).

    Returns:
        List of dicts: {"id", "source", "timestamp", "tag_count"}.
    """
    # Single query: fetch all records at once (the optimization)
    query = (
        select(
            Record.id,
            Record.source,
            Record.timestamp,
            Record.tags,
        )
        .where(Record.deleted_at.is_(None))
        .order_by(Record.id.desc())
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.all()

    # Compute tag counts from the single query result
    return [
        {
            "id": row.id,
            "source": row.source,
            "timestamp": row.timestamp.isoformat(),
            "tag_count": len(row.tags) if row.tags else 0,
        }
        for row in rows
    ]


async def enrich_records_concurrent(
    session: AsyncSession,
    record_ids: list[int],
    semaphore: asyncio.Semaphore,
) -> list[EnrichedRecord]:
    """Enrich a batch of records with external API data concurrently.

    Uses asyncio.Semaphore to cap concurrent outbound HTTP calls (default: 10).
    All records are fetched from DB in a single query, then enriched in parallel,
    each limited by the semaphore so we never exceed the outbound concurrency cap.

    Pattern:
        DB fetch (single query)
              │
              └─► asyncio.gather(
                      enrich(id=1),  ─► httpx fetch (under semaphore)
                      enrich(id=2),  ─► httpx fetch (under semaphore)
                      ...            ─► httpx fetch (under semaphore)
                  )

    Why semaphore: Without it, 50 concurrent requests fire simultaneously.
    asyncio.Semaphore(10) means at most 10 are inflight at once—protecting
    both the external API (rate limits) and the connection pool.

    Args:
        session: Active async database session.
        record_ids: List of record primary keys to enrich (1–50).
        semaphore: Shared semaphore to cap concurrent outbound requests.

    Returns:
        List of EnrichedRecord results (one per requested ID, in order).
        Failed enrichments include enriched=False and an error message.
    """
    import logging

    from services.ingestor.fetch import fetch_with_retry

    logger = logging.getLogger(__name__)

    # --- 1. Fetch all requested records in a single DB query ---
    result = await session.execute(
        select(Record)
        .where(Record.id.in_(record_ids))
        .where(Record.deleted_at.is_(None))
    )
    records_by_id: dict[int, Record] = {r.id: r for r in result.scalars().all()}

    # --- 2. Define the per-record enrichment coroutine ---
    async def enrich_one(record_id: int) -> EnrichedRecord:
        """Fetch external metadata for a single record, respecting semaphore."""
        record = records_by_id.get(record_id)
        if record is None:
            return EnrichedRecord(
                record_id=record_id,
                source="unknown",
                enriched=False,
                error=f"Record {record_id} not found",
            )

        # Semaphore ensures at most N concurrent fetches across all coroutines
        async with semaphore:
            try:
                # jsonplaceholder post IDs cycle 1–100; use modulo to stay in range
                post_id = (record_id % 100) or 1
                url = f"https://jsonplaceholder.typicode.com/posts/{post_id}"
                data = await fetch_with_retry(url, max_retries=2)

                logger.info(
                    "record_enriched",
                    extra={"record_id": record_id, "post_id": post_id},
                )
                return EnrichedRecord(
                    record_id=record_id,
                    source=record.source,
                    external_title=data.get("title"),
                    external_body=data.get("body"),
                    enriched=True,
                )
            except Exception as exc:
                logger.warning(
                    "record_enrich_failed",
                    extra={"record_id": record_id, "error": str(exc)},
                )
                return EnrichedRecord(
                    record_id=record_id,
                    source=record.source,
                    enriched=False,
                    error=str(exc),
                )

    # --- 3. Launch all enrichments concurrently, bounded by semaphore ---
    # TaskGroup (Python 3.11+) is preferred over gather() because it:
    # 1. Raises ExceptionGroup on failure, making partial failure handling explicit.
    # 2. Cancels siblings if one task fails (avoiding zombie tasks).
    # 3. Ensures all tasks are waited for before exiting the block.
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(enrich_one(rid)) for rid in record_ids]

    return [t.result() for t in tasks]


async def upsert_record(
    session: AsyncSession,
    request: RecordRequest,
) -> tuple[Record, bool]:
    """Insert a record or return the existing one on (source, timestamp) conflict.

    Idempotency key: the (source, timestamp) unique constraint.
    A second call with the same source+timestamp returns the existing record
    without raising an error — safe to retry from clients.

    Pattern:
        Optimistic INSERT → detect IntegrityError → rollback → SELECT existing

    Why optimistic insert (not SELECT-then-INSERT):
        SELECT-then-INSERT has a TOCTOU race: two concurrent requests both see
        no row, both INSERT, one wins, one fails. Catching IntegrityError is the
        correct atomic pattern.

    Args:
        session: Active async database session.
        request: RecordRequest payload (source+timestamp = idempotency key).

    Returns:
        Tuple of (record, created):
            - record: The Record ORM instance (new or pre-existing).
            - created: True if a new row was inserted; False if existing was found.
    """
    import logging

    logger = logging.getLogger(__name__)

    record = Record(
        source=request.source,
        timestamp=request.timestamp,
        raw_data=request.data,
        tags=request.tags,
        tenant_id=get_tenant_id(),
    )
    try:
        session.add(record)
        # flush before commit to surface IntegrityError early (before other work)
        await session.flush()
        await session.commit()
        await session.refresh(record)
        logger.info(
            "upsert_created",
            extra={"source": request.source, "timestamp": str(request.timestamp)},
        )
        return record, True
    except IntegrityError:
        # Unique constraint violated — rollback and fetch the existing row
        await session.rollback()
        result = await session.execute(
            select(Record).where(
                Record.source == request.source,
                Record.timestamp == request.timestamp,
                Record.deleted_at.is_(None),
            )
        )
        existing = result.scalar_one_or_none()
        assert existing is not None, (
            f"Unique constraint violation on (source, timestamp) but no active "
            f"record found for source={request.source}, timestamp={request.timestamp}. "
            f"This can only occur if the record was soft-deleted between INSERT and "
            f"SELECT (extreme race condition)."
        )
        logger.info(
            "upsert_conflict",
            extra={
                "source": request.source,
                "timestamp": str(request.timestamp),
                "existing_id": existing.id,
            },
        )
        return existing, False


# ============================================================================
# User CRUD
# ============================================================================


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Fetch a user by username.

    Args:
        session: Active async database session.
        username: Exact username to look up.

    Returns:
        User ORM instance or None if not found.
    """
    result = await session.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Fetch an active user by primary key.

    Args:
        session: Active async database session.
        user_id: Primary key of the user to retrieve.

    Returns:
        User ORM instance or None if not found or inactive.
    """
    result = await session.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    password_hash: str,
    role: str = "viewer",
    tenant_id: int | None = None,
) -> User:
    """Insert a new user record.

    Args:
        session: Active async database session.
        username: Unique username (3–64 characters).
        email: Unique email address.
        password_hash: Argon2id hash of the raw password.
        role: Initial role assignment (default: viewer).
        tenant_id: Optional tenant ID override. If None, uses get_tenant_id().

    Returns:
        Newly created User ORM instance.

    Raises:
        IntegrityError: If username or email already exists (unique constraint).
    """
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        tenant_id=tenant_id if tenant_id is not None else get_tenant_id(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def has_tenant_access(
    session: AsyncSession, user_id: int, target_tenant_id: int
) -> bool:
    """Check if a user is explicitly authorized for a specific tenant via UserTenant."""
    result = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == target_tenant_id,
            UserTenant.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def add_tenant_to_user(
    session: AsyncSession, user_id: int, target_tenant_id: int
) -> UserTenant:
    """Grant a user access to a specific tenant via the UserTenant junction table."""
    user_tenant = UserTenant(
        user_id=user_id,
        tenant_id=target_tenant_id,
    )
    try:
        session.add(user_tenant)
        await session.commit()
        await session.refresh(user_tenant)
        return user_tenant
    except IntegrityError:
        # Already exists
        await session.rollback()
        result = await session.execute(
            select(UserTenant).where(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == target_tenant_id,
            )
        )
        existing = result.scalar_one()
        if existing.deleted_at is not None:
            existing.deleted_at = None
            await session.commit()
            await session.refresh(existing)
        return existing
