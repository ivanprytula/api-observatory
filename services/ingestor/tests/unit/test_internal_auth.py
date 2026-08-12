from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from libs.platform.auth import (
    ServiceClaims,
    generate_internal_token,
    require_internal_auth,
    verify_internal_token,
)


_TEST_SECRET = "test-internal-secret-for-unit-tests-only"


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def set_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set INTERNAL_JWT_SECRET for all tests in this module."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _TEST_SECRET)


class TestGenerateInternalToken:
    def test_returns_string(self) -> None:
        token = generate_internal_token("ingestor")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_claims_are_correct(self) -> None:
        token = generate_internal_token("ingestor")
        payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert payload["iss"] == "api-observatory"
        assert payload["sub"] == "ingestor"
        assert "exp" in payload
        assert "iat" in payload

    def test_token_expires_in_60s(self) -> None:
        before = int(time.time())
        token = generate_internal_token("processor")
        payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        # Allow 2s clock skew
        assert payload["exp"] - before <= 62
        assert payload["exp"] - before >= 58

    def test_token_ttl_can_be_configured_but_stays_short_lived(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("INTERNAL_JWT_TTL_SECONDS", "120")
        before = int(time.time())
        token = generate_internal_token("processor")
        payload = jwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert payload["exp"] - before <= 122
        assert payload["exp"] - before >= 118


class TestVerifyInternalToken:
    def test_valid_token_returns_claims(self) -> None:
        token = generate_internal_token("dashboard")
        claims = verify_internal_token(token)
        assert isinstance(claims, ServiceClaims)
        assert claims.sub == "dashboard"
        assert claims.iss == "api-observatory"

    def test_expired_token_raises(self) -> None:
        # Generate a token with exp in the past
        payload = {
            "iss": "api-observatory",
            "sub": "ingestor",
            "iat": int(time.time()) - 120,
            "exp": int(time.time()) - 60,
        }
        token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_internal_token(token)

    def test_wrong_issuer_raises(self) -> None:
        payload = {
            "iss": "some-other-service",
            "sub": "ingestor",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            verify_internal_token(token)

    def test_wrong_secret_raises(self) -> None:
        token = generate_internal_token("ingestor")
        # Decode with a different secret should fail
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(token, "wrong-secret", algorithms=["HS256"])

    def test_tampered_token_raises(self) -> None:
        token = generate_internal_token("ingestor")
        # Flip a character in the signature
        tampered = token[:-4] + "XXXX"
        with pytest.raises(jwt.InvalidTokenError):
            verify_internal_token(tampered)

    def test_previous_internal_secret_is_accepted_during_rotation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        old_secret = "previous-internal-secret"
        monkeypatch.setenv("INTERNAL_JWT_SECRET_PREVIOUS", old_secret)
        payload = {
            "iss": "api-observatory",
            "sub": "ingestor",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        token = jwt.encode(payload, old_secret, algorithm="HS256")

        claims = verify_internal_token(token)

        assert claims.sub == "ingestor"


class TestRequireInternalAuth:
    @pytest.mark.asyncio
    async def test_valid_header_returns_claims(self) -> None:
        token = generate_internal_token("ingestor")
        claims = await require_internal_auth(f"Bearer {token}")
        assert claims.sub == "ingestor"

    @pytest.mark.asyncio
    async def test_missing_header_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_non_bearer_scheme_raises_401(self) -> None:
        token = generate_internal_token("ingestor")
        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(f"Basic {token}")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self) -> None:
        payload = {
            "iss": "api-observatory",
            "sub": "ingestor",
            "iat": int(time.time()) - 120,
            "exp": int(time.time()) - 60,
        }
        token = jwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(f"Bearer {token}")
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth("Bearer not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    async def test_mtls_enabled_rejects_missing_verified_header(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("INTERNAL_MTLS_ENABLED", "true")
        monkeypatch.setenv(
            "INTERNAL_MTLS_ALLOWED_SUBJECTS",
            "spiffe://cluster.local/ns/default/sa/ingestor",
        )
        token = generate_internal_token("ingestor")

        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(f"Bearer {token}")

        assert exc_info.value.status_code == 401
        assert "client certificate" in exc_info.value.detail.lower()

    async def test_mtls_enabled_rejects_unknown_subject(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("INTERNAL_MTLS_ENABLED", "true")
        monkeypatch.setenv(
            "INTERNAL_MTLS_ALLOWED_SUBJECTS",
            "spiffe://cluster.local/ns/default/sa/ingestor",
        )
        token = generate_internal_token("ingestor")

        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(
                f"Bearer {token}",
                client_cert_verified="SUCCESS",
                client_cert_subject="spiffe://cluster.local/ns/default/sa/other-service",
            )

        assert exc_info.value.status_code == 403

    async def test_mtls_enabled_accepts_allowed_subject(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        allowed_subject = "spiffe://cluster.local/ns/default/sa/ingestor"
        monkeypatch.setenv("INTERNAL_MTLS_ENABLED", "true")
        monkeypatch.setenv("INTERNAL_MTLS_ALLOWED_SUBJECTS", allowed_subject)
        token = generate_internal_token("ingestor")

        claims = await require_internal_auth(
            f"Bearer {token}",
            client_cert_verified="SUCCESS",
            client_cert_subject=allowed_subject,
        )

        assert claims.sub == "ingestor"
        assert claims.mtls_subject == allowed_subject

    async def test_mtls_enabled_without_allowlist_returns_503(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("INTERNAL_MTLS_ENABLED", "true")
        monkeypatch.delenv("INTERNAL_MTLS_ALLOWED_SUBJECTS", raising=False)
        token = generate_internal_token("ingestor")

        with pytest.raises(HTTPException) as exc_info:
            await require_internal_auth(
                f"Bearer {token}",
                client_cert_verified="SUCCESS",
                client_cert_subject="spiffe://cluster.local/ns/default/sa/ingestor",
            )

        assert exc_info.value.status_code == 503
