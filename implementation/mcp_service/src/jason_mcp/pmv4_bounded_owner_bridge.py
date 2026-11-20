"""Authenticated Jason MCP -> one immutable Owner PMv4 objective (source-only).

No published MCP action or production signer is enabled by this module.
The same existing Microsoft Entra identity/Owner consent, protected main,
Ed25519 Owner signer and existing PlanGrantLedger are used. Unlike a per-step
approval, the human affirms the FULL ordered, hashed and rollback-pinned plan
only once; a recovered identical authenticated receipt never re-prompts.
No root request, standing authority, Teams approval or provider action.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kernel.pmv4_plan_child_proof import (
    issue_authenticated_owner_objective,
    verify_authenticated_owner_objective,
)
from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, canonical,
)
from orchestrator.pmv4_objective_scope import BoundedObjective


class PMv4McpBoundedOwnerDenied(PermissionError):
    pass


def authorize_one_bounded_objective_from_mcp(
    *, bearer_token: str, verified_owner_principal: str,
    verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    protected_main_check: Callable[[str], bool],
    objective: BoundedObjective, ledger: Any,
    signing_key: Ed25519PrivateKey, approval_id: str,
    affirmative_decision: str,
    at: datetime | None = None, production: bool = False,
) -> dict[str, Any]:
    """One signed parent, exact native plan; not a production root action."""
    if production:
        raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_NATIVE_ROOT_NOT_DEPLOYED")
    if (not isinstance(objective, BoundedObjective)
            or verified_organization != "aot"
            or verified_owner_principal not in EXACT_OWNER_OAUTH_SUBJECTS.values()
            or not isinstance(bearer_token, str) or len(bearer_token) < 16
            or affirmative_decision != "approve_exact_one_pmv4_objective"
            or not isinstance(signing_key, Ed25519PrivateKey)
            or any(not callable(x) for x in (
                verify_entra_bearer, exact_owner_consent, protected_main_check,
            ))):
        raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_EXACT_SESSION_REQUIRED")
    issued_at = at or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_TIME_INVALID")

    def exact_verified_token(value: str) -> Mapping[str, Any] | None:
        if value != bearer_token:
            raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_BEARER_SUBSTITUTED")
        claims = verify_entra_bearer(value)
        if (not isinstance(claims, Mapping)
                or EXACT_OWNER_OAUTH_SUBJECTS.get(claims.get("oid"))
                   != verified_owner_principal):
            raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_ENTRA_SUBJECT_MISMATCH")
        return claims

    def strict_exact_consent(presented: Mapping[str, Any]) -> bool:
        if (not isinstance(presented, Mapping)
                or set(presented) != {
                    "service", "approval_id", "owner_principal",
                    "plan_fingerprint", "full_reviewed_objective",
                }
                or presented["service"] != "pmv4-bounded-owner-objective"
                or presented["owner_principal"] != verified_owner_principal
                or presented["approval_id"] != approval_id
                or presented["plan_fingerprint"] != objective.fingerprint
                or presented["full_reviewed_objective"] != objective.review_material()):
            raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_PRESENTED_PLAN_CHANGED")
        return exact_owner_consent(dict(presented)) is True

    parent = issue_authenticated_owner_objective(
        objective=objective, ledger=ledger, approval_id=approval_id,
        bearer_token=bearer_token, verify_entra_bearer=exact_verified_token,
        exact_owner_consent=strict_exact_consent,
        protected_main_check=protected_main_check,
        signer_private_key=signing_key, at=issued_at,
    )
    signed = verify_authenticated_owner_objective(
        parent, objective=objective,
        pinned_public_key=signing_key.public_key(),
        at=issued_at, ledger=ledger,
    )
    if signed["owner_principal"] != verified_owner_principal:
        raise PMv4McpBoundedOwnerDenied("PMV4_ONE_OWNER_FINAL_SUBJECT_MISMATCH")
    return {
        "status": "source_only_owner_full_objective_signed",
        "approval_id": signed["parent_approval_id"],
        "parent_plan_fingerprint": objective.fingerprint,
        "parent_signed_sha256": sha256(canonical(parent)).hexdigest(),
        "signed_parent": parent,
        "human_decision_count": 1,
        "production_authorized": False,
        "production_installation_queued": False,
        "root_mutation": False,
        "standing_authority": False,
    }
