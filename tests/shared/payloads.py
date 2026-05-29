"""Shared test payloads and data factories."""

OBSERVATION_API = {
    "source": "api.example.com",
    "data": {"price": 123.45},
    "tags": ["Stock", "NASDAQ"],
    # timestamp is optional — defaults to current UTC if omitted
}

OBSERVATION_PERF = {
    "source": "perf.test",
    "timestamp": "2024-01-15T10:00:00",
    "data": {"value": 0},
    "tags": [],
}

OBSERVATION_E2E = {
    "source": "test",
    "timestamp": "2024-01-15T10:00:00Z",
    "data": {"index": 0},
}
