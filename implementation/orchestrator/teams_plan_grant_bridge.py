"""Optional terminal-free plan receipt after existing Teams and JKD-001 gates.

Not a Teams ingress, identity source, or execution authority. Must be called only
with the verified result from TeamsApprovalFlow and the server-owned proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from datetime import datetime

from .approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from .approval_plan_scope import ApprovedPlanScope
from .teams_approval_flow import TeamsApprovalFlowResult


@dataclass(frozen=True, slots=True)
class ServerOwnedPlanProposal:
    approval_id: str
    organization_id: str
    client_id: str | None
    requester_id: str
    capability: str
    plan_fingerprint: str
    scope: ApprovedPlanScope


def record_verified_teams_plan_grant(*, result: TeamsApprovalFlowResult,
        proposal: ServerOwnedPlanProposal, ledger: PlanGrantLedger,
        decided_at: datetime) -> None:
    """Fail closed if verified Teams decision and JKD request mismatch proposal.

    Scope checks for downstream steps remain mandatory, as do new per-step JKD
    execution authority and other independent gates. Never accept card fields
    as proposal contents.
    """
    accepted = result.accepted_approval
    resumed = result.resumed_request
    if accepted.status != 'approved' or resumed is None or not getattr(resumed, 'authority_context_id', None):
        raise PermissionError('approved and freshly authorized Teams result required')
    if (accepted.approval_id != proposal.approval_id or
        accepted.organization_id != proposal.organization_id or
        accepted.client_id != proposal.client_id or
        accepted.requested_by != proposal.requester_id or
        accepted.capability != proposal.capability):
        raise PermissionError('approval does not match server-owned proposal')
    if (proposal.scope.organization_id != proposal.organization_id or
        not proposal.plan_fingerprint or not accepted.decided_by or
        accepted.decided_at.tzinfo is None or decided_at.tzinfo is None or
        accepted.decided_at != decided_at or
        accepted.expires_at.tzinfo is None or decided_at >= accepted.expires_at):
        raise PermissionError('invalid plan proposal scope')
    decision = VerifiedPlanDecision(
        approval_id=accepted.approval_id,
        approver_identity_id=accepted.decided_by,
        authenticated=True, authorized=True, approved=True,
        plan_fingerprint=proposal.plan_fingerprint,
        decided_at=decided_at)
    try:
        ledger.record(proposal.scope, decision)
    except sqlite3.IntegrityError:
        # Recovery may publish this same atomic human receipt while its original
        # HTTP callback is still finishing. This is not a replayed human vote.
        ledger.require_matching_decision(proposal.scope, decision)
