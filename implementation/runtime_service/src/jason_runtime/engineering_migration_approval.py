"""Source-only approval issuance contract for the independent engineering cutover.

This adds NO second approval ledger, callback, or deployment controller.  The
approved UniversalPlanIssuer supplies the existing signed Teams challenge,
identity binding and policy checks.  The candidate is not registered or
executable in production, and no host state may be modified by this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from orchestrator.contracts import OrchestrationMode, OrchestrationRequest

CAPABILITY = "engineering.migration.activate"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED = frozenset({
    "candidate_sha", "rollback_sha", "reviewed_scope_sha256",
    "continuity_evidence_sha256", "migration_phase",
})
_PHASE = "independent_engineering_lanes"


class EngineeringMigrationApprovalError(PermissionError):
    """No signed Teams permission or migration execution rights are implied."""


def validate_exact_request(request: OrchestrationRequest) -> dict[str, str]:
    """Reject incomplete or unreviewed scope before contacting Teams."""
    if (
        request.organization_id != "aot"
        or request.client_id is not None
        or request.capability_name != CAPABILITY
        or request.capability_version != "1.0"
        or request.permission_mode != "execute"
        or request.requested_mode != "deterministic"
        or request.orchestration_mode is not OrchestrationMode.EXECUTE
        or request.approval_present
        or request.authority_allowed
        or set(request.arguments) != _ALLOWED
    ):
        raise EngineeringMigrationApprovalError("Engineering migration request scope invalid")
    args = request.arguments
    if any(not isinstance(args[k], str) for k in _ALLOWED):
        raise EngineeringMigrationApprovalError("Immutable migration arguments required")
    if not _SHA.fullmatch(args["candidate_sha"]) or not _SHA.fullmatch(args["rollback_sha"]):
        raise EngineeringMigrationApprovalError("Exact candidate and rollback SHAs required")
    if args["candidate_sha"] == args["rollback_sha"]:
        raise EngineeringMigrationApprovalError("Candidate cannot equal rollback")
    if not _DIGEST.fullmatch(args["reviewed_scope_sha256"]) or not _DIGEST.fullmatch(args["continuity_evidence_sha256"]):
        raise EngineeringMigrationApprovalError("Reviewed scope and continuity digests required")
    if args["migration_phase"] != _PHASE:
        raise EngineeringMigrationApprovalError("Unreviewed engineering migration phase")
    return {key: args[key] for key in sorted(_ALLOWED)}


@dataclass(frozen=True, slots=True)
class ExistingTeamsEngineeringMigrationIssuer:
    """Reuse the canonical issuer, never synthesize a Teams identity or decision."""
    issuer: Any

    def submit_for_authenticated_requester(
        self, *, request: OrchestrationRequest, verified_teams_identity: Any,
    ) -> dict:
        args = validate_exact_request(request)
        if verified_teams_identity is None:
            raise EngineeringMigrationApprovalError("Authenticated Teams requester required")
        return self.issuer.submit_plan(
            requests=(request,), identity=verified_teams_identity,
            title="Project Jason: approve exact independent engineering migration",
            summary=(
                "Engineering lanes only; preserve the original paused worker and production "
                "freeze. Candidate " + args["candidate_sha"]
                + "; rollback " + args["rollback_sha"]
                + "; scope SHA256 " + args["reviewed_scope_sha256"]
                + "; continuity SHA256 " + args["continuity_evidence_sha256"]
                + ". Approval is for this immutable reviewed migration only."
            ),
            production=True, ttl_seconds=900,
        )

    def submit_for_authorized_workload(
        self, *, request: OrchestrationRequest, verified_workload_principal: Any,
    ) -> dict:
        args = validate_exact_request(request)
        if verified_workload_principal is None:
            raise EngineeringMigrationApprovalError("Registered workload principal required")
        return self.issuer.submit_service_plan(
            requests=(request,), principal=verified_workload_principal,
            title="Project Jason: approve exact independent engineering migration",
            summary=(
                "Engineering lanes only; preserve paused controller and freeze. "
                "Candidate " + args["candidate_sha"]
                + "; rollback " + args["rollback_sha"]
                + "; reviewed scope SHA256 " + args["reviewed_scope_sha256"]
                + "; continuity SHA256 " + args["continuity_evidence_sha256"]
                + ". A signed Teams decision is required before native release."
            ),
            production=True, ttl_seconds=900,
        )
