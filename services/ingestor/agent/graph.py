import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph

from services.ingestor.config import settings

from .nodes import (
    classify_node,
    deep_analyze_node,
    fetch_context_node,
    format_result_node,
    publish_node,
)
from .state import AgentState


logger = logging.getLogger(__name__)


def _should_deep_analyze(state: AgentState) -> str:
    c = state.get("classification")
    if c is None or c.priority >= 4 or c.category == "unknown":
        return "deep_analyze"
    return "format_result"


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("fetch_context", fetch_context_node)
    g.add_node("classify", classify_node)
    g.add_node("deep_analyze", deep_analyze_node)
    g.add_node("format_result", format_result_node)
    g.add_node("publish", publish_node)

    g.add_edge(START, "fetch_context")
    g.add_edge("fetch_context", "classify")
    g.add_conditional_edges("classify", _should_deep_analyze)
    g.add_edge("deep_analyze", "publish")
    g.add_edge("format_result", "publish")
    g.add_edge("publish", END)
    return g  # ty: ignore[invalid-return-type]


def get_checkpointer() -> AsyncRedisSaver:
    # AsyncRedisSaver v0.4.x accepts a Redis URL string as first positional argument
    return AsyncRedisSaver(settings.redis_url)


_graph = build_graph()

# Default checkpointer for unit tests and local runs without Redis is MemorySaver.
# This ensures that checkpoints work out-of-the-box in all test suites and modules.
memory_saver = MemorySaver()
record_enrichment_agent = _graph.compile(checkpointer=memory_saver)
record_enrichment_agent_hitl = _graph.compile(
    checkpointer=memory_saver, interrupt_before=["publish"]
)


_redis_agent = None
_redis_agent_hitl = None


def get_agent():
    """Get the compiled enrichment agent, using the Redis checkpointer if enabled."""
    global _redis_agent
    if _redis_agent is None:
        if settings.redis_enabled:
            try:
                saver = get_checkpointer()
                _redis_agent = _graph.compile(checkpointer=saver)
            except Exception as e:
                logger.warning(
                    "redis_checkpointer_failed",
                    extra={"error": str(e), "fallback": "memory"},
                )
                _redis_agent = record_enrichment_agent
        else:
            _redis_agent = record_enrichment_agent
    return _redis_agent


def get_agent_hitl():
    """Get the compiled HITL enrichment agent, using the Redis checkpointer if enabled."""
    global _redis_agent_hitl
    if _redis_agent_hitl is None:
        if settings.redis_enabled:
            try:
                saver = get_checkpointer()
                _redis_agent_hitl = _graph.compile(
                    checkpointer=saver, interrupt_before=["publish"]
                )
            except Exception as e:
                logger.warning(
                    "redis_checkpointer_failed",
                    extra={"error": str(e), "fallback": "memory"},
                )
                _redis_agent_hitl = record_enrichment_agent_hitl
        else:
            _redis_agent_hitl = record_enrichment_agent_hitl
    return _redis_agent_hitl


def compile_with_checkpointer():
    """Return (agent, agent_hitl) compiled with the Redis checkpointer."""
    saver = get_checkpointer()
    return (
        _graph.compile(checkpointer=saver),
        _graph.compile(checkpointer=saver, interrupt_before=["publish"]),
    )
