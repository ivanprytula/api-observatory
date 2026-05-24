"""Integration tests for Provider Scorecard endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient


_SOURCE: dict[str, Any] = {
    "url": "https://api.provider-scorecard-test.example.com",
    "source_type": "rest",
    "tags": ["scorecard-test"],
}


async def _create_source(client: AsyncClient, name: str) -> int:
    response = await client.post("/api/v1/sources", json={**_SOURCE, "name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _sample(
    source_id: int,
    *,
    success: bool = True,
    latency_ms: float = 50.0,
    offset_minutes: int = 0,
) -> dict[str, Any]:
    ts = datetime.now(UTC) - timedelta(minutes=offset_minutes)
    return {
        "source_id": source_id,
        "sampled_at": ts.isoformat(),
        "latency_ms": latency_ms,
        "is_success": success,
        "http_status": 200 if success else 503,
    }


async def _seed_samples(
    client: AsyncClient,
    source_id: int,
    successes: int = 9,
    failures: int = 1,
) -> None:
    for i in range(successes):
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json=_sample(
                source_id, success=True, latency_ms=50.0 + i * 10, offset_minutes=i
            ),
        )
        assert resp.status_code == 201

    for j in range(failures):
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json=_sample(
                source_id,
                success=False,
                latency_ms=5000.0,
                offset_minutes=successes + j,
            ),
        )
        assert resp.status_code == 201


class TestHealthSamplesApi:
    """POST /api/v1/scorecards/samples."""

    async def test_record_sample_returns_201(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-sample-create")
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json=_sample(source_id, latency_ms=120.0),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source_id"] == source_id
        assert body["latency_ms"] == 120.0
        assert body["is_success"] is True
        assert "id" in body

    async def test_record_failed_sample(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-sample-fail")
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json={
                **_sample(source_id, success=False, latency_ms=4000.0),
                "http_status": 503,
                "error_message": "Service unavailable",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_success"] is False
        assert body["http_status"] == 503
        assert body["error_message"] == "Service unavailable"

    async def test_invalid_latency_rejected(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-sample-invalid")
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json={**_sample(source_id), "latency_ms": -1.0},
        )
        assert resp.status_code == 422

    async def test_sample_with_region(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-sample-region")
        resp = await client.post(
            "/api/v1/scorecards/samples",
            json={**_sample(source_id), "region": "eu-west-1"},
        )
        assert resp.status_code == 201
        assert resp.json()["region"] == "eu-west-1"


class TestScorecardListApi:
    """GET /api/v1/scorecards."""

    async def test_empty_when_no_samples(self, client: AsyncClient) -> None:
        """Sources with no samples still appear but show 100% uptime / 0 count."""
        source_id = await _create_source(client, "sc-list-empty")
        resp = await client.get(f"/api/v1/scorecards?source_id={source_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        sc = body["items"][0]
        assert sc["source_id"] == source_id
        assert sc["sample_count"] == 0
        assert sc["uptime_pct"] == 100.0
        assert sc["error_budget_burn_rate"] == 0.0

    async def test_uptime_and_burn_rate_computed(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-list-seeded")
        await _seed_samples(client, source_id, successes=9, failures=1)

        resp = await client.get(
            f"/api/v1/scorecards?source_id={source_id}&days=30&slo_target_pct=99.9"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        sc = body["items"][0]

        assert sc["sample_count"] == 10
        assert sc["error_count"] == 1
        assert abs(sc["uptime_pct"] - 90.0) < 0.01
        # error_rate=0.10, budget=0.001  → burn_rate ≈ 100
        assert sc["error_budget_burn_rate"] > 50.0

    async def test_p95_latency_reasonable(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-list-p95")
        # Seed 20 samples with latencies 10, 20, …, 200 ms, all successful
        for i in range(20):
            resp = await client.post(
                "/api/v1/scorecards/samples",
                json=_sample(
                    source_id, latency_ms=float((i + 1) * 10), offset_minutes=i
                ),
            )
            assert resp.status_code == 201

        resp = await client.get(f"/api/v1/scorecards?source_id={source_id}&days=7")
        assert resp.status_code == 200
        sc = resp.json()["items"][0]
        # p95 of 10..200 (step 10): rank = ceil(0.95*20) = 19 → value 190
        assert 180.0 <= sc["p95_latency_ms"] <= 200.0

    async def test_list_respects_limit(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/scorecards?limit=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 1

    async def test_invalid_slo_target_rejected(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/scorecards?slo_target_pct=50")
        assert resp.status_code == 422

    async def test_invalid_days_rejected(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/scorecards?days=0")
        assert resp.status_code == 422


class TestScorecardDetailApi:
    """GET /api/v1/scorecards/{source_id}."""

    async def test_404_for_unknown_source(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/scorecards/999999")
        assert resp.status_code == 404

    async def test_returns_scorecard_for_known_source(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "sc-detail-known")
        await _seed_samples(client, source_id, successes=5, failures=0)

        resp = await client.get(f"/api/v1/scorecards/{source_id}?days=30")
        assert resp.status_code == 200
        sc = resp.json()
        assert sc["source_id"] == source_id
        assert sc["sample_count"] == 5
        assert sc["uptime_pct"] == 100.0
        assert sc["error_count"] == 0
        assert sc["error_budget_burn_rate"] == 0.0

    async def test_detail_with_custom_slo(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-detail-slo")
        await _seed_samples(client, source_id, successes=8, failures=2)

        resp = await client.get(
            f"/api/v1/scorecards/{source_id}?slo_target_pct=95.0&days=30"
        )
        assert resp.status_code == 200
        sc = resp.json()
        # 80% uptime vs 95% SLO: budget=5%, error_rate=20%  → burn=4.0
        assert sc["slo_target_pct"] == 95.0
        assert abs(sc["error_budget_burn_rate"] - 4.0) < 0.01

    async def test_zero_samples_returns_100_uptime(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "sc-detail-zero")
        resp = await client.get(f"/api/v1/scorecards/{source_id}?days=7")
        assert resp.status_code == 200
        sc = resp.json()
        assert sc["sample_count"] == 0
        assert sc["uptime_pct"] == 100.0
        assert sc["p95_latency_ms"] == 0.0
