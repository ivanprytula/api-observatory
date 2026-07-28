"""Integration tests for BI and Reporting endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration


_SOURCE: dict[str, Any] = {
    "name": "reporting-test-source",
    "url": "https://api.example.com/reporting",
    "source_type": "rest",
    "tags": ["Reporting", "Test"],
}

_SCHEMA_V1: dict[str, Any] = {
    "id": 99,
    "status": "ok",
    "payload": {"region": "eu", "latency_ms": 120},
}

_SCHEMA_V2_BREAKING: dict[str, Any] = {
    "id": 99,
    "status": {"code": "ok"},
    "payload": {"region": "eu"},
}


async def _create_source(client: AsyncClient, name: str) -> int:
    response = await client.post("/api/v1/sources", json={**_SOURCE, "name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


async def _seed_breaking_drift(client: AsyncClient, source_id: int) -> None:
    first = await client.post(
        "/api/v1/contracts/snapshots",
        json={
            "source_id": source_id,
            "schema_version": "v1",
            "payload_schema": _SCHEMA_V1,
        },
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/contracts/snapshots",
        json={
            "source_id": source_id,
            "schema_version": "v2",
            "payload_schema": _SCHEMA_V2_BREAKING,
        },
    )
    assert second.status_code == 201


class TestReportingApi:
    """BI and reporting API behavior."""

    async def test_kpi_rollups_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/kpi-rollups")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_kpi_rollups_returns_series_after_drift(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-kpi-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get(
            f"/api/v1/reporting/kpi-rollups?source_id={source_id}&days=30"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1

        first = body["items"][0]
        assert first["metric"] == "compatibility_score"
        assert first["source_id"] == source_id
        assert first["points"]

    async def test_cohort_comparison_returns_ranked_rows(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-cohort-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/cohort-comparison?days=30")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1

        row = next(item for item in body["items"] if item["source_id"] == source_id)
        assert row["rank"] >= 1
        assert 0.0 <= row["avg_compatibility_score"] <= 100.0
        assert 0.0 <= row["breaking_rate_pct"] <= 100.0

    async def test_dashboard_presets(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/dashboard-presets")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        preset_ids = {item["preset_id"] for item in body["items"]}
        assert "ops-scorecard" in preset_ids
        assert "exec-weekly-summary" in preset_ids

    async def test_create_export_job(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/reporting/exports",
            json={
                "preset_id": "ops-scorecard",
                "export_format": "json",
                "source_ids": [1],
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert body["preset_id"] == "ops-scorecard"
        assert body["export_format"] == "json"

    # ------------------------------------------------------------------
    # drift-heatmap
    # ------------------------------------------------------------------

    async def test_drift_heatmap_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/drift-heatmap")
        assert response.status_code == 200
        body = response.json()
        assert body["cells"] == []
        assert body["sources"] == []
        assert body["severities"] == []
        assert body["total_events"] == 0
        assert body["window_days"] >= 1

    async def test_drift_heatmap_contains_cells_after_drift(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-heatmap-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get(
            f"/api/v1/reporting/drift-heatmap?days=30&source_ids={source_id}"
        )
        assert response.status_code == 200
        body = response.json()

        assert body["total_events"] >= 1
        assert body["window_days"] == 30
        assert len(body["cells"]) >= 1

        # At least one cell should belong to the seeded source.
        source_cells = [c for c in body["cells"] if c["source_id"] == source_id]
        assert source_cells, "Expected at least one cell for the seeded source."

        # All heat_values must be in [0.0, 1.0].
        for cell in body["cells"]:
            assert 0.0 <= cell["heat_value"] <= 1.0

        # The hottest cell must have heat_value == 1.0 (normalisation invariant).
        assert max(c["heat_value"] for c in body["cells"]) == 1.0

    async def test_drift_heatmap_breaking_severity_present(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-heatmap-breaking-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get(
            f"/api/v1/reporting/drift-heatmap?days=30&source_ids={source_id}"
        )
        assert response.status_code == 200
        body = response.json()

        severities_in_cells = {c["severity"] for c in body["cells"]}
        # A breaking drift should produce a high or critical severity event.
        assert severities_in_cells & {"high", "critical", "medium"}

    async def test_drift_heatmap_severities_ordered(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "reporting-heatmap-order-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get(
            f"/api/v1/reporting/drift-heatmap?days=30&source_ids={source_id}"
        )
        assert response.status_code == 200
        body = response.json()

        canonical = ["critical", "high", "medium", "low", "none"]
        returned = body["severities"]
        # Returned severities must appear in canonical order.
        indices = [canonical.index(s) for s in returned if s in canonical]
        assert indices == sorted(indices), "Severities are not in canonical order."

    async def test_drift_heatmap_source_filter(self, client: AsyncClient) -> None:
        source_a = await _create_source(client, "reporting-heatmap-filter-a")
        source_b = await _create_source(client, "reporting-heatmap-filter-b")
        await _seed_breaking_drift(client, source_a)
        await _seed_breaking_drift(client, source_b)

        response = await client.get(
            f"/api/v1/reporting/drift-heatmap?days=30&source_ids={source_a}"
        )
        assert response.status_code == 200
        body = response.json()

        ids_in_response = {c["source_id"] for c in body["cells"]}
        assert source_b not in ids_in_response, "source_b should be excluded by filter."

    async def test_drift_heatmap_invalid_days(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/drift-heatmap?days=0")
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Cost-to-value chart
    # ------------------------------------------------------------------

    async def test_cost_value_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/cost-value")
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["team_summaries"] == []
        assert body["total_cost_usd"] == 0.0
        assert body["window_days"] >= 1

    async def test_cost_value_returns_rows_after_snapshot(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-cost-value-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/cost-value?days=30")
        assert response.status_code == 200
        body = response.json()
        ids = [r["source_id"] for r in body["rows"]]
        assert source_id in ids, "Source with snapshots should appear in rows."

    async def test_cost_value_source_with_no_cost_has_zero_total(
        self, client: AsyncClient
    ) -> None:
        """Source without cost_per_call_usd → total_cost_usd == 0, counts still present."""
        source_id = await _create_source(client, "reporting-cost-value-no-cost")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/cost-value?days=30")
        assert response.status_code == 200
        body = response.json()
        row = next((r for r in body["rows"] if r["source_id"] == source_id), None)
        assert row is not None
        assert row["total_cost_usd"] == 0.0
        assert row["total_calls"] >= 1

    async def test_cost_value_breaking_counts_as_insight(
        self, client: AsyncClient
    ) -> None:
        """Breaking drift event is counted as an insight_generated."""
        source_id = await _create_source(client, "reporting-cost-value-insight")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/cost-value?days=30")
        assert response.status_code == 200
        body = response.json()
        row = next((r for r in body["rows"] if r["source_id"] == source_id), None)
        assert row is not None
        assert row["insights_generated"] >= 1, (
            "Breaking drift should appear as insight."
        )

    async def test_cost_value_source_filter(self, client: AsyncClient) -> None:
        source_a = await _create_source(client, "reporting-cost-value-filter-a")
        source_b = await _create_source(client, "reporting-cost-value-filter-b")
        await _seed_breaking_drift(client, source_a)
        await _seed_breaking_drift(client, source_b)

        response = await client.get(
            f"/api/v1/reporting/cost-value?days=30&source_ids={source_a}"
        )
        assert response.status_code == 200
        body = response.json()
        ids_in_response = {r["source_id"] for r in body["rows"]}
        assert source_b not in ids_in_response, "source_b should be excluded by filter."

    async def test_cost_value_invalid_days(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/cost-value?days=0")
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Freshness SLA dashboard
    # ------------------------------------------------------------------

    async def test_freshness_sla_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/freshness-sla")
        assert response.status_code == 200
        body = response.json()
        assert body["sources"] == []
        assert body["incidents"] == []
        assert body["total_breached"] == 0
        assert body["total_ok"] == 0
        assert body["total_no_data"] == 0
        assert body["window_days"] >= 1
        assert body["sla_threshold_hours"] >= 1

    async def test_freshness_sla_source_with_snapshot_is_ok(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-freshness-ok-source")
        await _seed_breaking_drift(client, source_id)

        # Use a very large threshold so the just-created snapshot is within SLA.
        response = await client.get(
            "/api/v1/reporting/freshness-sla?days=30&sla_threshold_hours=168"
        )
        assert response.status_code == 200
        body = response.json()
        row = next((r for r in body["sources"] if r["source_id"] == source_id), None)
        assert row is not None
        assert row["last_snapshot_at"] is not None
        assert row["total_snapshots"] >= 1
        assert row["status"] in ("ok", "warning")

    async def test_freshness_sla_no_snapshot_is_no_data(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "reporting-freshness-no-data-source")

        response = await client.get(
            f"/api/v1/reporting/freshness-sla?days=30&source_ids={source_id}"
        )
        assert response.status_code == 200
        body = response.json()
        row = next((r for r in body["sources"] if r["source_id"] == source_id), None)
        assert row is not None
        assert row["last_snapshot_at"] is None
        assert row["status"] == "no_data"
        assert row["total_snapshots"] == 0

    async def test_freshness_sla_no_data_counted_in_total(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(
            client, "reporting-freshness-no-data-count-source"
        )
        response = await client.get(
            f"/api/v1/reporting/freshness-sla?days=30&source_ids={source_id}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_no_data"] >= 1

    async def test_freshness_sla_source_filter(self, client: AsyncClient) -> None:
        source_a = await _create_source(client, "reporting-freshness-filter-a")
        source_b = await _create_source(client, "reporting-freshness-filter-b")
        await _seed_breaking_drift(client, source_a)
        await _seed_breaking_drift(client, source_b)

        response = await client.get(
            f"/api/v1/reporting/freshness-sla?days=30&source_ids={source_a}"
        )
        assert response.status_code == 200
        body = response.json()
        ids_in_response = {r["source_id"] for r in body["sources"]}
        assert source_b not in ids_in_response, "source_b should be excluded by filter."

    async def test_freshness_sla_invalid_days(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/freshness-sla?days=0")
        assert response.status_code == 422

    async def test_freshness_sla_invalid_threshold(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/reporting/freshness-sla?sla_threshold_hours=0"
        )
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------------

    async def test_executive_summary_empty_db(self, client: AsyncClient) -> None:
        """Empty database returns a valid summary with zero counts and no actions."""
        response = await client.get("/api/v1/reporting/executive-summary")
        assert response.status_code == 200
        body = response.json()

        assert body["window_days"] >= 1
        assert "generated_at" in body

        drift = body["drift"]
        assert drift["total_sources_with_drift"] == 0
        assert drift["total_events"] == 0
        assert drift["avg_compatibility_score"] == 100.0
        assert drift["breaking_source_count"] == 0

        freshness = body["freshness"]
        assert freshness["total_sources"] == 0
        assert freshness["breached"] == 0
        assert freshness["open_incidents"] == 0

        cost = body["cost"]
        assert cost["total_cost_usd"] == 0.0
        assert cost["total_sources"] == 0
        assert cost["avg_cost_per_insight_usd"] is None
        assert cost["highest_cost_source_name"] is None

        assert body["action_items"] == []
        assert body["total_actions"] == 0

    async def test_executive_summary_drift_section_populated(
        self, client: AsyncClient
    ) -> None:
        """Drift section reflects seeded breaking events."""
        source_id = await _create_source(client, "exec-summary-drift-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/executive-summary?days=30")
        assert response.status_code == 200
        body = response.json()

        drift = body["drift"]
        assert drift["total_sources_with_drift"] >= 1
        assert drift["total_events"] >= 1
        assert 0.0 <= drift["avg_compatibility_score"] <= 100.0
        assert drift["breaking_source_count"] >= 1

    async def test_executive_summary_action_items_shape(
        self, client: AsyncClient
    ) -> None:
        """Action items contain required fields with valid priority and category values."""
        source_id = await _create_source(client, "exec-summary-actions-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/executive-summary?days=30")
        assert response.status_code == 200
        body = response.json()

        valid_priorities = {"critical", "high", "medium", "low"}
        valid_categories = {"drift", "freshness", "cost", "reliability"}

        for item in body["action_items"]:
            assert item["priority"] in valid_priorities
            assert item["category"] in valid_categories
            assert item["title"]
            assert item["description"]

    async def test_executive_summary_action_items_sorted_by_priority(
        self, client: AsyncClient
    ) -> None:
        """Action items are ordered critical → high → medium → low."""
        source_id = await _create_source(client, "exec-summary-sort-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/reporting/executive-summary?days=30")
        assert response.status_code == 200
        body = response.json()

        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [order[item["priority"]] for item in body["action_items"]]
        assert priorities == sorted(priorities), (
            "Actions must be sorted critical first."
        )

    async def test_executive_summary_total_actions_matches_list(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/reporting/executive-summary?days=30")
        assert response.status_code == 200
        body = response.json()
        assert body["total_actions"] == len(body["action_items"])

    async def test_executive_summary_invalid_days(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/reporting/executive-summary?days=0")
        assert response.status_code == 422

    async def test_executive_summary_invalid_sla_threshold(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            "/api/v1/reporting/executive-summary?sla_threshold_hours=0"
        )
        assert response.status_code == 422
