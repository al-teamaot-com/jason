"""Runtime composition for governed Microsoft Teams approval responses.

This module only assembles existing trust boundaries. Microsoft authentication and
Teams interactions remain evidence/transport inputs. Provider-neutral approval
validation, JKD-001 re-authorization, and the Central Orchestrator remain the
authority path.
"""

from __future__ import annotations

from dataclasses import dataclass

from connectors.src.jason_connectors.approval_requests import ApprovalRequestService
from orchestrator.approval_audit import ApprovalAuditRecorder
from orchestrator.approvals import ApprovalResumeBridge
from orchestrator.teams_approval_flow import ApprovalAttentionSink, TeamsApprovalFlow, MicrosoftPrincipalVerifier

from .teams_approval_ingress import (
    MicrosoftIdentityBindingResolver,
    MicrosoftTenantBindingResolver,
    TeamsApprovalIngress,
)


@dataclass(frozen=True, slots=True)
class TeamsApprovalResponseRuntimeDependencies:
    """Explicit dependencies required to assemble the response path.

    Binding resolvers are deliberately separate from Microsoft token verification:
    a valid Microsoft identity is not automatically a Jason identity or approver.
    """

    token_verifier: MicrosoftPrincipalVerifier
    tenant_bindings: MicrosoftTenantBindingResolver
    identity_bindings: MicrosoftIdentityBindingResolver
    approval_service: ApprovalRequestService
    resume_bridge: ApprovalResumeBridge
    audit: ApprovalAuditRecorder
    attention_sink: ApprovalAttentionSink | None = None


def build_teams_approval_response_flow(
    *,
    dependencies: TeamsApprovalResponseRuntimeDependencies,
) -> TeamsApprovalFlow:
    """Compose the authenticated Teams response path without creating authority."""

    ingress = TeamsApprovalIngress(
        tenant_bindings=dependencies.tenant_bindings,
        identity_bindings=dependencies.identity_bindings,
    )
    return TeamsApprovalFlow(
        token_verifier=dependencies.token_verifier,
        ingress=ingress,
        approval_service=dependencies.approval_service,
        resume_bridge=dependencies.resume_bridge,
        audit=dependencies.audit,
        attention_sink=dependencies.attention_sink,
    )


def build_universal_teams_plan_approval_service(*, dependencies: TeamsApprovalResponseRuntimeDependencies,
        ledger_path: str):
    """Assemble shared bounded-plan grants over existing verified Teams ingress.

    Composition only: the caller must provide durable server-owned plan proposals,
    and all resumed work still goes through separate governed execution gates.
    """
    if not ledger_path or not ledger_path.strip():
        raise ValueError('durable approval plan ledger path required')
    from orchestrator.approval_plan_grants import PlanGrantLedger
    from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService
    return UniversalTeamsPlanApprovalService(
        teams_flow=build_teams_approval_response_flow(dependencies=dependencies),
        ledger=PlanGrantLedger(ledger_path),
    )
