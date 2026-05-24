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

# Compile without checkpointer so the module can be imported without a live Redis
# connection (important for tests and cold imports). Production endpoints should
# call compile_with_checkpointer() once at startup and use the returned agents.
record_enrichment_agent = _graph.compile()
record_enrichment_agent_hitl = _graph.compile(interrupt_before=["publish"])


def compile_with_checkpointer():
    """Return (agent, agent_hitl) compiled with the Redis checkpointer."""
    saver = get_checkpointer()
    return (
        _graph.compile(checkpointer=saver),
        _graph.compile(checkpointer=saver, interrupt_before=["publish"]),
    )
