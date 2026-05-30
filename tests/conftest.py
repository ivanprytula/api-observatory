"""Top-level pytest configuration.

Shared fixtures are defined in `tests/fixtures_shared.py` and re-exported here
for tests collected under the top-level `tests/` tree.
"""

from tests import fixtures_shared as shared


globals().update({name: getattr(shared, name) for name in shared.__all__})
__all__ = shared.__all__
