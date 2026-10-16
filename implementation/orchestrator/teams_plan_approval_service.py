"""Composition entrypoint for universal plan decisions over verified Teams ingress.

This is a non-executing integration boundary. TeamsApprovalFlow performs Entra,
provider-neutral, JKD-001 and mandatory audit checks. The plan ledger records
only an affirmative outcome bound to a server-owned plan proposal. Execution
remains exclusively under the Central Orchestrator's independent step authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .approval_plan_grants import PlanGrantLedger
from .teams_approval_flow import TeamsApprovalFlow, TeamsApprovalFlowResult
from .teams_plan_grant_bridge import ServerOwnedPlanProposal, record_verified_teams_plan_grant
from .contracts import OrchestrationRequest


@dataclass(frozen=True, slots=True)
class UniversalTeamsPlanApprovalService:
    teams_flow: TeamsApprovalFlow
    ledger: PlanGrantLedger

    def handle_response(
        self, *, token: str, payload: Mapping[str, str],
        original_request: OrchestrationRequest,
        proposal: ServerOwnedPlanProposal,
        decided_at: datetime, now: datetime | None = None,
    ) -> TeamsApprovalFlowResult:
        if proposal.approval_id != payload.get('approval_id'):
            raise PermissionError('proposal does not match Teams approval request')
        if proposal.organization_id != original_request.organization_id or \
                proposal.client_id != original_request.client_id or \
                proposal.requester_id != original_request.principal_id or \
                proposal.capability != original_request.capability_name:
            raise PermissionError('proposal does not match original governed request')
        result = self.teams_flow.handle_response(
            token=token, payload=payload, original_request=original_request,
            decided_at=decided_at, now=now)
        if result.accepted_approval.status == 'approved':
            record_verified_teams_plan_grant(
                result=result, proposal=proposal, ledger=self.ledger,
                decided_at=result.accepted_approval.decided_at)
        return result
