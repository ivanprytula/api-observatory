"""Bridge fixtures for the services/ingestor/tests subtree.

These tests are outside the top-level tests/ directory, so they don't inherit
fixtures from tests/conftest.py automatically. Re-exporting keeps a single
fixture source of truth without plugin double-registration.
"""

from tests.conftest import *  # noqa: F403
from tests.conftest import _auto_provision_postgres  # noqa: F401
