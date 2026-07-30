from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MutationPolicy:
    capability: str
    risk: RiskLevel
    requires_approval: bool = True
    requires_reason: bool = True
    supports_dry_run: bool = True
    idempotency_required: bool = True
    allowed_modes: frozenset[str] = frozenset({"propose", "execute"})


@dataclass(frozen=True)
class ApprovalGrant:
    approval_id: str
    capability: str
    principal_id: str
    organization_id: str
    client_id: str | None
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    argument_digest: str
    single_use: bool = True

    def is_valid_for(self, context: ConnectorContext, argument_digest: str) -> bool:
        now = datetime.now(timezone.utc)
        return (
            self.capability == context.capability
            and self.principal_id == context.principal_id
            and self.organization_id == context.organization_id
            and self.client_id == context.client_id
            and self.argument_digest == argument_digest
            and self.approved_at <= now < self.expires_at
        )


class ApprovalResolver(Protocol):
    def resolve(self, approval_id: str, context: ConnectorContext) -> ApprovalGrant: ...

    def consume(self, approval_id: str, context: ConnectorContext) -> None: ...


class IdempotencyStore(Protocol):
    def reserve(self, key: str, context: ConnectorContext) -> bool: ...

    def complete(self, key: str, context: ConnectorContext, result: Mapping[str, Any]) -> None: ...

    def release(self, key: str, context: ConnectorContext) -> None: ...


@dataclass(frozen=True)
class MutationPlan:
    capability: str
    provider: str
    risk: RiskLevel
    target: Mapping[str, Any]
    proposed_changes: Mapping[str, Any]
    preconditions: tuple[str, ...] = ()
    rollback_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class MutationExecutor(Protocol):
    def execute_mutation(self, request: ConnectorRequest, plan: MutationPlan) -> ConnectorResult: ...


def require_mutation_authority(
    request: ConnectorRequest,
    policy: MutationPolicy,
    *,
    argument_digest: str,
    approval_resolver: ApprovalResolver | None,
    audit: AuditSink,
) -> ApprovalGrant | None:
    if request.context.capability != policy.capability:
        raise ConnectorAuthorizationError("Mutation policy does not match requested capability.")
    if request.context.mode not in policy.allowed_modes:
        raise ConnectorAuthorizationError("Write capability requires propose or execute mode.")

    reason = request.arguments.get("reason")
    if policy.requires_reason and (not isinstance(reason, str) or not reason.strip()):
        raise ConnectorAuthorizationError("A human-readable business reason is required.")

    if request.context.mode == "propose":
        return None

    if policy.idempotency_required:
        key = request.arguments.get("idempotency_key")
        if not isinstance(key, str) or not key.strip():
            raise ConnectorAuthorizationError("An idempotency key is required for execution.")

    if not policy.requires_approval:
        return None
    if approval_resolver is None:
        raise ConnectorAuthorizationError("Approval service is not configured.")

    approval_id = request.arguments.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ConnectorAuthorizationError("An approval is required for execution.")

    grant = approval_resolver.resolve(approval_id, request.context)
    if not grant.is_valid_for(request.context, argument_digest):
        audit.record("connector.mutation.approval_rejected", request.context, {"approval_id": approval_id})
        raise ConnectorAuthorizationError("Approval is invalid, expired, or does not match this change.")
    return grant
