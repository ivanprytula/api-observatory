import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.agent.graph import (
    get_agent,
    get_agent_hitl,
)
from services.ingestor.api_schemas.records import AgentRunResponse
from services.ingestor.database import get_db
from services.ingestor.repositories.records import get_record as get_record_op


logger = logging.getLogger(__name__)

router = APIRouter()


class ResumeRequest(BaseModel):
    approve: bool


@router.post("/enrich/{record_id}", response_model=AgentRunResponse)
async def enrich_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await get_record_op(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    run_id = str(uuid.uuid4())
    initial_state = {
        "record_id": record_id,
        "record": {
            "source": record.source,
            "raw_data": record.raw_data,
            "tags": record.tags,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        },
    }

    config = {"configurable": {"thread_id": run_id}}
    agent = get_agent()
    final_state = await agent.ainvoke(initial_state, config=config)

    return AgentRunResponse(
        run_id=run_id,
        record_id=record_id,
        classification=final_state.get("classification"),
        analysis=final_state.get("result", ""),
        published=True,
        hitl_paused=False,
    )


@router.post("/enrich/{record_id}/review", response_model=AgentRunResponse)
async def enrich_record_review(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await get_record_op(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    run_id = str(uuid.uuid4())
    initial_state = {
        "record_id": record_id,
        "record": {
            "source": record.source,
            "raw_data": record.raw_data,
            "tags": record.tags,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        },
    }

    config = {"configurable": {"thread_id": run_id}}
    agent_hitl = get_agent_hitl()
    final_state = await agent_hitl.ainvoke(initial_state, config=config)

    return AgentRunResponse(
        run_id=run_id,
        record_id=record_id,
        classification=final_state.get("classification"),
        analysis=final_state.get("result", ""),
        published=False,
        hitl_paused=True,
    )


@router.post("/runs/{run_id}/resume", response_model=AgentRunResponse)
async def resume_run(run_id: str, body: ResumeRequest):
    config = {"configurable": {"thread_id": run_id}}
    agent_hitl = get_agent_hitl()

    # get state
    state_snapshot = await agent_hitl.aget_state(config)
    if not state_snapshot:
        raise HTTPException(status_code=404, detail="Run not found or not resumable")

    if body.approve:
        final_state = await agent_hitl.ainvoke(None, config=config)
        published = True
    else:
        # update state
        await agent_hitl.aupdate_state(config, {"error": "rejected_by_human"})
        final_state = await agent_hitl.aget_state(config)
        final_state = final_state.values
        published = False

    return AgentRunResponse(
        run_id=run_id,
        record_id=final_state.get("record_id"),
        classification=final_state.get("classification"),
        analysis=final_state.get("result", ""),
        published=published,
        hitl_paused=False,
    )


@router.get("/enrich/{record_id}/stream")
async def stream_enrich_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await get_record_op(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    run_id = str(uuid.uuid4())
    initial_state = {
        "record_id": record_id,
        "record": {
            "source": record.source,
            "raw_data": record.raw_data,
            "tags": record.tags,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        },
    }

    config = {"configurable": {"thread_id": run_id}}
    agent = get_agent()

    async def event_gen() -> AsyncGenerator[str]:
        try:
            async for event in agent.astream_events(
                initial_state, config=config, version="v1"
            ):
                if event["event"] == "on_chain_end":
                    # skip root chain end if needed
                    pass
                elif (
                    event["event"] == "on_chain_stream"
                    or event["event"] == "on_chat_model_stream"
                ):
                    pass

                # actually LangGraph provides node outputs nicely via stream

            # Stream node outputs via astream(stream_mode="updates")
            # Each node completion emits an update event with node name and state
            async for event in agent.astream(
                initial_state, config=config, stream_mode="updates"
            ):
                for node_name, node_state in event.items():
                    data = {
                        "node": node_name,
                        "classification": node_state.get("classification").model_dump()
                        if node_state.get("classification")
                        else None,
                        "analysis": node_state.get("result", ""),
                    }
                    yield f"event: node_complete\ndata: {json.dumps(data)}\n\n"

            # We don't get the FULL state via updates, we only get the deltas. Let's merge it:
            final_state_snapshot = await agent.aget_state(config)
            final_state_vals = final_state_snapshot.values

            done_data = {
                "run_id": run_id,
                "record_id": record_id,
                "classification": final_state_vals.get("classification").model_dump()
                if final_state_vals.get("classification")
                else None,
                "analysis": final_state_vals.get("result", ""),
                "published": True,
                "hitl_paused": False,
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"
        except Exception as exc:
            logger.error("agent_stream_failed", extra={"error": str(exc)})
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
