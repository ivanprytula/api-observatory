from typing import TypedDict

from services.ingestor.api_schemas.records import RecordClassification


class AgentState(TypedDict):
    record_id: int
    record: dict
    rag_context: str
    classification: RecordClassification | None
    analysis_depth: str  # "standard" | "deep"
    result: str
    error: str | None
