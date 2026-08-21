#!/usr/bin/env python3
"""Seed the initial admin and reserved global superadmin accounts.

Idempotent: safe to re-run. Delegates to the same bootstrap helpers the
application used to call on startup, so account creation stays consistent with
public registration (argon2 hashing, tenant provisioning, Casbin role
assignment).

This is intentionally a standalone step, decoupled from the application
lifespan, so that:
  - Migrations (``alembic upgrade head``) can run as a dedicated step after the
    services start, without the app assuming any schema exists at boot.
  - Test suites can apply only schema migrations and keep a clean DB (no seed
    users), calling the bootstrap helpers directly only where an admin is
    actually needed.

No-op (exit 0) when the relevant credentials are not configured in the
environment. Exits non-zero if the schema is missing (e.g. migrations have not
been applied yet) so an orchestrator can gate startup on successful seeding.

Usage (matches the `just db-migrate` container invocation):
    docker compose run --rm --no-deps ingestor python scripts/seed_admin.py

Or locally:
    uv run python scripts/seed_admin.py
"""

from __future__ import annotations

import asyncio
import logging

from services.ingestor.config import settings
from services.ingestor.core.bootstrap import bootstrap_initial_admin, ensure_superadmin
from services.ingestor.database import AsyncSessionLocal, engine


logger = logging.getLogger("seed_admin")


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # Run in strict order: ensure_superadmin must commit BEFORE
        # bootstrap_initial_admin so the superadmin gets id=1.
        # If superadmin creation was configured but failed, skip the admin
        # to avoid the admin accidentally taking id=1.
        superadmin = await ensure_superadmin(session)
        if superadmin is None and settings.superadmin_password:
            logger.error(
                "seed_superadmin_failed",
                extra={"reason": "ensure_superadmin_did_not_succeed"},
            )
        await bootstrap_initial_admin(session)
    # Release pooled connections within the same event loop so the process exits
    # cleanly (no cross-loop "Task attached to a different loop" error).
    await engine.dispose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not settings.init_admin_username and not settings.superadmin_password:
        logger.info(
            "seed_admin_skipped",
            extra={"reason": "no_credentials_configured"},
        )
        return 0

    try:
        asyncio.run(seed())
    except Exception as exc:
        logger.error("seed_admin_failed", extra={"error": str(exc)})
        return 1

    logger.info("seed_admin_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
