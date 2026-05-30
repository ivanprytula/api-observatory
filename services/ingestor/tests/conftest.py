"""Service-tree local pytest configuration.

Shared fixtures are discovered from this test tree and the repository root
`conftest.py` during normal pytest collection.
"""

from tests.fixtures_shared import *  # noqa: F401,F403
from tests.fixtures_shared import _auto_provision_postgres  # noqa: F401
