import json
import logging
from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from services.ingestor.agent.state import AgentState
from services.ingestor.api_schemas.records import RecordClassification
from services.ingestor.config import settings
from services.ingestor.events import publish_record_created
from services.ingestor.vector_search import search_record_documents


try:
    from services.ingestor.storage.mongo import insert_scraped_doc
except ImportError:

    async def insert_scraped_doc(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("Mongo storage module is not available")


logger = logging.getLogger(__name__)


async def fetch_context_node(state: AgentState) -> dict[str, Any]:
    source = state["record"].get("source")
    raw_data = state["record"].get("raw_data", {})
    query_text = f"Source: {source}, Data: {json.dumps(raw_data)}"
    try:
        context_results = await search_record_documents(query=query_text, top_k=3)
        context_docs = [r.get("text", "") for r in context_results.get("results", [])]
        context_text = "\n---\n".join(context_docs)
    except Exception as exc:
        logger.warning("fetch_context_failed", extra={"error": str(exc)})
        context_text = "No additional context available."

    return {"rag_context": context_text}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def classify_node(state: AgentState) -> dict[str, Any]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    system_prompt = (
        "You are a senior data analyst. Analyze the following record. "
        "Return the analysis as a structured JSON object matching the requested schema."
    )
    user_prompt = (
        f"Context from similar records:\n{state.get('rag_context', '')}\n\n"
        f"Record to analyze:\n"
        f"Source: {state['record'].get('source')}\n"
        f"Data: {json.dumps(state['record'].get('raw_data', {}))}\n"
    )

    try:
        completion = await client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=RecordClassification,
        )
        parsed = completion.choices[0].message.parsed
        return {"classification": parsed}
    except Exception as exc:
        logger.error("llm_classify_failed", extra={"error": str(exc)})
        return {"error": str(exc)}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def deep_analyze_node(state: AgentState) -> dict[str, Any]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    c = state.get("classification")
    classification_str = c.model_dump_json() if c else "None"

    system_prompt = (
        "Perform a deep, comprehensive analysis of the record, considering"
        " the classification and context."
    )
    user_prompt = (
        f"Context:\n{state.get('rag_context', '')}\n\n"
        f"Classification:\n{classification_str}\n\n"
        f"Record:\n{json.dumps(state['record'])}\n"
    )

    try:
        completion = await client.chat.completions.create(
            model=settings.openai_model_deep,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        result = completion.choices[0].message.content
        return {"analysis_depth": "deep", "result": result or ""}
    except Exception as exc:
        logger.error("llm_deep_analyze_failed", extra={"error": str(exc)})
        return {"error": str(exc)}


async def format_result_node(state: AgentState) -> dict[str, Any]:
    c = state.get("classification")
    category = c.category if c else "none"
    return {
        "analysis_depth": "standard",
        "result": f"Standard classification: {category}",
    }


async def publish_node(state: AgentState) -> dict[str, Any]:
    record_id = state.get("record_id")
    result = state.get("result", "")

    await publish_record_created(record_id, {"analysis_result": result})

    try:
        await insert_scraped_doc(
            source="agent",
            url=f"agent://record/{record_id}",
            title=f"Analysis for {record_id}",
            content=result,
        )
    except Exception as exc:
        logger.warning("insert_scraped_doc_failed", extra={"error": str(exc)})

    return {}
