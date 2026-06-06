"""Seed the database with test records for load testing.

Creates N records via the batch API in chunks of 1 000.
No direct DB access — works against the running app only.

Usage:
    uv run python scripts/testing/seed_data.py            # 10 000 records (default)
    uv run python scripts/testing/seed_data.py 50000      # custom count
    BASE_URL=http://localhost:8000 uv run python scripts/testing/seed_data.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

import httpx


BASE_URL: str = "http://localhost:8000"
BATCH_SIZE: int = 1_000  # /batch endpoint hard limit
DEFAULT_TOTAL: int = 10_000
SOURCES: tuple[str, ...] = (
    "sensor-alpha",
    "sensor-beta",
    "api-ingest",
    "etl-pipeline",
    "webhook-receiver",
)


def _make_records(count: int, offset: int) -> list[dict]:
    """Build a list of record payloads starting at *offset*."""
    base_ts = datetime(2024, 1, 1, tzinfo=UTC)
    records = []
    for i in range(count):
        idx = offset + i
        ts = base_ts + timedelta(seconds=idx)
        records.append(
            {
                "source": SOURCES[idx % len(SOURCES)],
                "timestamp": ts.isoformat(),
                "data": {"value": idx, "batch": idx // BATCH_SIZE},
                "tags": [f"tag-{idx % 10}", f"bucket-{idx % 5}"],
            }
        )
    return records


async def seed(total: int = DEFAULT_TOTAL, base_url: str = BASE_URL) -> None:
    """Seed *total* records into the running app at *base_url*."""
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Verify the app is reachable before doing any work.
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
        except (httpx.HTTPError, httpx.ConnectError) as exc:
            print(f"[error] App not reachable at {base_url}: {exc}", file=sys.stderr)
            sys.exit(1)

        created = 0
        batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_num in range(batches):
            count = min(BATCH_SIZE, total - created)
            records = _make_records(count, offset=created)

            resp = await client.post(
                "/api/v1/records/batch",
                json={"records": records},
            )
            resp.raise_for_status()

            created += count
            pct = created / total * 100
            print(
                f"[seed] {created:>6}/{total}  ({pct:.0f}%)  batch {batch_num + 1}/{batches}"
            )

    print(f"[seed] Done. {created} records inserted.")


if __name__ == "__main__":
    total = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TOTAL
    url = sys.argv[2] if len(sys.argv) > 2 else BASE_URL
    asyncio.run(seed(total, url))
