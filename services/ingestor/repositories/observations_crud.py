"""Observation and event CRUD operations."""

from datetime import datetime

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import (
    ObservationRequest,
    UpdateObservationRequest,
)
from services.ingestor.core.tenant import get_tenant_id, get_user_role
from services.ingestor.models import (
    Observation,
    ProcessedEvent,
    Tenant,
    User,
    UserTenant,
    _utcnow,
)


async def claim_pending_events(
    session: AsyncSession, batch_size: int
) -> list[ProcessedEvent]:
    """Atomically claim a batch of pending events using SELECT FOR UPDATE SKIP LOCKED."""
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


async def create_observation(
    session: AsyncSession, request: ObservationRequest
) -> Observation:
    observation = Observation(
        source=request.source,
        timestamp=request.timestamp,
        raw_data=request.data,
        tags=request.tags,
        tenant_id=get_tenant_id(),
    )
    session.add(observation)
    await session.commit()
    await session.refresh(observation)
    return observation


async def create_observations_batch(
    session: AsyncSession, requests: list[ObservationRequest]
) -> list[Observation]:
    """Bulk-insert with RETURNING — single round-trip to database."""
    if not requests:
        return []

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

    stmt = insert(Observation).values(insert_data).returning(Observation)
    result = await session.execute(stmt)
    observations = result.scalars().all()

    await session.commit()
    return list(observations)


async def create_observations_batch_naive(
    session: AsyncSession, requests: list[ObservationRequest]
) -> list[Observation]:
    """Naive bulk-insert: N individual INSERTs + N individual REFRESH calls."""
    if not requests:
        return []

    observations = [
        Observation(
            source=r.source,
            timestamp=r.timestamp,
            raw_data=r.data,
            tags=r.tags,
            tenant_id=get_tenant_id(),
        )
        for r in requests
    ]
    session.add_all(observations)
    await session.commit()
    for observation in observations:
        await session.refresh(observation)
    return list(observations)


def _apply_tenant_filter(query) -> tuple:
    """Apply tenant isolation filter with admin bypass."""
    tenant_id = get_tenant_id()
    user_role = get_user_role()

    if user_role == "admin":
        return query, False

    if tenant_id is not None:
        return query.where(
            (Observation.tenant_id == tenant_id) | (Observation.tenant_id.is_(None))
        ), True

    return query.where(Observation.tenant_id.is_(None)), True


async def get_observations(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    source: str | None = None,
) -> tuple[list[Observation], int]:
    count_q = (
        select(func.count())
        .select_from(Observation)
        .where(Observation.deleted_at.is_(None))
    )
    data_q = (
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .order_by(Observation.id)
        .offset(skip)
        .limit(limit)
    )
    if source:
        count_q = count_q.where(Observation.source == source)
        data_q = data_q.where(Observation.source == source)

    count_q, _ = _apply_tenant_filter(count_q)
    data_q, _ = _apply_tenant_filter(data_q)

    total = (await session.execute(count_q)).scalar_one()
    observations = list((await session.execute(data_q)).scalars().all())
    return observations, total


async def get_observations_by_date_range(
    session: AsyncSession,
    start: datetime,
    end: datetime,
    source: str | None = None,
) -> list[Observation]:
    """Fetch observations within a timestamp range using the ix_observations_timestamp index."""
    query = (
        select(Observation)
        .where(
            Observation.deleted_at.is_(None),
            Observation.timestamp >= start,
            Observation.timestamp < end,
        )
        .order_by(Observation.timestamp.desc(), Observation.id.desc())
    )
    if source:
        query = query.where(Observation.source == source)

    query, _ = _apply_tenant_filter(query)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_observation(
    session: AsyncSession, observation_id: int
) -> Observation | None:
    result = await session.execute(
        select(Observation).where(
            Observation.id == observation_id, Observation.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def mark_processed(
    session: AsyncSession, observation_id: int
) -> Observation | None:
    """Mark an observation as processed and set processed_at timestamp."""
    observation = await session.get(Observation, observation_id)
    if observation is None:
        return None
    observation.processed = True
    if observation.processed_at is None:
        observation.processed_at = _utcnow()
    await session.commit()
    await session.refresh(observation)
    return observation


async def update_observation(
    session: AsyncSession, observation_id: int, request: UpdateObservationRequest
) -> Observation | None:
    """Update an observation with provided fields (partial update)."""
    observation = await session.get(Observation, observation_id)
    if observation is None:
        return None

    if request.source is not None:
        observation.source = request.source
    if request.timestamp is not None:
        observation.timestamp = request.timestamp
    if request.data is not None:
        observation.raw_data = request.data
    if request.tags is not None:
        observation.tags = request.tags

    await session.commit()
    await session.refresh(observation)
    return observation


async def delete_observation(
    session: AsyncSession, observation_id: int
) -> Observation | None:
    observation = await session.get(Observation, observation_id)
    if observation is None:
        return None
    await session.delete(observation)
    await session.commit()
    return observation


async def soft_delete_observation(
    session: AsyncSession, observation_id: int
) -> Observation | None:
    observation = await session.get(Observation, observation_id)
    if observation is None or observation.deleted_at is not None:
        return None
    observation.deleted_at = _utcnow()
    await session.commit()
    await session.refresh(observation)
    return observation


async def upsert_observation(
    session: AsyncSession,
    request: ObservationRequest,
) -> tuple[Observation, bool]:
    """Insert a observation or return the existing one on (source, timestamp) conflict."""
    import logging

    logger = logging.getLogger(__name__)

    observation = Observation(
        source=request.source,
        timestamp=request.timestamp,
        raw_data=request.data,
        tags=request.tags,
        tenant_id=get_tenant_id(),
    )
    try:
        session.add(observation)
        await session.flush()
        await session.commit()
        await session.refresh(observation)
        logger.info(
            "upsert_created",
            extra={"source": request.source, "timestamp": str(request.timestamp)},
        )
        return observation, True
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(Observation).where(
                Observation.source == request.source,
                Observation.timestamp == request.timestamp,
                Observation.deleted_at.is_(None),
            )
        )
        existing = result.scalar_one_or_none()
        assert existing is not None, (
            f"Unique constraint violation on (source, timestamp) but no active "
            f"observation found for source={request.source}, timestamp={request.timestamp}. "
            f"This can only occur if the observation was soft-deleted between INSERT and "
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
    """Fetch a user by username."""
    result = await session.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def update_user_role(
    session: AsyncSession,
    username: str,
    role: str,
) -> User | None:
    """Assign a new role to a user."""
    user = await get_user_by_username(session, username)
    if user is None:
        return None
    user.role = role
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Fetch an active user by primary key."""
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
    """Insert a new user observation."""
    if tenant_id is None:
        tenant = Tenant(name=f"{username}-personal")
        session.add(tenant)
        await session.flush()
        tenant_id = tenant.id

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        tenant_id=tenant_id,
    )
    session.add(user)
    await session.flush()

    user_tenant = UserTenant(user_id=user.id, tenant_id=tenant_id)
    session.add(user_tenant)

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
