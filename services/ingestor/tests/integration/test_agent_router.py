"""Integration tests for the agent router (GET/resume) — the HTTP layer.

`services.ingestor.agent.runner.resume_agent_run` is mocked here: the ASGI
test client never runs the app's lifespan (see main.py's comment on why
Prometheus instrumentation is registered at module level), so the real
Postgres checkpointer never starts in this test process and `_graph` stays
`None`. The graph's own pause/resume wiring is covered by
`services/ingestor/tests/unit/agent/test_graph.py`; this file covers the
router's request/response contract instead.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import AgentRun, Observation


async def _create_agent_run(
    db: AsyncSession, *, status: str = "awaiting_review"
) -> AgentRun:
    observation = Observation(
        source="agent-router-test-source",
        timestamp=datetime(2026, 1, 1),
        raw_data={"event_type": "breaking", "severity": "critical"},
        tags=["incident", "critical"],
    )
    db.add(observation)
    await db.flush()
    agent_run = AgentRun(
        observation_id=observation.id,
        status=status,
        severity_assessment="critical" if status != "pending" else None,
    )
    db.add(agent_run)
    await db.commit()
    await db.refresh(agent_run)
    return agent_run


class TestGetAgentRun:
    async def test_returns_404_for_missing_run(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/agent/runs/999999")
        assert response.status_code == 404

    async def test_returns_current_state(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        agent_run = await _create_agent_run(db, status="awaiting_review")

        response = await client.get(f"/api/v1/agent/runs/{agent_run.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == agent_run.id
        assert body["status"] == "awaiting_review"
        assert body["severity_assessment"] == "critical"


class TestResumeAgentRun:
    async def test_returns_404_for_missing_run(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/agent/runs/999999/resume", json={"approve": True}
        )
        assert response.status_code == 404

    async def test_returns_409_when_not_awaiting_review(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        agent_run = await _create_agent_run(db, status="pending")

        response = await client.post(
            f"/api/v1/agent/runs/{agent_run.id}/resume", json={"approve": True}
        )

        assert response.status_code == 409

    async def test_approve_delegates_to_runner_and_returns_updated_run(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        agent_run = await _create_agent_run(db, status="awaiting_review")
        agent_run.status = "approved"
        agent_run.reviewer_user_id = 7

        with patch(
            "services.ingestor.agent.runner.resume_agent_run",
            new=AsyncMock(return_value=agent_run),
        ) as resume_mock:
            response = await client.post(
                f"/api/v1/agent/runs/{agent_run.id}/resume",
                json={"approve": True, "reviewer_user_id": 7},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert response.json()["reviewer_user_id"] == 7
        resume_mock.assert_awaited_once_with(
            agent_run.id, approve=True, reviewer_user_id=7
        )

    async def test_returns_501_when_agent_disabled(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        agent_run = await _create_agent_run(db, status="awaiting_review")

        with patch(
            "services.ingestor.agent.runner.resume_agent_run",
            new=AsyncMock(
                side_effect=RuntimeError("Incident-triage agent is not enabled")
            ),
        ):
            response = await client.post(
                f"/api/v1/agent/runs/{agent_run.id}/resume", json={"approve": True}
            )

        assert response.status_code == 501
