from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from services.ingestor.core.tenant import (
    TenantMiddleware,
    get_tenant_id,
    get_user_role,
)


pytestmark = pytest.mark.unit

type App = Callable[[Scope, Receive, Send], Awaitable[None]]


async def _receive() -> Message:
    return {"type": "http.disconnect"}


async def _send(_message: Message) -> None:
    return None


def _scope(headers: list[tuple[bytes, bytes]]) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }


async def test_header_tenant_context_is_visible_only_during_request() -> None:
    seen: dict[str, int | str | None] = {}

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen["tenant"] = get_tenant_id()
        seen["role"] = get_user_role()

    await TenantMiddleware(app)(_scope([(b"x-tenant-id", b"42")]), _receive, _send)

    assert seen == {"tenant": 42, "role": None}
    assert get_tenant_id() is None
    assert get_user_role() is None


async def test_bearer_claims_take_priority_and_set_admin_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, int | str | None] = {}

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen["tenant"] = get_tenant_id()
        seen["role"] = get_user_role()

    monkeypatch.setattr(
        "services.ingestor.auth.decode_jwt_claims",
        lambda _token: {"tenant_id": "7", "sub": "admin-user"},
    )

    class _FakeEnforcer:
        def get_roles_for_user_in_domain(self, _sub: str, _domain: str) -> list[str]:
            return ["admin"]

    monkeypatch.setattr(
        "services.ingestor.auth.get_casbin_enforcer",
        lambda: _FakeEnforcer(),
    )

    await TenantMiddleware(app)(
        _scope([(b"authorization", b"Bearer valid-token"), (b"x-tenant-id", b"42")]),
        _receive,
        _send,
    )

    assert seen == {"tenant": 7, "role": "admin"}


@pytest.mark.parametrize("header", [b"invalid", b""])
async def test_invalid_or_missing_header_leaves_global_context(header: bytes) -> None:
    seen: list[int | None] = []

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen.append(get_tenant_id())

    headers = [(b"x-tenant-id", header)] if header else []
    await TenantMiddleware(app)(_scope(headers), _receive, _send)

    assert seen == [None]


async def test_invalid_bearer_token_falls_back_to_global_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int | None] = []

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen.append(get_tenant_id())

    def _raise(_token: str) -> dict[str, Any]:
        raise ValueError("invalid token")

    monkeypatch.setattr("services.ingestor.auth.decode_jwt_claims", _raise)

    await TenantMiddleware(app)(
        _scope([(b"authorization", b"Bearer invalid-token")]),
        _receive,
        _send,
    )

    assert seen == [None]


async def test_non_http_scope_is_passed_through() -> None:
    calls: list[str] = []

    async def app(scope: Scope, _receive: Receive, _send: Send) -> None:
        calls.append(scope["type"])

    await TenantMiddleware(app)({"type": "lifespan"}, _receive, _send)

    assert calls == ["lifespan"]
