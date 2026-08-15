"""Pytest configuration for dashboard tests.

Mocks Streamlit at collection time so panel tests never need the real
framework installed.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = MagicMock()
