"""Exact-action Constant Contact approval using Jason's existing verified plan grant.

No approval is created or inferred here. The canonical issuer, persisted plan
requests, authenticated callback and grant ledger remain authoritative. Teams
is a supported transport, not a mandatory special approval authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from connectors.constant_contact.import_authorization import (
    ExactImportIntent, ImportAuthorizationError,
)
from orchestrator.approval_plan_scope import ProposedPlanStep
from orchestrator.approval_plan_grants import PlanGrantLedger

IMPORT_CAPABILITY = "marketing.contact.import"


@dataclass(frozen=True)
class ExistingVerifiedPlanGrantAdapter:
    ledger: PlanGrantLedger
    proposals: Any
    requests: Any
    # This must be sourced from Jason's trusted persisted work record, never
    # from workbook data, a user-supplied card field, or a chat message.
    server_owned_approval_id: str
    server_owned_work_id: str
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def require_exact_signed_approval(
        self, *, requester_id: str, intent: ExactImportIntent,
    ) -> None:
        if not self.server_owned_approval_id.startswith("planapproval-"):
            raise ImportAuthorizationError("Trusted plan approval reference required")
        try:
            proposal = self.proposals.require(self.server_owned_approval_id)
            self.requests.verify_proposal(proposal)
            steps = self.requests.steps(self.server_owned_approval_id)
        except (PermissionError, LookupError, ValueError, KeyError, TypeError):
            raise ImportAuthorizationError("Verified server-owned import proposal missing") from None

        if len(steps) != 1:
            raise ImportAuthorizationError("Constant Contact import requires one exact approved step")
        original = steps[0]
        scope = proposal.scope
        approved_material = {
            "work_id": self.server_owned_work_id,
            "intent_digest": intent.digest(),
            "account_binding_sha256": intent.account_binding_sha256,
            "specification_sha256": intent.specification_sha256,
            "preview_digest": intent.preview_digest,
            "suppression_receipt_sha256": intent.suppression_receipt_sha256,
            "list_ids": list(intent.list_ids),
            "contact_count": intent.contact_count,
        }
        if (
            not self.server_owned_work_id
            or proposal.approval_id != self.server_owned_approval_id
            or proposal.organization_id != "aot"
            or proposal.requester_id != requester_id
            or proposal.capability != IMPORT_CAPABILITY
            or proposal.client_id is not None
            or scope.organization_id != "aot"
            or scope.allowed_capabilities != frozenset({IMPORT_CAPABILITY})
            or not scope.production_allowed
            or scope.allowed_clients
            or original.principal_id != requester_id
            or original.organization_id != "aot"
            or original.client_id is not None
            or original.capability_name != IMPORT_CAPABILITY
            or original.permission_mode != "execute"
            or original.arguments != approved_material
        ):
            raise ImportAuthorizationError("Exact approved Constant Contact import material mismatch")

        # The canonical PlanRequestRepository verified its own SHA over the
        # original request and entire scope. The universal plan fingerprint is
        # intentionally NOT the same hash as this import's intent digest.
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
            receipt = self.ledger.decision_receipt(self.server_owned_approval_id)
            if (
                not receipt
                or receipt.get("approval_id") != proposal.approval_id
                or receipt.get("plan_fingerprint") != proposal.plan_fingerprint
                or not receipt.get("approver_identity_id")
                or receipt.get("revoked_at") is not None
            ):
                raise PermissionError("Missing verified decision receipt")
        except (PermissionError, ValueError, TypeError):
            raise ImportAuthorizationError("Verified import approval missing, expired or revoked") from None


# Compatibility for source-only tests/callers; deliberately no Teams-only
# transport requirement. Production install remains separately governed.
ExistingTeamsPlanGrantAdapter = ExistingVerifiedPlanGrantAdapter
