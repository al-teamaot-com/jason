"""Autonomous service-principal authority boundary for Jason.

This module creates governed orchestration requests for autonomous work without
impersonating an interactive technician. It does not call providers and it does
not grant authority. The service identity and exact capability grants must
already exist in JKD-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol
from uuid import uuid4

from kernel.capabilities import CapabilityRegistryService
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    PermissionMode,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore


class ApprovalWriter(Protocol):
    def put(self, record: ApprovalRecord) -> None: ...


@dataclass(frozen=True)
class AutonomousPrincipal:
    principal_id: str = "jason-autonomy-worker"
    organization_id: str = "aot"
    authentication_assurance: str = "workload_identity"


@dataclass(frozen=True)
class StandingPolicyAuthorization:
    playbook_id: str
    playbook_version: str
    policy_id: str
    promotion_approval_id: str

    def __post_init__(self) -> None:
        for name, value in {
            "playbook_id": self.playbook_id,
            "playbook_version": self.playbook_version,
            "policy_id": self.policy_id,
            "promotion_approval_id": self.promotion_approval_id,
        }.items():
            if not str(value).strip():
                raise ValueError(f"{name} must be non-empty")


class AutonomousAuthorityError(PermissionError):
    pass


class AutonomousRequestFactory:
    """Create one exact service-principal orchestration request.

    Approval-required mutations may proceed only when an explicitly approved
    standing playbook policy is supplied. A short-lived approval reservation is
    then created for the exact normalized action intent; the Central Orchestrator
    remains responsible for concrete execution-plan binding and single-use
    consumption.
    """

    def __init__(
        self,
        *,
        principal: AutonomousPrincipal,
        authority: IdentityAuthorityService,
        capabilities: CapabilityRegistryService,
        approvals: ApprovalWriter,
        execution_ledger: SQLiteGovernedExecutionLedger,
        promotion_store: SQLitePlaybookAutonomyApprovalStore,
    ) -> None:
        self.principal = principal
        self.authority = authority
        self.capabilities = capabilities
        self.approvals = approvals
        self.execution_ledger = execution_ledger
        self.promotion_store = promotion_store

    def build_observe(
        self,
        *,
        capability_name: str,
        arguments: Mapping[str, Any],
        client_id: str | None,
        correlation_id: str | None = None,
    ) -> OrchestrationRequest:
        """Build one JKD-001-authorized observe request for the workload identity."""

        capability = self.capabilities.get_current(
            capability_name=capability_name,
            allow_pilot=True,
        )
        execution_id = f"exec_autonomy_read_{uuid4().hex}"
        correlation = correlation_id or f"corr_autonomy_read_{uuid4().hex}"
        decision = self.authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation,
                principal_id=self.principal.principal_id,
                organization_id=self.principal.organization_id,
                client_id=client_id,
                capability=capability_name,
                requested_mode=PermissionMode.OBSERVE,
                authentication_assurance=self.principal.authentication_assurance,
            )
        )
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise AutonomousAuthorityError(
                "autonomous principal is not authorized to observe: "
                + ",".join(decision.reason_codes)
            )
        context = decision.execution_context
        if context is None:
            raise AutonomousAuthorityError("authority context missing")
        if capability.approval.required:
            raise AutonomousAuthorityError(
                "observe path refuses capabilities that require per-call approval"
            )

        return OrchestrationRequest(
            execution_id=execution_id,
            correlation_id=correlation,
            principal_id=self.principal.principal_id,
            organization_id=self.principal.organization_id,
            client_id=client_id,
            capability_name=capability_name,
            capability_version=capability.version,
            requested_mode="deterministic",
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=False,
            risk=capability.risk_level.value,
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=False,
                retention_allowed=False,
            ),
            budget=ExecutionBudget(
                maximum_estimated_cost=Decimal("1.00"),
                maximum_attempts=1,
            ),
            arguments=dict(arguments),
            requester_kind="service",
            principal_attributes={"workload": self.principal.principal_id},
            permission_mode="observe",
            policy_ids=("autonomous-shadow-read-v1",),
            authority_context_id=context.context_id,
            allow_pilot_capability=True,
            allow_pilot_provider=True,
        )

    def build(
        self,
        *,
        capability_name: str,
        arguments: Mapping[str, Any],
        client_id: str | None,
        standing_policy: StandingPolicyAuthorization | None = None,
        correlation_id: str | None = None,
    ) -> OrchestrationRequest:
        capability = self.capabilities.get_current(
            capability_name=capability_name,
            allow_pilot=True,
        )
        execution_id = f"exec_autonomy_{uuid4().hex}"
        correlation = correlation_id or f"corr_autonomy_{uuid4().hex}"

        initial = self.authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation,
                principal_id=self.principal.principal_id,
                organization_id=self.principal.organization_id,
                client_id=client_id,
                capability=capability_name,
                requested_mode=PermissionMode.EXECUTE,
                authentication_assurance=self.principal.authentication_assurance,
            )
        )

        approval_id: str | None = None
        idempotency_key: str | None = None
        approval_present = False
        decision = initial

        if initial.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
            if standing_policy is None:
                raise AutonomousAuthorityError(
                    "approval-required capability has no approved autonomous playbook policy"
                )
            promotion = self.promotion_store.get(standing_policy.promotion_approval_id)
            if promotion is None or not promotion.authorizes(
                playbook_id=standing_policy.playbook_id,
                playbook_version=standing_policy.playbook_version,
                policy_id=standing_policy.policy_id,
                capability=capability_name,
            ):
                raise AutonomousAuthorityError(
                    "playbook standing policy lacks exact durable owner promotion authority"
                )
            reservation = self.execution_ledger.reserve_approval(
                principal_id=self.principal.principal_id,
                organization_id=self.principal.organization_id,
                client_id=client_id,
                capability_name=capability_name,
                arguments=dict(arguments),
                request_id=execution_id,
                ttl_seconds=300,
            )
            approval_id = reservation.approval_id
            idempotency_key = reservation.idempotency_key
            if reservation.created:
                self.approvals.put(
                    ApprovalRecord(
                        approval_id=approval_id,
                        request_id=reservation.request_id,
                        capability=capability_name,
                        organization_id=self.principal.organization_id,
                        client_id=client_id,
                        requested_by=self.principal.principal_id,
                        status="approved",
                        decided_by=(
                            f"policy:{standing_policy.policy_id}:"
                            f"{standing_policy.playbook_id}@{standing_policy.playbook_version}"
                        ),
                        decided_at=datetime.now(timezone.utc),
                        expires_at=reservation.expires_at,
                    )
                )
            decision = self.authority.evaluate(
                AuthorityRequest(
                    request_id=reservation.request_id,
                    correlation_id=correlation,
                    principal_id=self.principal.principal_id,
                    organization_id=self.principal.organization_id,
                    client_id=client_id,
                    capability=capability_name,
                    requested_mode=PermissionMode.EXECUTE,
                    authentication_assurance=self.principal.authentication_assurance,
                    approval_id=approval_id,
                )
            )
            approval_present = True

        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise AutonomousAuthorityError(
                "autonomous principal is not authorized: "
                + ",".join(decision.reason_codes)
            )
        context = decision.execution_context
        if context is None:
            raise AutonomousAuthorityError("authority context missing")

        if capability.approval.required and not approval_present:
            raise AutonomousAuthorityError(
                "capability requires approval and no exact standing-policy approval was created"
            )

        policy_ids = ["autonomous-governance-v1"]
        if standing_policy is not None:
            policy_ids.append(standing_policy.policy_id)
            policy_ids.append(
                f"playbook:{standing_policy.playbook_id}@{standing_policy.playbook_version}"
            )

        return OrchestrationRequest(
            execution_id=execution_id,
            correlation_id=correlation,
            principal_id=self.principal.principal_id,
            organization_id=self.principal.organization_id,
            client_id=client_id,
            capability_name=capability_name,
            capability_version=capability.version,
            requested_mode="deterministic",
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=approval_present,
            risk=capability.risk_level.value,
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=False,
                retention_allowed=False,
            ),
            budget=ExecutionBudget(
                maximum_estimated_cost=Decimal("1.00"),
                maximum_attempts=min(1, capability.maximum_attempts),
            ),
            arguments=dict(arguments),
            requester_kind="service",
            principal_attributes={
                "workload": "jason-autonomy-worker",
                "playbook": standing_policy.playbook_id if standing_policy else "none",
            },
            permission_mode="execute",
            policy_ids=tuple(policy_ids),
            authority_context_id=context.context_id,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            allow_pilot_capability=True,
            allow_pilot_provider=True,
        )
