"""Pure scope-conformance guard for a previously authenticated plan grant.

Not an approval issuer or an execution authority. The orchestrator must still
verify live identity, approvals, policy, independent gates and target evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class ApprovedPlanScope:
    plan_id: str
    organization_id: str
    policy_digest: str
    allowed_capabilities: frozenset[str]
    allowed_clients: frozenset[str]
    max_risk: int
    production_allowed: bool
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.plan_id or not self.organization_id or not self.policy_digest:
            raise ValueError('plan identity and policy digest are required')
        if not self.allowed_capabilities or self.max_risk < 0:
            raise ValueError('bounded capabilities and risk are required')
        if self.expires_at.tzinfo is None:
            raise ValueError('expiry must be timezone-aware')


@dataclass(frozen=True, slots=True)
class ProposedPlanStep:
    plan_id: str
    organization_id: str
    policy_digest: str
    capability: str
    client_id: str | None
    risk: int
    production: bool


def require_plan_scope(scope: ApprovedPlanScope, step: ProposedPlanStep, *, now: datetime) -> None:
    """Deny out-of-plan steps; passing does NOT grant permission to execute."""
    if now.tzinfo is None:
        raise ValueError('time must be timezone-aware')
    if now.astimezone(timezone.utc) >= scope.expires_at.astimezone(timezone.utc):
        raise PermissionError('plan authorization expired')
    if step.plan_id != scope.plan_id or step.organization_id != scope.organization_id:
        raise PermissionError('plan or tenant mismatch')
    if step.policy_digest != scope.policy_digest:
        raise PermissionError('approval policy changed')
    if step.capability not in scope.allowed_capabilities:
        raise PermissionError('capability outside approved plan')
    if step.risk < 0 or step.risk > scope.max_risk:
        raise PermissionError('risk exceeds approved ceiling')
    if step.client_id not in scope.allowed_clients and not (step.client_id is None and not scope.allowed_clients):
        raise PermissionError('client outside approved plan')
    if step.production and not scope.production_allowed:
        raise PermissionError('production not included in plan')
