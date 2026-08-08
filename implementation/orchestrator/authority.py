from __future__ import annotations

from dataclasses import dataclass

from kernel.identity_authority import (
    ContextValidationRequest,
    ExecutionContextValidator,
    PermissionMode,
)

from .contracts import OrchestrationRequest


@dataclass(frozen=True, slots=True)
class JKD001OrchestrationContextEnforcer:
    validator: ExecutionContextValidator

    def validate(self, request: OrchestrationRequest) -> str | None:
        if request.authority_context_id is None:
            return "AUTHORITY_CONTEXT_REQUIRED"
        try:
            mode = PermissionMode(request.requested_mode)
        except ValueError:
            return "AUTHORITY_CONTEXT_MODE_INVALID"
        result = self.validator.validate(
            ContextValidationRequest(
                context_id=request.authority_context_id,
                correlation_id=request.correlation_id,
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                capability=request.capability_name,
                requested_mode=mode,
            )
        )
        return None if result.valid else result.reason_code
