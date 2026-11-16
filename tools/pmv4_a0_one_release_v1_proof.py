"""One existing v1 Owner exact-release proof for ALL three A0 actions.

Key simplification: existing independently root-pinned v1 approval ALREADY
supports exactly one immutable release manifest + scope. When the three A0
operations run under one root lock, one such signed release is sufficient;
there is no need to mint 3 new human consents or deploy a new approval issuer.

SOURCE-ONLY crypto acceptance. This module never authenticates a human,
reads private keys, opens sudo, installs root components, changes freeze, or
grants production authority by itself. The existing audited Entra Owner issuer
must provide independent human identity before a real one-release signature.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, TID, canonical,
    issue_exact_owner_release, verify_exact_owner_release,
)
from tools import pmv4_stage_a0_one_owner_review as review


class A0OneReleaseProofDenied(PermissionError):
    pass


def exact_three_action_manifest() -> dict[str, Any]:
    """All fields independently pinned to existing exact release scope."""
    p = review.exact_contract()
    root_dir = Path(__file__).resolve().parents[1]
    root_code = root_dir / "tools/pmv4_a0_exact_v1_root_release.py"
    root_policy = json.loads((root_dir / "config/pmv4-stage-a0/atomic-v1-root-policy-review.json").read_bytes())
    if (root_policy.get("candidate_sha") != review.SOURCE
            or root_policy.get("lkg_sha") != review.LKG
            or root_policy.get("reviewed_contract_sha256") != review.CONTRACT_SHA256
            or root_policy.get("production_apply_supported") is not False
            or root_policy.get("root_executor_sha256")
                != sha256(root_code.read_bytes()).hexdigest()):
        raise A0OneReleaseProofDenied("A0_ONE_RELEASE_ROOT_CODE_NOT_PINNED")
    actions = [dict(x) for x in p["ordered_actions"]]
    if (len(actions) != 3
            or [(
                x["capability"], x["component"], x["scope_sha256"],
                x["artifact_sha256"],
            ) for x in actions] != list(review.REVIEWED_ACTIONS)
            or any(x["rollback_sha"] != review.ZERO for x in actions)):
        raise A0OneReleaseProofDenied("A0_ONE_RELEASE_SCOPE_NOT_THREE")
    return {
        "schema_version": "1.0",
        "service": "pmv4-stage-a0-exact-three-action-one-release",
        "source_sha": review.SOURCE,
        "production_lkg": review.LKG,
        "rollback_sha": review.LKG,
        "freeze_sha256": review.FREEZE,
        "promotion_hold_sha256": review.HOLD,
        "reviewed_contract_sha256": review.CONTRACT_SHA256,
        "root_executor_sha256":root_policy["root_executor_sha256"],
        "exact_ordered_actions": actions,
        "source_staging": review.SOURCE_STAGE,
        "owner_consents": 1,
        "root_lock_shared_by_all_actions": True,
        "require_root_only_empty_baseline": True,
        "require_reverse_verified_rollback": True,
        "production_runtime_or_mcp_replacement": False,
        "production_freeze_or_hold_mutation": False,
        "provider_or_ticket_mutation": False,
        "standing_authority": False,
        "one_release_only": True,
    }


def exact_v1_release_scopes() -> dict[str, Any]:
    manifest = exact_three_action_manifest()
    allowed = {
        "schema_version": "1.0",
        "service": manifest["service"],
        "source_sha": manifest["source_sha"],
        "rollback_sha": manifest["rollback_sha"],
        "reviewed_contract_sha256": manifest["reviewed_contract_sha256"],
        "root_executor_sha256":manifest["root_executor_sha256"],
        "exact_ordered_actions": manifest["exact_ordered_actions"],
        "source_staging": manifest["source_staging"],
        "one_release_only": True,
    }
    return {
        "scope_sha256": sha256(canonical(allowed)).hexdigest(),
        "manifest_sha256": sha256(canonical(manifest)).hexdigest(),
        "source_sha": review.SOURCE,
        "rollback_sha": review.LKG,
        "freeze_sha256": review.FREEZE,
        "manifest": manifest,
    }


def issue_source_only_existing_v1_proof(
    *, approval_id: str, signer_key: Ed25519PrivateKey,
    verified_owner_oid: str, at: datetime,
    independent_entra_owner_was_verified: bool,
    confirmed_exact_full_plan: bool,
    production: bool = False,
) -> dict[str, Any]:
    if production:
        raise A0OneReleaseProofDenied("A0_NATIVE_ONE_RELEASE_ROOT_NOT_INSTALLED")
    if (not isinstance(signer_key, Ed25519PrivateKey)
            or independent_entra_owner_was_verified is not True
            or confirmed_exact_full_plan is not True
            or verified_owner_oid not in EXACT_OWNER_OAUTH_SUBJECTS
            or not isinstance(at, datetime) or at.tzinfo is None
            or not isinstance(approval_id, str)
            or not approval_id.startswith("owner-mcp-")
            or len(approval_id) != 42):
        raise A0OneReleaseProofDenied("A0_ONE_RELEASE_AUTHENTICATED_OWNER_REQUIRED")
    scope = exact_v1_release_scopes()
    return issue_exact_owner_release(
        approval_id=approval_id,
        release_id="release-" + review.SOURCE[:16],
        candidate_sha=review.SOURCE, rollback_sha=review.LKG,
        scope_sha256=scope["scope_sha256"],
        manifest_sha256=scope["manifest_sha256"],
        freeze_sha256=scope["freeze_sha256"],
        verified_tenant_id=TID,
        verified_owner_oid=verified_owner_oid,
        verified_principal=EXACT_OWNER_OAUTH_SUBJECTS[verified_owner_oid],
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=at,
        private_key=signer_key,
    )


def verify_existing_v1_whole_transaction(
    *, signed: Mapping[str, Any],
    root_pinned_public_key: Ed25519PublicKey,
    at: datetime,
    consumed_ids: frozenset[str] = frozenset(),
    production: bool = False,
) -> dict[str, Any]:
    """Existing native v1 signature checks, with strict whole-scope binding.

    This is only cryptographic readback. A live root-owned executor MUST
    independently verify and enforce all three actions under one lease.
    """
    if production:
        raise A0OneReleaseProofDenied("A0_NATIVE_ONE_RELEASE_ROOT_NOT_INSTALLED")
    if (not isinstance(root_pinned_public_key, Ed25519PublicKey)
            or not isinstance(signed, Mapping)
            or not isinstance(at, datetime) or at.tzinfo is None
            or not isinstance(consumed_ids, frozenset)):
        raise A0OneReleaseProofDenied("A0_ONE_RELEASE_ROOT_INPUT_UNTRUSTED")
    scope = exact_v1_release_scopes()
    proof = verify_exact_owner_release(
        signed,
        public_key=root_pinned_public_key,
        expected_candidate_sha=review.SOURCE,
        expected_rollback_sha=review.LKG,
        expected_release_id="release-" + review.SOURCE[:16],
        expected_scope_sha256=scope["scope_sha256"],
        expected_manifest_sha256=scope["manifest_sha256"],
        expected_freeze_sha256=scope["freeze_sha256"],
        at=at, consumed_ids=consumed_ids,
    )
    if (proof.get("one_release_only") is not True
            or proof.get("standing_authority") is not False):
        raise A0OneReleaseProofDenied("A0_ONE_RELEASE_UNBOUNDED_PROOF_DENIED")
    return {
        "status": "exact_v1_signed_whole_A0_release_crypto_verified_only",
        "owner_approval_id": proof["approval_id"],
        "scope_sha256": scope["scope_sha256"],
        "manifest_sha256": scope["manifest_sha256"],
        "approved_action_count": len(scope["manifest"]["exact_ordered_actions"]),
        "root_mutation_authorized": False,
        "production_release_installed": False,
    }
