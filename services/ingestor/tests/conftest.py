"""Service-tree local pytest configuration.

Shared fixtures are discovered from this test tree and the repository root
`conftest.py` during normal pytest collection.
"""

from tests import fixtures_shared as shared


globals().update({name: getattr(shared, name) for name in shared.__all__})

__all__ = shared.__all__
