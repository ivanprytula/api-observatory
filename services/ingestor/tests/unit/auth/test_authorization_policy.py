"""Unit tests for the central policy-as-code authorization evaluator."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.ingestor.auth import require_roles
from services.ingestor.security.authorization import (
    AuthorizationInput,
    evaluate_authorization,
)


class TestAuthorizationPolicy:
    """Focused coverage for OPA-style authorization decisions."""

    def test_admin_scope_bypasses_scope_checks(self) -> None:
        decision = evaluate_authorization(
            AuthorizationInput(
                action="api_key_scope_guard",
                principal_type="api_key",
                scopes={"admin"},
                required_scopes={"records:write"},
            )
        )

        assert decision.allow is True
        assert decision.policy_name == "admin_bypass"

    def test_missing_scope_denies_by_policy(self) -> None:
        decision = evaluate_authorization(
            AuthorizationInput(
                action="api_key_scope_guard",
                principal_type="api_key",
                scopes={"records:read"},
                required_scopes={"records:write"},
            )
        )

        assert decision.allow is False
        assert decision.policy_name == "scope_membership"

    def test_tenant_mismatch_denies_before_role_check(self) -> None:
        decision = evaluate_authorization(
            AuthorizationInput(
                action="role_guard",
                principal_type="user",
                tenant_id=7,
                resource_tenant_id=9,
                roles={"tenant_admin"},
                required_roles={"tenant_admin"},
            )
        )

        assert decision.allow is False
        assert decision.policy_name == "tenant_isolation"

    def test_require_roles_uses_policy_engine(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            require_roles(
                {"tenant_admin"},
                {"tenant_admin"},
                tenant_id=1,
                resource_tenant_id=2,
            )

        assert exc_info.value.status_code == 403
