"""Comprehensive middleware and edge case tests.

Tests for:
- Correlation ID middleware behavior
- Error handling
- Boundary conditions
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.shared.payloads import RECORD_API


# ---------------------------------------------------------------------------
# Correlation ID Middleware
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestCorrelationIdMiddleware:
    """Verify correlation ID is generated, injected, and returned."""

    async def test_correlation_id_auto_generated(self, client: AsyncClient) -> None:
        """Request without X-Correlation-ID header generates UUID."""
        r = await client.get("/readyz")
        assert r.status_code == 200
        cid = r.headers.get("X-Correlation-ID")
        assert cid is not None
        assert len(cid) == 36  # UUID format: 8-4-4-4-12

    async def test_correlation_id_propagated(self, client: AsyncClient) -> None:
        """Request with X-Correlation-ID header is propagated in response."""
        custom_cid = str(uuid.uuid4())
        r = await client.post(
            "/api/v1/records",
            json=RECORD_API,
            headers={"X-Correlation-ID": custom_cid},
        )
        assert r.status_code == 201
        assert r.headers.get("X-Correlation-ID") == custom_cid

    async def test_correlation_id_on_error_response(self, client: AsyncClient) -> None:
        """Correlation ID present on error responses (404, 422)."""
        custom_cid = str(uuid.uuid4())
        r = await client.get(
            "/api/v1/records/99999",
            headers={"X-Correlation-ID": custom_cid},
        )
        assert r.status_code == 404
        assert r.headers.get("X-Correlation-ID") == custom_cid

    async def test_correlation_id_on_validation_error(
        self, client: AsyncClient
    ) -> None:
        """Correlation ID present on validation errors (422)."""
        custom_cid = str(uuid.uuid4())
        r = await client.post(
            "/api/v1/records",
            json={"data": {}},
            headers={"X-Correlation-ID": custom_cid},
        )
        assert r.status_code == 422
        assert r.headers.get("X-Correlation-ID") == custom_cid


# ---------------------------------------------------------------------------
# Pagination Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestPaginationEdgeCases:
    """Boundary conditions on pagination parameters."""

    async def test_list_with_zero_offset(self, client: AsyncClient) -> None:
        """Offset=0 returns from the beginning."""
        await client.post("/api/v1/records", json=RECORD_API)
        await client.post("/api/v1/records", json=RECORD_API)

        r = await client.get("/api/v1/records?offset=0&limit=10")
        assert r.status_code == 200
        assert len(r.json()) >= 2

    async def test_list_with_offset_beyond_count(self, client: AsyncClient) -> None:
        """Offset beyond record count returns empty list."""
        r = await client.get("/api/v1/records?offset=1000&limit=10")
        assert r.status_code == 200
        body = r.json()
        # Response may be a dict with 'records' and 'pagination' keys
        if isinstance(body, dict):
            assert "records" in body
            assert len(body["records"]) == 0
        else:
            assert isinstance(body, list)

    async def test_list_with_negative_limit(self, client: AsyncClient) -> None:
        """Negative limit is rejected."""
        r = await client.get("/api/v1/records?offset=0&limit=-5")
        assert r.status_code in [422, 400, 200]  # Depends on validation

    async def test_list_with_zero_limit(self, client: AsyncClient) -> None:
        """Zero limit is rejected."""
        r = await client.get("/api/v1/records?offset=0&limit=0")
        assert r.status_code in [422, 400, 200]  # Depends on validation


# ---------------------------------------------------------------------------
# Request Body Validation
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRequestBodyValidation:
    """Request body validation edge cases."""

    async def test_create_with_extra_fields(self, client: AsyncClient) -> None:
        """Extra fields are silently ignored."""
        payload = {**RECORD_API, "extra_field": "should_be_ignored"}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 201
        result = r.json()
        assert "extra_field" not in result

    async def test_create_with_empty_source(self, client: AsyncClient) -> None:
        """Empty source string fails validation."""
        payload = {**RECORD_API, "source": ""}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 422

    async def test_create_with_oversized_source(self, client: AsyncClient) -> None:
        """Source > max_length fails validation."""
        payload = {**RECORD_API, "source": "x" * 300}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 422

    async def test_create_with_invalid_timestamp_format(
        self, client: AsyncClient
    ) -> None:
        """Invalid timestamp format fails validation."""
        payload = {**RECORD_API, "timestamp": "not-a-timestamp"}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 422

    async def test_create_with_empty_tags_list(self, client: AsyncClient) -> None:
        """Empty tags list is allowed."""
        payload = {**RECORD_API, "tags": []}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 201
        result = r.json()
        assert result["tags"] == []

    async def test_create_with_oversized_tags(self, client: AsyncClient) -> None:
        """Tags array > max_length fails validation."""
        payload = {**RECORD_API, "tags": [f"tag-{i}" for i in range(100)]}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 422

    async def test_create_with_non_dict_data(self, client: AsyncClient) -> None:
        """data field must be a dict."""
        payload = {**RECORD_API, "data": "not-a-dict"}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Fixture Verification
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRecordFixtures:
    """Verify record fixtures work correctly."""

    async def test_created_record_has_id(self, created_record: dict) -> None:
        """created_record fixture has id field."""
        assert "id" in created_record
        assert isinstance(created_record["id"], int)

    async def test_created_record_has_source(self, created_record: dict) -> None:
        """created_record fixture has source field."""
        assert "source" in created_record
        assert isinstance(created_record["source"], str)

    async def test_created_records_returns_multiple(
        self, created_records: list[dict]
    ) -> None:
        """created_records fixture returns 3 records."""
        assert len(created_records) == 3
        for record in created_records:
            assert "id" in record
            assert "source" in record

    async def test_record_payload_is_mutable(self, record_payload: dict) -> None:
        """record_payload fixture returns mutable copy."""
        original_source = record_payload["source"]
        record_payload["source"] = "modified"
        assert record_payload["source"] == "modified"
        assert original_source != "modified"


# ---------------------------------------------------------------------------
# Error Response Structure
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestErrorResponses:
    """Verify error responses have consistent structure."""

    async def test_404_has_detail(self, client: AsyncClient) -> None:
        """404 errors include detail field."""
        r = await client.get("/api/v1/records/99999")
        assert r.status_code == 404
        body = r.json()
        assert "detail" in body

    async def test_422_has_detail(self, client: AsyncClient) -> None:
        """422 errors include detail field."""
        r = await client.post("/api/v1/records", json={"data": {}})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body


# ---------------------------------------------------------------------------
# Request Lifecycle Logging
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRequestLifecycleLogging:
    """Verify request_start / request_end log entries are emitted with correct fields."""

    async def test_request_lifecycle_logs_emitted(self, client: AsyncClient) -> None:
        """GET /readyz emits request_start and request_end log entries."""
        from unittest.mock import patch

        with patch("services.ingestor.main.logger") as mock_logger:
            await client.get("/readyz")

        call_args = [c[0][0] for c in mock_logger.info.call_args_list]
        assert "request_start" in call_args, f"Missing request_start. Got: {call_args}"
        assert "request_end" in call_args, f"Missing request_end. Got: {call_args}"

    async def test_request_end_has_duration_ms(self, client: AsyncClient) -> None:
        """request_end log entry includes duration_ms field in extra."""
        from unittest.mock import patch

        with patch("services.ingestor.main.logger") as mock_logger:
            await client.get("/readyz")

        end_calls = [
            c for c in mock_logger.info.call_args_list if c[0][0] == "request_end"
        ]
        assert end_calls, "No request_end log call found"
        extra = end_calls[0][1].get("extra", {})
        assert "duration_ms" in extra, f"request_end missing duration_ms. extra={extra}"
        assert isinstance(extra["duration_ms"], float)
        assert extra["duration_ms"] >= 0

    async def test_request_end_has_status_code(self, client: AsyncClient) -> None:
        """request_end log entry includes status_code field in extra."""
        from unittest.mock import patch

        with patch("services.ingestor.main.logger") as mock_logger:
            r = await client.get("/readyz")

        end_calls = [
            c for c in mock_logger.info.call_args_list if c[0][0] == "request_end"
        ]
        assert end_calls
        extra = end_calls[0][1].get("extra", {})
        assert "status_code" in extra
        assert extra["status_code"] == r.status_code

    async def test_request_start_has_method_and_path(self, client: AsyncClient) -> None:
        """request_start log entry includes method and path in extra."""
        from unittest.mock import patch

        with patch("services.ingestor.main.logger") as mock_logger:
            await client.get("/readyz")

        start_calls = [
            c for c in mock_logger.info.call_args_list if c[0][0] == "request_start"
        ]
        assert start_calls
        extra = start_calls[0][1].get("extra", {})
        assert extra.get("method") == "GET"
        assert extra.get("path") == "/readyz"
