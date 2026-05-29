from typing import TypedDict

from services.ingestor.api_schemas.observations import ObservationClassification


class AgentState(TypedDict):
    observation_id: int
    observation: dict
    rag_context: str
    classification: ObservationClassification | None
    analysis_depth: str  # "standard" | "deep"
    result: str
    error: str | None
