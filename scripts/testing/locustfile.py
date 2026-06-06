"""Locust load test: cursor-based vs offset pagination comparison.

Two user classes represent two pagination strategies running concurrently:

  OffsetPaginationUser  — GET /api/v1/records?skip=X&limit=50
                          Mixes shallow and deep pages to expose the
                          O(skip) cost growth of offset pagination.

  CursorPaginationUser  — GET /api/v2/records/cursor?cursor=...&limit=50
                          Follows next_cursor, demonstrating O(1) cost
                          at any depth.

Usage:
    # Headless (terminal stats only)
    uv run locust -f scripts/testing/locustfile.py \\
        --headless -u 20 -r 5 --run-time 60s \\
        --host http://localhost:8000

    # Web UI at http://localhost:8089 (interactive control)
    uv run locust -f scripts/testing/locustfile.py --host http://localhost:8000

    # Run only one strategy
    uv run locust -f scripts/testing/locustfile.py --headless -u 20 -r 5 \\
        --run-time 60s --host http://localhost:8000 OffsetPaginationUser

    # Compare strategies side-by-side — each with 10 users, 60s run
    uv run locust -f scripts/testing/locustfile.py --headless \\
        -u 20 -r 5 --run-time 60s --host http://localhost:8000

Prerequisites:
    uv add --dev locust
    uv run python scripts/testing/seed_data.py 10000
    docker compose up -d app   # app must be running
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task


LIMIT: int = 50
RNG = random.SystemRandom()

# Shallow offsets: small index scan — fast
SHALLOW_OFFSETS: list[int] = [0, 50, 100, 200]

# Deep offsets: full table scan — cost grows with skip
DEEP_OFFSETS: list[int] = [1_000, 2_500, 5_000, 7_500, 9_000]


class OffsetPaginationUser(HttpUser):
    """Simulates a client using classic skip/limit (offset) pagination.

    Task weighting: 3× shallow, 1× deep — mimics a realistic read pattern
    where most clients read recent data but some occasionally jump deep.
    """

    wait_time = between(0.1, 0.5)
    weight = 1  # equal weight with CursorPaginationUser

    @task(3)
    def shallow_page(self) -> None:
        """Request a shallow page (first ~200 rows — low I/O cost)."""
        skip = RNG.choice(SHALLOW_OFFSETS)
        self.client.get(
            f"/api/v1/records?skip={skip}&limit={LIMIT}",
            name="/api/v1/records [shallow]",
        )

    @task(1)
    def deep_page(self) -> None:
        """Request a deep page (skip=1000–9000 — triggers full table scan)."""
        skip = RNG.choice(DEEP_OFFSETS)
        self.client.get(
            f"/api/v1/records?skip={skip}&limit={LIMIT}",
            name="/api/v1/records [deep]",
        )


class CursorPaginationUser(HttpUser):
    """Simulates a client using cursor-based pagination.

    Each virtual user maintains its own cursor chain state.
    When the chain is exhausted (has_more=False) or a page depth threshold
    is passed, the chain resets from the first page.

    The key observable: latency stays flat regardless of depth.
    """

    wait_time = between(0.1, 0.5)
    weight = 1  # equal weight with OffsetPaginationUser

    def on_start(self) -> None:
        """Initialise cursor state for this VU."""
        self._cursor: str | None = None
        self._page: int = 0

    @task
    def next_cursor_page(self) -> None:
        """Fetch the next page; advance cursor or reset if chain exhausted."""
        params = f"limit={LIMIT}"
        if self._cursor:
            params += f"&cursor={self._cursor}"

        # Label deep vs shallow so Locust separates them in the stats table.
        if self._page == 0:
            name = "/api/v2/records/cursor [first-page]"
        elif self._page < 10:
            name = "/api/v2/records/cursor [shallow]"
        else:
            name = "/api/v2/records/cursor [deep]"

        with self.client.get(
            f"/api/v2/records/cursor?{params}",
            name=name,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                self._reset()
                return

            body = resp.json()
            resp.success()

            if body.get("has_more") and body.get("next_cursor"):
                self._cursor = body["next_cursor"]
                self._page += 1
            else:
                # Chain exhausted — start over from the first page.
                self._reset()

    def _reset(self) -> None:
        """Reset cursor chain to the beginning."""
        self._cursor = None
        self._page = 0
