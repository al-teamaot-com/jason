"""Authenticated MCP Owner decision to Stage E signed-proof adapter.

The live issuer is disabled until explicitly installed and enabled. When
enabled it publishes one signed request; the root worker independently
verifies the request and executes only its own reviewed native transaction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4
import os

from kernel import signed_owner_release as signer
from jason_mcp import pmv4_stage_a0_owner_issuer as common

APP_ID, ISSUER = common.APP_ID, common.ISSUER
BOOTSTRAP_ACTION = "pmv4_e_stage_exact_signed_inert_root_v1"


class StageEMcpBridgeDenied(PermissionError):
    pass


def _build_stage_e_request(
    *, bearer_token: str,
    verified_principal: str, verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    source_review: Callable[[str, str], bool],
    reviewed_offer: Mapping[str, Any],
    candidate_sha: str, rollback_sha: str,
    scope_sha256: str, manifest_sha256: str, freeze_sha256: str,
    affirmative_decision: str, signing_key: Any,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Build one exact signed proof after independently checking Owner claims."""
    if (verified_organization != "aot"
            or verified_principal not in signer.EXACT_OWNER_OAUTH_SUBJECTS.values()
            or not isinstance(bearer_token, str) or len(bearer_token) < 16
            or affirmative_decision != "approve_exact_pmv4_stage_e_cutover"
            or not callable(verify_entra_bearer)
            or not callable(exact_owner_consent)
            or not callable(source_review)
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
    if source_review(candidate_sha, rollback_sha) is not True:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_SOURCE_REVIEW_DENIED")

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

    proof = signer.issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id="release-" + candidate_sha[:16],
        candidate_sha=candidate_sha, rollback_sha=rollback_sha,
        scope_sha256=scope_sha256, manifest_sha256=manifest_sha256,
        freeze_sha256=freeze_sha256, verified_tenant_id=signer.TID,
        verified_owner_oid=claims["oid"], verified_principal=verified_principal,
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=signing_key,
    )
    signer.verify_exact_owner_release(
        proof, public_key=signing_key.public_key(),
        expected_candidate_sha=candidate_sha, expected_rollback_sha=rollback_sha,
        expected_release_id="release-" + candidate_sha[:16],
        expected_scope_sha256=scope_sha256, expected_manifest_sha256=manifest_sha256,
        expected_freeze_sha256=freeze_sha256, at=now,
    )
    request = {
        "schema_version": "1.0", "request_id": "release-" + candidate_sha[:16],
        "action": BOOTSTRAP_ACTION, "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha, "scope_sha256": scope_sha256,
        "manifest_sha256": manifest_sha256, "freeze_sha256": freeze_sha256,
        "signed_owner_proof": proof,
    }
    return {
        "status": "source_only_stage_e_request_prepared",
        "request": request,
        "standing_authority": False,
        "production_authorized": False,
        "production_mutations": False,
    }


def build_stage_e_request(*, production: bool = True, **kwargs) -> dict[str, Any]:
    """Offline proof fixture; live issuance uses fixed paths and a feature gate."""
    if production:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_ROOT_DISPATCH_NOT_DEPLOYED")
    return _build_stage_e_request(**kwargs)


def issue_stage_e_request(
    *, bearer_token: str,
    verified_principal: str, verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    protected_main_check: Callable[[str], bool],
    candidate_sha: str, rollback_sha: str,
    scope_sha256: str, manifest_sha256: str, freeze_sha256: str,
    affirmative_decision: str, production: bool = True,
    requests_path: Path = common.REQUESTS, freeze_path: Path = common.FREEZE,
    signer_path: Path = common.SIGNER, at: datetime | None = None,
) -> dict[str, Any]:
    """Queue a signed request; the root policy and native gates decide execution.

    The inputs describe the Owner's exact decision; they do not themselves
    prove that the source was reviewed. The protected-main check and the
    independent root dispatcher, CI, scope guard, and native ledger must pass.
    """
    if production and (
        Path(requests_path) != common.REQUESTS
        or Path(freeze_path) != common.FREEZE
        or Path(signer_path) != common.SIGNER
        or at is not None or os.geteuid() != 1000
        or os.environ.get("JASON_PMV4_STAGE_E_ISSUER_ENABLED") != "true"
    ):
        raise StageEMcpBridgeDenied("PMV4_E_MCP_ISSUER_NOT_INSTALLED")
    if not callable(protected_main_check):
        raise StageEMcpBridgeDenied("PMV4_E_MCP_PROTECTED_MAIN_REQUIRED")
    common._trusted_requests(Path(requests_path), production=production)
    if common._trusted_freeze(Path(freeze_path), production=production) != freeze_sha256:
        raise StageEMcpBridgeDenied("PMV4_E_MCP_FREEZE_BINDING_MISMATCH")
    signing_key = signer.read_service_owner_signing_key(Path(signer_path))
    decision = {
        "candidate": candidate_sha, "rollback": rollback_sha,
        "scope_sha256": scope_sha256, "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
    }
    built = _build_stage_e_request(
        bearer_token=bearer_token, verified_principal=verified_principal,
        verified_organization=verified_organization,
        verify_entra_bearer=verify_entra_bearer,
        exact_owner_consent=exact_owner_consent,
        source_review=lambda candidate, rollback: (
            protected_main_check(candidate) is True and candidate != rollback),
        reviewed_offer=decision, candidate_sha=candidate_sha,
        rollback_sha=rollback_sha, scope_sha256=scope_sha256,
        manifest_sha256=manifest_sha256, freeze_sha256=freeze_sha256,
        affirmative_decision=affirmative_decision, signing_key=signing_key, at=at,
    )
    owner_request = built["request"]
    approval_id = owner_request["signed_owner_proof"]["payload"]["approval_id"]
    request_id = "pmv4-e-" + candidate_sha[:16] + "-" + approval_id[10:]
    common._publish_exact_request(Path(requests_path) / (request_id + ".json"), {
        "request_id": request_id, "source_revision": candidate_sha,
        "action": "pmv4_e_cutover", "owner_request": owner_request,
    })
    return {
        "status": "signed_exact_stage_e_request_queued",
        "request_id": request_id, "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha, "approval_id": approval_id,
        "standing_authority": False, "production_deployment": False,
    }
