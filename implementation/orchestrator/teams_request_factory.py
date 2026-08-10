from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    PermissionMode,
)

from .contracts import OrchestrationMode, OrchestrationRequest
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
)


class ConversationAuthorityError(PermissionError):
    """Safe authority failure raised before conversational work reaches execution."""

    def __init__(self, code: str, reason_codes: tuple[str, ...]) -> None:
        self.code = code
        self.reason_codes = reason_codes
        super().__init__(code)


class ConversationApprovalRequired(ConversationAuthorityError):
    pass


@dataclass(frozen=True, slots=True)
class GovernedTeamsOrchestrationRequestFactory:
    """Convert a bound Teams intent into a JKD-001-authorized orchestration request.

    The factory never trusts Teams/OpenClaw to assert authority. It asks Jason's
    Identity Authority for the requested canonical capability and permission mode,
    requires a fresh execution context, and preserves that context into the Central
    Orchestrator. Provider execution strategy remains separate from human authority.
    """

    authority: IdentityAuthorityService
    data_handling: DataHandlingPolicy = DataHandlingPolicy(
        classification="internal",
        hosted_processing_allowed=False,
        retention_allowed=False,
    )
    budget: ExecutionBudget = ExecutionBudget(maximum_estimated_cost=Decimal("0"))
    policy_ids: tuple[str, ...] = ("teams-conversation-read-v1",)
    execution_id_factory: Callable[[], str] = lambda: f"exec_{uuid4().hex}"
    correlation_id_factory: Callable[[], str] = lambda: f"corr_{uuid4().hex}"

    def build(
        self,
        *,
        principal: BoundConversationPrincipal,
        intent: ConversationIntent,
        identity: TeamsConversationPrincipalEvidence,
    ) -> OrchestrationRequest:
        execution_id = self.execution_id_factory()
        correlation_id = self.correlation_id_factory()

        try:
            permission_mode = PermissionMode(intent.permission_mode)
        except ValueError as error:
            raise ConversationAuthorityError(
                "AUTHORITY_MODE_INVALID",
                ("AUTHORITY_MODE_INVALID",),
            ) from error

        decision = self.authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation_id,
                principal_id=principal.principal_id,
                organization_id=principal.organization_id,
                client_id=principal.client_id,
                capability=intent.capability_name,
                requested_mode=permission_mode,
                authentication_assurance=identity.authentication_assurance,
            )
        )

        if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
            raise ConversationApprovalRequired(
                "APPROVAL_REQUIRED",
                decision.reason_codes,
            )

        # Do not silently downgrade ALLOWED_LIMITED. The human requested a specific
        # permission mode, and only an exact allowed context may become executable.
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise ConversationAuthorityError(
                "AUTHORITY_DENIED",
                decision.reason_codes,
            )

        context = decision.execution_context
        if context is None:
            raise ConversationAuthorityError(
                "AUTHORITY_CONTEXT_MISSING",
                ("AUTHORITY_CONTEXT_MISSING",),
            )

        return OrchestrationRequest(
            execution_id=execution_id,
            correlation_id=correlation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            capability_version=intent.capability_version,
            requested_mode=intent.execution_mode,
            permission_mode=intent.permission_mode,
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=context.approval_required,
            risk=intent.risk,
            data_handling=self.data_handling,
            budget=self.budget,
            arguments=dict(intent.arguments),
            requester_kind="human",
            policy_ids=self.policy_ids,
            authority_context_id=context.context_id,
        )
