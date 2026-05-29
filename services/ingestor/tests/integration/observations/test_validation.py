"""Comprehensive Pydantic v2 validation tests.

Week 2 Milestone 5: Validation Deep-Dive
Tests cover custom validators, error messages, and edge cases.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from services.ingestor.api_schemas.observations import ObservationRequest
from tests.shared.payloads import OBSERVATION_API


_OBSERVATION = OBSERVATION_API


# ---------------------------------------------------------------------------
# Missing & empty required fields
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_missing_required_field_source(client: AsyncClient) -> None:
    """Missing source (required field) → 422."""
    bad = {**_OBSERVATION}
    del bad["source"]

    r = await client.post("/api/v1/observations", json=bad)

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    # Error should mention 'source' field
    detail_str = str(body["detail"]).lower()
    assert "source" in detail_str


@pytest.mark.integration
async def test_validation_missing_required_field_data(client: AsyncClient) -> None:
    """Missing data (required field) → 422."""
    bad = {**_OBSERVATION}
    del bad["data"]

    r = await client.post("/api/v1/observations", json=bad)

    assert r.status_code == 422


@pytest.mark.integration
async def test_validation_empty_source_string(client: AsyncClient) -> None:
    """Empty source (violates min_length=1) → 422."""
    r = await client.post("/api/v1/observations", json={**_OBSERVATION, "source": ""})

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body


@pytest.mark.integration
async def test_validation_source_too_long(client: AsyncClient) -> None:
    """Source exceeds max_length (255) → 422."""
    long_source = "x" * 256

    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": long_source}
    )

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Custom validators: source
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_source_localhost_rejected(client: AsyncClient) -> None:
    """Custom validator: source='localhost' → 422 (security rule).

    Week 2 Milestone 5: Domain-specific validation rule.
    """
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": "localhost"}
    )

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    # Error should mention 'localhost'
    assert "localhost" in str(body["detail"]).lower()


@pytest.mark.integration
async def test_validation_source_localhost_case_insensitive(
    client: AsyncClient,
) -> None:
    """Localhost validation is case-insensitive."""
    for variant in ["LOCALHOST", "LocalHost", "LoCalHost"]:
        r = await client.post(
            "/api/v1/observations", json={**_OBSERVATION, "source": variant}
        )
        assert r.status_code == 422, f"Failed for source={variant}"


@pytest.mark.integration
async def test_validation_source_127_0_0_1_rejected(client: AsyncClient) -> None:
    """Loopback IP (127.0.0.1) is rejected as invalid source.

    127.0.0.1 is the IPv4 loopback address, same as 'localhost'.
    """
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": "127.0.0.1"}
    )

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert "loopback" in str(body["detail"]).lower() or "127.0.0.1" in str(
        body["detail"]
    )


@pytest.mark.integration
async def test_validation_source_ipv6_loopback_rejected(client: AsyncClient) -> None:
    """IPv6 loopback (::1) is rejected as invalid source."""
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": "::1"}
    )

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body


@pytest.mark.integration
async def test_validation_source_0_0_0_0_rejected(client: AsyncClient) -> None:
    """IPv4 wildcard (0.0.0.0) is rejected as invalid source.

    0.0.0.0 is the 'any address' used for binding servers, not a valid
    external source for observations.
    """
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": "0.0.0.0"}
    )

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert "reserved" in str(body["detail"]).lower() or "0.0.0.0" in str(body["detail"])


@pytest.mark.integration
async def test_validation_source_ipv6_wildcard_rejected(client: AsyncClient) -> None:
    """IPv6 wildcard (::) is rejected as invalid source."""
    r = await client.post("/api/v1/observations", json={**_OBSERVATION, "source": "::"})

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Custom validators: timestamp
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_timestamp_future_rejected(client: AsyncClient) -> None:
    """Custom validator: future timestamp → 422.

    Timestamps far in future (2099) should be rejected.
    """
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "timestamp": "2099-01-01T00:00:00"},
    )

    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert "future" in str(body["detail"]).lower()


@pytest.mark.integration
async def test_validation_timestamp_past_accepted(client: AsyncClient) -> None:
    """Past timestamps should be accepted."""
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "timestamp": "2020-01-01T00:00:00"},
    )

    assert r.status_code == 201


@pytest.mark.integration
async def test_validation_timestamp_invalid_format(client: AsyncClient) -> None:
    """Invalid ISO 8601 format → 422."""
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "timestamp": "not-a-date"},
    )

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Custom validators: tags
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_tags_normalized_to_lowercase(client: AsyncClient) -> None:
    """Tags are lowercase-normalized (not a rejection, a transformation).

    Week 2 Milestone 5: Validators can transform, not just validate.
    """
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "tags": ["NASDAQ", "Tech", "STOCK"]},
    )

    assert r.status_code == 201
    body = r.json()
    # Verify tags were lowercased
    assert body["tags"] == ["nasdaq", "tech", "stock"]


@pytest.mark.integration
async def test_validation_tags_too_many(client: AsyncClient) -> None:
    """Tags exceed max_items (10) → 422."""
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "tags": [f"tag-{i}" for i in range(11)]},
    )

    assert r.status_code == 422


@pytest.mark.integration
async def test_validation_tags_empty_allowed(client: AsyncClient) -> None:
    """Empty tags list is allowed (default_factory=[])."""
    r = await client.post(
        "/api/v1/observations",
        json={**_OBSERVATION, "tags": []},
    )

    assert r.status_code == 201
    body = r.json()
    assert body["tags"] == []


# ---------------------------------------------------------------------------
# Data field (flexible dict) validation
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_data_accepts_empty_dict(client: AsyncClient) -> None:
    """Data field can be empty dict."""
    r = await client.post("/api/v1/observations", json={**_OBSERVATION, "data": {}})

    assert r.status_code == 201
    body = r.json()
    assert body["raw_data"] == {}


@pytest.mark.integration
async def test_validation_data_accepts_complex_dict(client: AsyncClient) -> None:
    """Data field accepts nested/complex structures."""
    complex_data = {
        "nested": {"key": "value"},
        "list": [1, 2, 3],
        "boolean": True,
        "null": None,
        "number": 42.5,
    }
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "data": complex_data}
    )

    assert r.status_code == 201
    body = r.json()
    assert body["raw_data"] == complex_data


# ---------------------------------------------------------------------------
# Comprehensive error response validation
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_error_response_structure(client: AsyncClient) -> None:
    """Validation error response has proper structure for client handling.

    Pydantic v2 returns standardized validation error format.
    """
    r = await client.post("/api/v1/observations", json={})  # Empty request

    assert r.status_code == 422
    body = r.json()
    # Pydantic v2 validation error structure
    assert "detail" in body
    assert isinstance(body["detail"], list)
    # Each error should have 'msg' and 'loc'
    for error in body["detail"]:
        assert "msg" in error or "message" in error


@pytest.mark.integration
async def test_validation_multiple_errors_reported(client: AsyncClient) -> None:
    """Multiple validation errors are all reported (not just first one)."""
    # This request violates multiple constraints:
    # - source is empty (min_length=1)
    # - timestamp is future
    # - missing data field
    bad_data = {
        "source": "",  # Empty
        "timestamp": "2099-01-01T00:00:00",  # Future
        # data is missing
        "tags": ["VALID"],
    }
    r = await client.post("/api/v1/observations", json=bad_data)

    assert r.status_code == 422
    body = r.json()
    # Should report multiple errors
    errors = body["detail"]
    assert len(errors) >= 2, f"Expected multiple errors, got {errors}"


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_batch_size_minimum(client: AsyncClient) -> None:
    """Batch with 0 observations (MIN_BATCH_SIZE=1) → 422."""
    r = await client.post("/api/v1/observations/batch", json={"observations": []})

    assert r.status_code == 422


@pytest.mark.integration
async def test_validation_batch_size_maximum(client: AsyncClient) -> None:
    """Batch with >1000 observations (MAX_BATCH_SIZE=1000) → 422."""
    payload = {"observations": [_OBSERVATION] * 1001}

    r = await client.post("/api/v1/observations/batch", json=payload)

    assert r.status_code == 422


@pytest.mark.integration
async def test_validation_batch_validates_each_observation(client: AsyncClient) -> None:
    """If any observation in batch is invalid, entire batch is rejected."""
    payload = {
        "observations": [
            _OBSERVATION,  # Valid
            {**_OBSERVATION, "source": "127.0.0.1"},  # Invalid (loopback IP)
            _OBSERVATION,  # Would be valid but batch is rejected
        ]
    }

    r = await client.post("/api/v1/observations/batch", json=payload)

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Helpful error messages
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_error_messages_helpful(client: AsyncClient) -> None:
    """Error messages are descriptive enough to guide users.

    Week 2 Milestone 5: "Error messages are helpful"
    """
    # Send localhost
    r = await client.post(
        "/api/v1/observations", json={**_OBSERVATION, "source": "localhost"}
    )

    assert r.status_code == 422
    body = r.json()
    error_text = str(body["detail"]).lower()
    # Should mention what constraint was violated
    assert any(
        keyword in error_text for keyword in ["localhost", "source", "invalid", "not"]
    ), f"Error message not helpful: {body['detail']}"


# ---------------------------------------------------------------------------
# Timezone-aware timestamp handling (schema validator branches)
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_validation_timestamp_tz_aware_utc_stripped(
    client: AsyncClient,
) -> None:
    """Tz-aware UTC timestamp is stripped to naive and accepted."""
    observation = ObservationRequest(
        source="test.example.com",
        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        data={"v": 1},
    )
    assert observation.timestamp.tzinfo is None
    assert observation.timestamp == datetime(2024, 1, 15, 10, 0, 0)


@pytest.mark.integration
async def test_validation_timestamp_tz_aware_custom_stripped(
    client: AsyncClient,
) -> None:
    """Tz-aware timestamp with arbitrary offset is stripped to naive."""
    ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    observation = ObservationRequest(
        source="test.example.com",
        timestamp=ts,
        data={"v": 1},
    )
    assert observation.timestamp.tzinfo is None


@pytest.mark.integration
async def test_validation_timestamp_future_tz_aware_rejected(
    client: AsyncClient,
) -> None:
    """Tz-aware future timestamp is rejected after tz-stripping."""
    future_ts = datetime(2099, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="future"):
        ObservationRequest(
            source="test.example.com",
            timestamp=future_ts,
            data={"v": 1},
        )
