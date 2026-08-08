from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from .contracts import ExecutionContext, PermissionMode, permission_rank


class ExecutionContextRepository(Protocol):
    def get_context(self, context_id: str) -> ExecutionContext | None: ...
    def context_revocation(self, context_id: str) -> tuple[datetime, str] | None: ...


@dataclass(frozen=True, slots=True)
class ContextValidationRequest:
    context_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    capability: str
    requested_mode: PermissionMode


@dataclass(frozen=True, slots=True)
class ContextValidationResult:
    valid: bool
    reason_code: str
    context: ExecutionContext | None = None


@dataclass
class ExecutionContextValidator:
    contexts: ExecutionContextRepository
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def validate(self, request: ContextValidationRequest) -> ContextValidationResult:
        context = self.contexts.get_context(request.context_id)
        if context is None:
            return ContextValidationResult(False, "EXECUTION_CONTEXT_NOT_FOUND")

        revoked = self.contexts.context_revocation(request.context_id)
        if revoked is not None:
            return ContextValidationResult(False, "EXECUTION_CONTEXT_REVOKED", context)

        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("context validation clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        if now >= context.expires_at:
            return ContextValidationResult(False, "EXECUTION_CONTEXT_EXPIRED", context)

        exact = (
            context.correlation_id == request.correlation_id
            and context.principal_id == request.principal_id
            and context.organization_id == request.organization_id
            and context.client_id == request.client_id
            and context.capability == request.capability
        )
        if not exact:
            return ContextValidationResult(False, "EXECUTION_CONTEXT_SCOPE_MISMATCH", context)

        if permission_rank(request.requested_mode) > permission_rank(context.maximum_mode):
            return ContextValidationResult(False, "EXECUTION_CONTEXT_MODE_EXCEEDED", context)

        return ContextValidationResult(True, "EXECUTION_CONTEXT_VALID", context)
