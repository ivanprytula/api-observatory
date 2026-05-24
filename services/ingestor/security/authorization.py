"""Central policy-as-code authorization decisions.

This module keeps authorization decisions in one place so route guards can
delegate to a single evaluator instead of hand-rolling checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AuthorizationInput:
    """Structured input for a policy authorization decision."""

    action: str
    principal_type: str
    principal_id: str | int | None = None
    tenant_id: int | None = None
    resource_tenant_id: int | None = None
    roles: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    required_roles: set[str] = field(default_factory=set)
    required_scopes: set[str] = field(default_factory=set)


@dataclass(slots=True)
class AuthorizationDecision:
    """Authorization outcome returned by the policy evaluator."""

    allow: bool
    policy_name: str
    reason: str


def evaluate_authorization(policy_input: AuthorizationInput) -> AuthorizationDecision:
    """Evaluate authorization using explicit deny-by-default rules.

    Admin roles or scopes bypass lower-level checks. Tenant mismatches are
    denied before evaluating role or scope membership.
    """
    if (
        policy_input.resource_tenant_id is not None
        and policy_input.tenant_id is not None
        and policy_input.resource_tenant_id != policy_input.tenant_id
    ):
        return AuthorizationDecision(
            allow=False,
            policy_name="tenant_isolation",
            reason="Tenant context does not match resource tenant",
        )

    if "admin" in policy_input.roles or "admin" in policy_input.scopes:
        return AuthorizationDecision(
            allow=True,
            policy_name="admin_bypass",
            reason="Admin principal bypassed fine-grained policy checks",
        )

    if policy_input.required_roles:
        if policy_input.required_roles & policy_input.roles:
            return AuthorizationDecision(
                allow=True,
                policy_name="role_membership",
                reason="Required role present on principal",
            )
        return AuthorizationDecision(
            allow=False,
            policy_name="role_membership",
            reason="Principal is missing the required role membership",
        )

    if policy_input.required_scopes:
        if policy_input.required_scopes.issubset(policy_input.scopes):
            return AuthorizationDecision(
                allow=True,
                policy_name="scope_membership",
                reason="Required scope present on principal",
            )
        return AuthorizationDecision(
            allow=False,
            policy_name="scope_membership",
            reason="Principal is missing the required scope membership",
        )

    return AuthorizationDecision(
        allow=False,
        policy_name="default_deny",
        reason="No explicit authorization policy matched the request",
    )
