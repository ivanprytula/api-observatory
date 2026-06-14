import logging

from langgraph.checkpoint.memory import MemorySaver
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


def get_checkpointer() -> MemorySaver | object:
    # Lazy import to avoid crash when langgraph version doesn't have cache module
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver

        return AsyncRedisSaver(settings.cache_url)  # ty: ignore[no-any-return]
    except ImportError as e:
        logger.warning(
            "cache_checkpointer_unavailable",
            extra={"error": str(e), "fallback": "memory"},
        )
        return MemorySaver()


_graph = build_graph()

# Default checkpointer for unit tests and local runs without Cache is MemorySaver.
# This ensures that checkpoints work out-of-the-box in all test suites and modules.
memory_saver = MemorySaver()
observation_enrichment_agent = _graph.compile(checkpointer=memory_saver)
observation_enrichment_agent_hitl = _graph.compile(
    checkpointer=memory_saver, interrupt_before=["publish"]
)


_cache_agent = None
_cache_agent_hitl = None


def get_agent():
    """Get the compiled enrichment agent, using the Cache checkpointer if enabled."""
    global _cache_agent
    if _cache_agent is None:
        if settings.cache_enabled:
            try:
                saver = get_checkpointer()
                _cache_agent = _graph.compile(checkpointer=saver)
            except Exception as e:
                logger.warning(
                    "cache_checkpointer_failed",
                    extra={"error": str(e), "fallback": "memory"},
                )
                _cache_agent = observation_enrichment_agent
        else:
            _cache_agent = observation_enrichment_agent
    return _cache_agent


def get_agent_hitl():
    """Get the compiled HITL enrichment agent, using the Cache checkpointer if enabled."""
    global _cache_agent_hitl
    if _cache_agent_hitl is None:
        if settings.cache_enabled:
            try:
                saver = get_checkpointer()
                _cache_agent_hitl = _graph.compile(
                    checkpointer=saver, interrupt_before=["publish"]
                )
            except Exception as e:
                logger.warning(
                    "cache_checkpointer_failed",
                    extra={"error": str(e), "fallback": "memory"},
                )
                _cache_agent_hitl = observation_enrichment_agent_hitl
        else:
            _cache_agent_hitl = observation_enrichment_agent_hitl
    return _cache_agent_hitl


def compile_with_checkpointer():
    """Return (agent, agent_hitl) compiled with the Cache checkpointer."""
    saver = get_checkpointer()
    return (
        _graph.compile(checkpointer=saver),
        _graph.compile(checkpointer=saver, interrupt_before=["publish"]),
    )
