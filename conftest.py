"""Root pytest configuration.

Pytest auto-loads each tree's local conftest modules.

Post-MVP deferrals:
- Scraping functionality/tests
- MongoDB functionality/tests
"""

# Defer non-MVP slices at collection time so they do not block unit/integration/e2e
# runs for the active MVP scope.
collect_ignore_glob = [
    "services/ingestor/tests/integration/scrapers/test_*.py",
    "tests/e2e/scrapers/test_*.py",
    "services/ingestor/tests/unit/storage/test_mongo_operations.py",
    # Advanced PostgreSQL features (post-MVP optimization)
    "services/ingestor/tests/integration/observations/test_materialized_views_and_partitioning.py",
    "services/ingestor/tests/integration/observations/test_cte_window_functions.py",
    # JWT + RBAC advanced auth (post-MVP auth hardening)
    "services/ingestor/tests/integration/observations/test_v2_jwt_rbac.py",
    # Background processing async tasks (post-MVP feature)
    "services/ingestor/tests/integration/test_background_processing_api.py",
    # Pub/Sub events (post-MVP streaming feature)
    "services/ingestor/tests/integration/test_pubsub.py",
    # Advanced schema features (post-MVP infrastructure)
    "tests/integration/schema/test_schema_integrity.py",
]
