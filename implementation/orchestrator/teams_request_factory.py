from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Protocol
from uuid import uuid4

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    ApprovalRecord,
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


class ApprovalWriter(Protocol):
    def put(self, record: ApprovalRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class GovernedTeamsOrchestrationRequestFactory:
    """Convert a bound Teams intent into a JKD-001-authorized orchestration request.

    The factory never trusts Teams/OpenClaw to assert authority. It asks Jason's
    Identity Authority for the requested canonical capability and permission mode,
    requires a fresh execution context, and preserves that context into the Central
    Orchestrator. Provider execution strategy remains separate from human authority.

    A capability may explicitly declare that an authenticated imperative conversation
    turn is itself the per-execution approval evidence. That policy is capability data,
    not a transport privilege: the requester must still possess matching JKD-001
    authority, a formal ApprovalRecord is persisted, and authority is re-evaluated
    before execution.
    """

    authority: IdentityAuthorityService
    capabilities: CapabilityRegistryService | None = None
    approvals: ApprovalWriter | None = None
    data_handling: DataHandlingPolicy = DataHandlingPolicy(
        classification="internal",
        hosted_processing_allowed=False,
        retention_allowed=False,
    )
    budget: ExecutionBudget = ExecutionBudget(maximum_estimated_cost=Decimal("1.00"), maximum_attempts=1)
    policy_ids: tuple[str, ...] = ("teams-conversation-v1",)
    execution_id_factory: Callable[[], str] = lambda: f"exec_{uuid4().hex}"
    correlation_id_factory: Callable[[], str] = lambda: f"corr_{uuid4().hex}"
    idempotency_key_factory: Callable[[], str] = lambda: f"idem_{uuid4().hex}"
    approval_id_factory: Callable[[], str] = lambda: f"approval_{uuid4().hex}"
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

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

        capability = None
        if self.capabilities is not None:
            try:
                capability = self.capabilities.get_current(
                    capability_name=intent.capability_name,
                    allow_pilot=True,
                )
            except (KeyError, LookupError, ValueError):
                capability = None

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

        approval_present = False
        if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
            if not self._authenticated_imperative_may_approve(capability, intent):
                raise ConversationApprovalRequired(
                    "APPROVAL_REQUIRED",
                    decision.reason_codes,
                )
            if self.approvals is None:
                raise ConversationApprovalRequired(
                    "APPROVAL_REQUIRED",
                    decision.reason_codes,
                )

            now = self._now()
            approval_id = self.approval_id_factory()
            self.approvals.put(
                ApprovalRecord(
                    approval_id=approval_id,
                    request_id=execution_id,
                    capability=intent.capability_name,
                    organization_id=principal.organization_id,
                    client_id=principal.client_id,
                    requested_by=principal.principal_id,
                    status="approved",
                    decided_by=principal.principal_id,
                    decided_at=now,
                    expires_at=now + timedelta(minutes=5),
                )
            )
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
                    approval_id=approval_id,
                )
            )
            approval_present = True

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

        is_pilot = bool(
            capability is not None
            and capability.lifecycle_status is CapabilityLifecycle.PILOT
        )
        idempotency_key = None
        if capability is not None and capability.idempotency_key_required:
            idempotency_key = self.idempotency_key_factory()

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
            approval_present=approval_present or context.approval_required,
            risk=intent.risk,
            data_handling=self.data_handling,
            budget=self.budget,
            arguments=dict(intent.arguments),
            requester_kind="human",
            policy_ids=self.policy_ids,
            authority_context_id=context.context_id,
            allow_pilot_capability=is_pilot,
            allow_pilot_provider=is_pilot,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _authenticated_imperative_may_approve(capability, intent: ConversationIntent) -> bool:
        if capability is None or intent.permission_mode != "execute":
            return False
        return (
            str(
                capability.metadata.get(
                    "conversation_authenticated_imperative_is_approval",
                    "",
                )
            ).lower()
            == "true"
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Teams request factory clock must be timezone-aware")
        return value.astimezone(timezone.utc)
