"""Streamlit dashboard entry point.

This file now delegates to the modular framework-agnostic implementation.
The core logic lives in services/dashboard/core/ and ui/streamlit/.
"""

from services.dashboard.ui.streamlit.app import main


main()
