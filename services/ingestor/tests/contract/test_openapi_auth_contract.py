"""OpenAPI contract coverage for the default production-v1 JWT boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import schemathesis
from hypothesis import Phase, find, settings
from starlette_testclient import TestClient

from services.ingestor import auth as ingestor_auth
from services.ingestor.main import (
    _PUBLIC_V1_AUTH_PATHS,
    _is_protected_v1_path,
    app,
)


pytestmark = pytest.mark.contract

_ASGI_HEADERS = {"host": "localhost"}


@asynccontextmanager
async def _contract_lifespan(_: Any) -> AsyncIterator[None]:
    """Avoid unrelated external-service startup for this ASGI-only contract gate."""
    yield


async def _discard_security_audit_event(
    *,
    event_type: str,
    action: str,
    decision: str,
    actor_type: str,
    actor_id: str | None = None,
    tenant_id: int | None = None,
    reason: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    """Keep denied-request audit persistence outside this HTTP contract gate."""


@pytest.fixture(scope="module", autouse=True)
def _isolate_application_hooks() -> Iterator[None]:
    """Keep contract-only hooks scoped to selected contract tests."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(app.router, "lifespan_context", _contract_lifespan)
    monkeypatch.setattr(
        ingestor_auth,
        "emit_security_audit_event",
        _discard_security_audit_event,
    )
    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module")
def asgi_session() -> Iterator[TestClient]:
    """Keep one in-process ASGI client for all generated contract cases."""
    with TestClient(app, base_url="http://localhost") as session:
        yield session


def _protected_v1_schema() -> schemathesis.BaseSchema:
    """Load and limit the generated schema to protected v1 operations only."""
    schema = schemathesis.openapi.from_asgi(
        "/openapi.json", app, headers=_ASGI_HEADERS
    ).include(path_regex=r"^/api/v1/")
    for path in _PUBLIC_V1_AUTH_PATHS:
        schema = schema.exclude(path=path)
    return schema


_PROTECTED_V1_SCHEMA = _protected_v1_schema()


def _operations(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return documented HTTP operations for protected v1 paths."""
    return [
        operation
        for path, path_item in schema["paths"].items()
        if _is_protected_v1_path(path)
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and isinstance(operation, dict)
    ]


def test_openapi_documents_protected_v1_auth_contract() -> None:
    """Every protected v1 operation advertises bearer auth and JSON auth errors."""
    schema = app.openapi()
    bearer_scheme = schema["components"]["securitySchemes"]["BearerAuth"]

    assert bearer_scheme == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    operations = _operations(schema)
    assert operations
    for operation in operations:
        assert operation["security"] == [{"BearerAuth": []}]
        for status_code in ("401", "403"):
            response = operation["responses"][status_code]
            assert response["content"]["application/json"]["schema"] == {
                "type": "object",
                "required": ["detail"],
                "properties": {"detail": {}},
            }


def test_protected_v1_operations_reject_generated_anonymous_cases(
    asgi_session: TestClient,
) -> None:
    """One generated unauthenticated request per protected operation returns 401."""
    generation_settings = settings(
        max_examples=1,
        deadline=None,
        phases=(Phase.generate,),
    )
    for result in _PROTECTED_V1_SCHEMA.get_all_operations():
        operation = result.ok()
        case = find(
            operation.as_strategy(),
            lambda _: True,
            settings=generation_settings,
        )
        case.headers.pop("Authorization", None)
        response = case.call(session=asgi_session, headers=_ASGI_HEADERS)

        assert response.status_code == 401, operation.label
        case.validate_response(response)
