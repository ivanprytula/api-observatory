from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration
from langgraph.checkpoint.memory import MemorySaver

from services.ingestor.api_schemas.observations import ObservationClassification


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_search_observation_documents():
    with patch(
        "services.ingestor.agent.nodes.search_observation_documents",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = {"results": [{"text": "mocked context"}]}
        yield mock


@pytest.fixture
def mock_openai():
    with patch("services.ingestor.agent.nodes.AsyncOpenAI") as mock:
        client_mock = MagicMock()
        mock.return_value = client_mock

        # mock parse (for classify_node)
        parse_mock = AsyncMock()
        mock_response = MagicMock()
        mock_parsed = ObservationClassification(
            category="test", priority=2, summary="test", sentiment="neutral"
        )
        mock_response.choices = [MagicMock(message=MagicMock(parsed=mock_parsed))]
        parse_mock.return_value = mock_response
        client_mock.beta.chat.completions.parse = parse_mock

        # mock create (for deep_analyze_node)
        create_mock = AsyncMock()
        mock_create_response = MagicMock()
        mock_create_response.choices = [
            MagicMock(message=MagicMock(content="deep analysis result"))
        ]
        create_mock.return_value = mock_create_response
        client_mock.chat.completions.create = create_mock

        yield client_mock


@pytest.fixture
def mock_publish_observation_created():
    with patch(
        "services.ingestor.agent.nodes.publish_observation_created",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_insert_scraped_doc():
    with patch(
        "services.ingestor.agent.nodes.insert_scraped_doc", new_callable=AsyncMock
    ) as mock:
        yield mock


from services.ingestor.agent.graph import (  # noqa: E402
    build_graph,
    observation_enrichment_agent,
)


# Mock AsyncRedisSaver
@pytest.fixture(autouse=True)
def mock_redis_saver():
    with patch("services.ingestor.agent.graph.AsyncRedisSaver") as mock:
        saver_instance = AsyncMock()
        mock.return_value = saver_instance
        yield mock


async def test_low_priority_skips_deep_analyze(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    # Setup mock to return priority 2
    mock_parsed = ObservationClassification(
        category="test", priority=2, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    config = {"configurable": {"thread_id": "1"}}
    final_state = await observation_enrichment_agent.ainvoke(
        initial_state, config=config
    )

    assert final_state["analysis_depth"] == "standard"
    assert (
        mock_openai.chat.completions.create.call_count == 0
    )  # deep_analyze not called


async def test_high_priority_routes_to_deep_analyze(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    # Setup mock to return priority 5
    mock_parsed = ObservationClassification(
        category="test", priority=5, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    config = {"configurable": {"thread_id": "2"}}
    final_state = await observation_enrichment_agent.ainvoke(
        initial_state, config=config
    )

    assert final_state["analysis_depth"] == "deep"
    assert mock_openai.chat.completions.create.call_count == 1


async def test_unknown_category_routes_to_deep_analyze(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    mock_parsed = ObservationClassification(
        category="unknown", priority=1, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    config = {"configurable": {"thread_id": "3"}}
    final_state = await observation_enrichment_agent.ainvoke(
        initial_state, config=config
    )

    assert final_state["analysis_depth"] == "deep"
    assert mock_openai.chat.completions.create.call_count == 1


async def test_hitl_pauses_before_publish(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    mock_parsed = ObservationClassification(
        category="test", priority=2, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    # Use in-memory checkpointer so HITL state can be retrieved after pause
    memory_saver = MemorySaver()
    hitl_agent = build_graph().compile(
        checkpointer=memory_saver, interrupt_before=["publish"]
    )

    config = {"configurable": {"thread_id": "4"}}
    await hitl_agent.ainvoke(initial_state, config=config)

    # Check if we didn't call publish yet
    assert mock_publish_observation_created.call_count == 0
    assert mock_insert_scraped_doc.call_count == 0

    # State should indicate we are next going to publish
    state = await hitl_agent.aget_state(config)
    assert "publish" in state.next


async def test_hitl_resume_approves(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    # Setup mock to return priority 2
    mock_parsed = ObservationClassification(
        category="test", priority=2, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    memory_saver = MemorySaver()
    hitl_agent = build_graph().compile(
        checkpointer=memory_saver, interrupt_before=["publish"]
    )

    config = {"configurable": {"thread_id": "5"}}
    await hitl_agent.ainvoke(initial_state, config=config)

    # Resume with approval
    final_state = await hitl_agent.ainvoke(None, config=config)

    # Verify that the publish node successfully executed on resume
    assert mock_publish_observation_created.call_count == 1
    assert mock_insert_scraped_doc.call_count == 1
    assert final_state["analysis_depth"] == "standard"


async def test_hitl_resume_rejects(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    # Setup mock to return priority 2
    mock_parsed = ObservationClassification(
        category="test", priority=2, summary="test", sentiment="neutral"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[
        0
    ].message.parsed = mock_parsed

    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }

    memory_saver = MemorySaver()
    hitl_agent = build_graph().compile(
        checkpointer=memory_saver, interrupt_before=["publish"]
    )

    config = {"configurable": {"thread_id": "6"}}
    await hitl_agent.ainvoke(initial_state, config=config)

    # Resume with rejection
    await hitl_agent.aupdate_state(config, {"error": "rejected_by_human"})

    # State values after reject:
    state = await hitl_agent.aget_state(config)
    assert state.values.get("error") == "rejected_by_human"

    # Verify that the publish node was skipped
    assert mock_publish_observation_created.call_count == 0
    assert mock_insert_scraped_doc.call_count == 0


async def test_stream_emits_node_events(
    mock_search_observation_documents,
    mock_openai,
    mock_publish_observation_created,
    mock_insert_scraped_doc,
):
    initial_state = {
        "observation_id": 1,
        "observation": {"source": "test", "raw_data": {}},
    }
    config = {"configurable": {"thread_id": "7"}}

    events = []
    async for event in observation_enrichment_agent.astream(
        initial_state, config=config, stream_mode="updates"
    ):
        events.append(event)

    # We should have updates from nodes: fetch_context, classify, format_result, publish
    assert len(events) > 0
    # The last node is publish
    assert "publish" in events[-1]
