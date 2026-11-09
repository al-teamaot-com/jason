"""Read-only validation of a previously signed Teams engineering migration plan.

The existing signed Teams gateway, original approval repository and append-only
PlanGrantLedger MUST already have accepted the authentic owner decision. This
verifier only binds that receipt to immutable stored request material. It does
not install units, lift pauses, invoke a release or grant native PMV3 authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.approval_plan_scope import ProposedPlanStep
from orchestrator.engineering_migration_capability import ENGINEERING_MIGRATION_ACTIVATE
from orchestrator.teams_plan_request_repository import plan_fingerprint

from .mobile_release_approval import read_mobile_release_policy
from .engineering_migration_approval import (
    EngineeringMigrationApprovalError, validate_exact_request,
)


@dataclass(frozen=True, slots=True)
class VerifiedMigrationPlan:
    """Advisory release-admission evidence, NOT a permission to deploy."""
    approval_id: str
    candidate_sha: str
    rollback_sha: str
    reviewed_scope_sha256: str
    continuity_evidence_sha256: str
    signed_plan_fingerprint: str
    native_release_authorized: bool = False


def require_signed_migration_grant(
    *, approval_id: str, proposals: Any, requests: Any,
    grants: Any, now: datetime, protected_approver_policy_path: Path,
    active_identity_bindings: Any,
) -> VerifiedMigrationPlan:
    if not isinstance(approval_id, str) or not approval_id.startswith("planapproval-"):
        raise EngineeringMigrationApprovalError("Original Teams plan approval identity required")
    if now.tzinfo is None:
        raise EngineeringMigrationApprovalError("Trusted aware time required")
    try:
        # Read only the native host-owned 0600 V4 policy; no caller-controlled
        # approver identity string and no regular-user recipient fallback.
        policy = read_mobile_release_policy(Path(protected_approver_policy_path))
        if policy.schema_version != "4.0" or policy.admin_approver_binding is None:
            raise EngineeringMigrationApprovalError("Privileged V4 release identity policy required")
        tenant_id, object_id = policy.admin_approver_binding
        binding = active_identity_bindings.find(
            microsoft_tenant_id=tenant_id, microsoft_object_id=object_id,
        )
        if (binding is None or binding.status != "active"
                or not isinstance(binding.jason_identity_id, str)
                or not binding.jason_identity_id):
            raise EngineeringMigrationApprovalError("Privileged Entra identity binding unavailable")
        privileged_approver_identity_id = binding.jason_identity_id
        proposal = proposals.require(approval_id)
        requests.verify_proposal(proposal)
        stored = requests.steps(approval_id)
        scope = proposal.scope
        if (
            len(stored) != 1
            or proposal.approval_id != approval_id
            or proposal.organization_id != "aot"
            or proposal.client_id is not None
            or proposal.capability != ENGINEERING_MIGRATION_ACTIVATE
            or scope.organization_id != "aot"
            or scope.allowed_capabilities != frozenset({ENGINEERING_MIGRATION_ACTIVATE})
            or scope.allowed_clients
            or scope.max_risk != 3
            or not scope.production_allowed
            or proposal.requester_id != stored[0].principal_id
            or proposal.plan_fingerprint != plan_fingerprint(stored, scope)
        ):
            raise EngineeringMigrationApprovalError("Signed migration plan binding mismatch")
        args = validate_exact_request(stored[0])
        grants.require_grant(
            ProposedPlanStep(
                plan_id=scope.plan_id,
                organization_id="aot",
                policy_digest=scope.policy_digest,
                capability=ENGINEERING_MIGRATION_ACTIVATE,
                client_id=None,
                risk=3,
                production=True,
            ),
            plan_fingerprint=proposal.plan_fingerprint,
            now=now,
        )
        receipt = grants.decision_receipt(approval_id)
        if (
            not isinstance(receipt, dict)
            or receipt.get("approval_id") != approval_id
            or receipt.get("plan_id") != scope.plan_id
            or receipt.get("plan_fingerprint") != proposal.plan_fingerprint
            or receipt.get("revoked_at") is not None
            or receipt.get("approver_identity_id") != privileged_approver_identity_id
        ):
            raise EngineeringMigrationApprovalError("Original signed Teams decision unavailable")
    except EngineeringMigrationApprovalError:
        raise
    except (PermissionError, ValueError, KeyError, TypeError, AttributeError):
        raise EngineeringMigrationApprovalError("Teams migration approval unverified") from None
    return VerifiedMigrationPlan(
        approval_id=approval_id,
        candidate_sha=args["candidate_sha"],
        rollback_sha=args["rollback_sha"],
        reviewed_scope_sha256=args["reviewed_scope_sha256"],
        continuity_evidence_sha256=args["continuity_evidence_sha256"],
        signed_plan_fingerprint=proposal.plan_fingerprint,
    )
