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
from orchestrator.teams_approval_flow import TeamsApprovalFlow

from .teams_approval_ingress import (
    MicrosoftIdentityBindingResolver,
    MicrosoftTenantBindingResolver,
    TeamsApprovalIngress,
)
from .microsoft_token_verification import MicrosoftPrincipalVerifier


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
    )
