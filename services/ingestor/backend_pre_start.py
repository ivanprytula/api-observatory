"""Pre-start helper: wait for database readiness.

Called from ``scripts/prestart.sh`` before the app starts so that
``uv run`` and other direct entrypoints survive DB cold-starts without
depending solely on Compose healthchecks.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_fixed

from services.ingestor.core.database import engine


@retry(stop=stop_after_attempt(60), wait=wait_fixed(1))
async def wait_for_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


if __name__ == "__main__":
    asyncio.run(wait_for_db())
