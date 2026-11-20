"""Authenticated MCP Owner decision to Stage E signed-proof adapter.

This integration is source-only until the matching root dispatcher and reviewed
deployment are installed. It does not publish a proof or execute root actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from implementation.kernel import signed_owner_release as signer
from jason_mcp.pmv4_stage_a0_owner_issuer import APP_ID, ISSUER
from tools import pmv4_e_exact_owner_offer as offer


class StageEMcpBridgeDenied(PermissionError):
    pass


def build_stage_e_request(
    *, bearer_token: str,
    verified_principal: str, verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    reviewed_offer: Mapping[str, Any],
    candidate_sha: str, rollback_sha: str,
    scope_sha256: str, manifest_sha256: str, freeze_sha256: str,
    affirmative_decision: str, signing_key: Any,
    at: datetime | None = None, production: bool = True,
) -> dict[str, Any]:
    """Create a signed test request from one authenticated exact decision.

    A future production caller must obtain the offer from the existing pinned
    Stage E offer verifier and publish it only after trusted root admission and
    fresh CI are ready. Production is deliberately unavailable until then.
    """
    if production:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_ROOT_DISPATCH_NOT_DEPLOYED")
    if (verified_organization != "aot"
            or verified_principal not in signer.EXACT_OWNER_OAUTH_SUBJECTS.values()
            or not isinstance(bearer_token, str) or len(bearer_token) < 16
            or affirmative_decision != "approve_exact_pmv4_stage_e_cutover"
            or not callable(verify_entra_bearer)
            or not callable(exact_owner_consent)
            or not isinstance(reviewed_offer, Mapping)):
        raise StageEMcpBridgeDenied("PMV4_E_MCP_AUTHENTICATED_OWNER_REQUIRED")

    expected = {
        "candidate": candidate_sha, "rollback": rollback_sha,
        "scope_sha256": scope_sha256, "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
    }
    if (not all(isinstance(v, str) and
                (signer.SHA.fullmatch(v) if k in ("candidate", "rollback")
                 else signer.DIGEST.fullmatch(v))
                for k, v in expected.items())
            or candidate_sha == rollback_sha
            or any(reviewed_offer.get(k) != v for k, v in expected.items())):
        raise StageEMcpBridgeDenied("PMV4_E_MCP_REVIEWED_OFFER_MISMATCH")

    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_CLOCK_INVALID")
    try:
        claims = verify_entra_bearer(bearer_token)
    except (PermissionError, ValueError, TypeError, RuntimeError, OSError) as exc:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_ENTRA_VERIFICATION_FAILED") from exc
    timestamp = int(now.timestamp())
    if (not isinstance(claims, Mapping)
            or claims.get("tid") != signer.TID
            or claims.get("iss") != ISSUER or claims.get("aud") != APP_ID
            or signer.EXACT_OWNER_OAUTH_SUBJECTS.get(claims.get("oid"))
               != verified_principal
            or any(type(claims.get(k)) is not int for k in ("iat", "nbf", "exp"))
            or not claims["iat"] <= timestamp
            or not claims["nbf"] <= timestamp < claims["exp"]
            or timestamp - claims["iat"] > 900):
        raise StageEMcpBridgeDenied("PMV4_E_MCP_ENTRA_CLAIMS_DENIED")

    binding = {
        "service": "pmv4-stage-e-six-unit-cutover",
        "candidate_sha": candidate_sha, "rollback_sha": rollback_sha,
        "scope_sha256": scope_sha256, "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256, "owner_principal": verified_principal,
    }
    if exact_owner_consent(binding) is not True:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_EXACT_DECISION_REQUIRED")

    request = offer.signed_request(
        expected, signer=signer, private=signing_key,
        owner_oid=claims["oid"], at=now,
    )
    return {
        "status": "source_only_stage_e_request_prepared",
        "request": request,
        "standing_authority": False,
        "production_authorized": False,
        "production_mutations": False,
    }
