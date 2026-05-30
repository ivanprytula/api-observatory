"""Top-level pytest configuration.

Shared fixtures are defined in `tests/fixtures_shared.py` and re-exported here
for tests collected under the top-level `tests/` tree.
"""

from tests.fixtures_shared import *  # noqa: F401,F403
