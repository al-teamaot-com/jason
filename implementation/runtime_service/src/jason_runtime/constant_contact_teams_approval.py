"""Bridge to Jason's *existing* signed Teams plan-grant ledger.

This is NOT a second approval database or a callback endpoint. It can only
verify a grant already published by the canonical verified Teams ingress,
bound to a server-owned proposal whose fingerprint equals the exact import
intent digest. The source-only adapter is not wired into production.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from orchestrator.approval_plan_scope import ProposedPlanStep
from orchestrator.approval_plan_grants import PlanGrantLedger
from connectors.constant_contact.import_authorization import ExactImportIntent, ImportAuthorizationError

IMPORT_CAPABILITY = "marketing.contact.import"


@dataclass(frozen=True)
class ExistingTeamsPlanGrantAdapter:
    ledger: PlanGrantLedger
    proposals: Any
    # Approval ID must originate from the server-owned import work record;
    # it must never be supplied by workbook/Teams-card arguments.
    server_owned_approval_id: str
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def require_exact_signed_approval(self, *,
                                      requester_id: str,
                                      intent: ExactImportIntent) -> None:
        if not self.server_owned_approval_id:
            raise ImportAuthorizationError("Server-owned Teams approval identity required")
        proposal = self.proposals.require(self.server_owned_approval_id)
        scope = proposal.scope
        if (proposal.approval_id != self.server_owned_approval_id
                or proposal.organization_id != "aot"
                or proposal.requester_id != requester_id
                or proposal.capability != IMPORT_CAPABILITY
                or scope.organization_id != "aot"
                or scope.allowed_capabilities != frozenset({IMPORT_CAPABILITY})
                or not scope.production_allowed
                or scope.allowed_clients
                or proposal.plan_fingerprint != intent.digest()):
            raise ImportAuthorizationError("Exact Teams import proposal binding mismatch")
        try:
            self.ledger.require_grant(
                ProposedPlanStep(
                    plan_id=scope.plan_id,
                    organization_id="aot",
                    policy_digest=scope.policy_digest,
                    capability=IMPORT_CAPABILITY,
                    client_id=None,
                    risk=scope.max_risk,
                    production=True,
                ),
                plan_fingerprint=proposal.plan_fingerprint,
                now=self.clock(),
            )
        except (PermissionError, ValueError):
            raise ImportAuthorizationError("Signed Teams import grant missing or expired") from None
