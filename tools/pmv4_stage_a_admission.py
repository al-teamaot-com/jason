#!/usr/bin/env python3
"""Standalone, non-mutating exact-Owner Stage A0 installation admission verifier.

This is a SOURCE-ONLY primitive for a future trusted root installation
transaction. It cannot issue Owner decisions or install host controls.
The real root installer must invoke it under native host locks after
independently loading immutable source/proof and live root health.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping

from implementation.kernel.signed_owner_release import (
    canonical, read_pinned_root_owner_public_key,
    verify_exact_owner_release,
)
from tools import pmv4_stage_a_packet as packet

class StageAAdmissionDenied(PermissionError):
    pass


def exact_stage_a_manifest(scope: Mapping[str, Any], freeze_sha256: str) -> dict[str, Any]:
    """Canonical exact-action identity. Never treat this as an authorization."""
    from tools.pmv4_shadow_release import HASH
    if (not isinstance(scope, Mapping) or scope.get("schema_version") != "1.0"
            or scope.get("phase") != "stage-a0-independent-trusted-host-bootstrap"
            or scope.get("rollback_sha") != packet.EMPTY_BASELINE
            or not isinstance(freeze_sha256, str)
            or HASH.fullmatch(freeze_sha256) is None
            or scope.get("install_approval_required") is not True
            or scope.get("production_freeze_change") is not False
            or scope.get("production_services_restart") is not False
            or scope.get("breaker_mutation") is not False
            or scope.get("owner_issuer_enabled") is not False
            or scope.get("provider_writes") is not False
            or scope.get("installer_authority")
               != "native-root-signed-exact-owner-transaction-only"):
        raise StageAAdmissionDenied("STAGE_A_SCOPE_IDENTITY_NOT_SAFE")
    return {
        "schema_version": "1.0",
        "service": "pmv4-stage-a0-host-bootstrap",
        "source_sha": scope["candidate_sha"],
        "rollback_sha": scope["rollback_sha"],
        "reviewed_scope_sha256": scope["scope_sha256"],
        "trusted_host_code_bundle_sha256": scope["host_code_bundle_sha256"],
        "freeze_sha256": freeze_sha256,
        "installation_mutation": "create-only-exact-stage-a0-root-objects",
        "protected_services_restart": False,
        "standing_authority": False,
    }


def verify_admission(
    *, repo: Path, candidate_sha: str, reviewed_scope: Mapping[str, Any],
    exact_manifest: Mapping[str, Any], signed_owner_proof: Mapping[str, Any],
    frozen_marker: Path, confirmed_root_health: Mapping[str, Any],
    protected_main_ci_check: Callable[[str], bool],
    consumed_ids: frozenset[str] = frozenset(),
    at: datetime | None = None,
    production: bool = True,
    pinned_trust: Path = Path(packet.TRUST),
    test_public_key: Any = None,
) -> dict[str, Any]:
    """Read-only root preflight; requires a separately authenticated proof.

    The caller must already hold the existing native release transaction lock.
    The trusted root installer must independently read protected root state
    and re-run admission under the transaction immediately before mutation.
    """
    if at is None:
        at = datetime.now(timezone.utc)
    if not isinstance(confirmed_root_health, Mapping):
        raise StageAAdmissionDenied("STAGE_A_ROOT_EVIDENCE_INVALID")
    if not callable(protected_main_ci_check) or (
        protected_main_ci_check(candidate_sha) is not True
    ):
        raise StageAAdmissionDenied("STAGE_A_PROTECTED_MAIN_CI_UNVERIFIED")
    if production and Path(pinned_trust) != Path(packet.TRUST):
        raise StageAAdmissionDenied("STAGE_A_TRUST_PATH_OVERRIDE")
    if production and test_public_key is not None:
        raise StageAAdmissionDenied("STAGE_A_CALLER_PUBLIC_KEY_OVERRIDE")
    packet.verify_exact_repository_head(repo, candidate_sha)
    independently_reviewed = packet.build_scope(repo, candidate_sha)
    if independently_reviewed != reviewed_scope:
        raise StageAAdmissionDenied("STAGE_A_REVIEWED_SCOPE_DRIFT")
    if (independently_reviewed.get("scope_sha256")
        != packet._digest(packet._canonical({
            k:v for k,v in independently_reviewed.items() if k != "scope_sha256"
        }))):
        raise StageAAdmissionDenied("STAGE_A_SCOPE_DIGEST_DRIFT")
    try:
        freeze_digest = sha256(Path(frozen_marker).read_bytes()).hexdigest()
    except OSError as exc:
        raise StageAAdmissionDenied("STAGE_A_FROZEN_MARKER_UNAVAILABLE") from exc
    expected_manifest = exact_stage_a_manifest(independently_reviewed, freeze_digest)
    if exact_manifest != expected_manifest:
        raise StageAAdmissionDenied("STAGE_A_EXACT_MANIFEST_DRIFT")
    # The already root-verified host health must be current and separately
    # obtained by the native release worker, not just a mutable PASS string.
    required_health = {
        "preflight_evidence_satisfied": True,
        "stage_a_empty_baseline_verified": True,
        "root_only_target_parent_verification_needed": False,
        "breaker_state": "closed",
        "installation_ready": False,
        "production_install_authorized": False,
    }
    if any(confirmed_root_health.get(k) != v for k,v in required_health.items()):
        raise StageAAdmissionDenied("STAGE_A_ROOT_PREFLIGHT_NOT_READY")
    if confirmed_root_health.get("freeze_sha256") != freeze_digest:
        raise StageAAdmissionDenied("STAGE_A_FREEZE_CHANGED")
    if not isinstance(consumed_ids, frozenset):
        raise StageAAdmissionDenied("STAGE_A_REPLAY_LEDGER_UNTRUSTED")
    pub = (read_pinned_root_owner_public_key(pinned_trust, require_root_owned=True)
           if production else test_public_key)
    try:
        verified = verify_exact_owner_release(
            signed_owner_proof, public_key=pub,
            expected_candidate_sha=candidate_sha,
            expected_rollback_sha=packet.EMPTY_BASELINE,
            expected_release_id="release-" + candidate_sha[:16],
            expected_scope_sha256=independently_reviewed["scope_sha256"],
            expected_manifest_sha256=sha256(canonical(expected_manifest)).hexdigest(),
            expected_freeze_sha256=freeze_digest,
            at=at, consumed_ids=consumed_ids,
        )
    except (PermissionError, ValueError, TypeError) as exc:
        raise StageAAdmissionDenied("STAGE_A_OWNER_SIGNED_DECISION_INVALID") from exc
    return {
        "status": "source_only_admission_verified",
        "exact_candidate_sha": candidate_sha,
        "exact_scope_sha256": independently_reviewed["scope_sha256"],
        "exact_manifest_sha256": sha256(canonical(expected_manifest)).hexdigest(),
        "rollback_sha": packet.EMPTY_BASELINE,
        "owner_approval_id": verified["approval_id"],
        "production_installed": False,
        "production_mutation": False,
        "trusted_root_installer_required": True,
    }
