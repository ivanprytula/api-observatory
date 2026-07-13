"""Unit tests for services/mcp/server.py's @mcp.tool() functions.

Each tool is called directly (they remain plain async callables under the
decorator) with its `ingestor_client` counterpart patched — this file checks
argument forwarding and tool registration/documentation, not HTTP behavior
(that's test_ingestor_client.py's job).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.mcp import server


TOOL_NAMES = [
    "list_sources",
    "get_source",
    "get_source_summary",
    "probe_source_health",
    "list_scorecards",
    "get_scorecard",
    "list_contract_snapshots",
    "list_drift_events",
    "get_compatibility_report",
    "get_agent_run",
    "resume_agent_run",
]


async def test_all_expected_tools_are_registered_with_descriptions() -> None:
    tools = await server.mcp.list_tools()
    registered = {tool.name: tool for tool in tools}

    for name in TOOL_NAMES:
        assert name in registered, f"tool {name!r} is not registered"
        assert registered[name].description, f"tool {name!r} has no description"


async def test_get_source_forwards_argument_and_returns_client_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_get_source = AsyncMock(return_value={"id": 42, "name": "demo"})
    monkeypatch.setattr(server.ingestor_client, "get_source", mock_get_source)

    result = await server.get_source(42)

    assert result == {"id": 42, "name": "demo"}
    mock_get_source.assert_awaited_once_with(42)


async def test_list_sources_forwards_all_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_list_sources = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(server.ingestor_client, "list_sources", mock_list_sources)

    result = await server.list_sources(is_active=True, offset=5, limit=50)

    assert result == {"items": []}
    mock_list_sources.assert_awaited_once_with(is_active=True, offset=5, limit=50)


async def test_resume_agent_run_forwards_approve_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_resume = AsyncMock(return_value={"id": 7, "status": "approved"})
    monkeypatch.setattr(server.ingestor_client, "resume_agent_run", mock_resume)

    result = await server.resume_agent_run(7, approve=True)

    assert result == {"id": 7, "status": "approved"}
    mock_resume.assert_awaited_once_with(7, approve=True)
