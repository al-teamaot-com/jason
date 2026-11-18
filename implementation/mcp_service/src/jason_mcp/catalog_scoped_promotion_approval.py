"""Fresh Entra Owner-signed exact catalog runtime/MCP release approval.

Source-only until a separately authorized production deployment. This action
only queues a one-use cryptographic decision; it never deploys or unfreezes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release, verify_exact_owner_release,
)

APPROVAL_WORDS = "APPROVE_EXACT_CATALOG_SCOPED_RUNTIME_MCP_RELEASE"


class CatalogScopedApprovalDenied(PermissionError):
    pass


def fail(code: str) -> None:
    raise CatalogScopedApprovalDenied("CATALOG_SCOPED_APPROVAL_" + code)


def trusted_offer_from_mcp(state_root: Path, release_id: str) -> dict[str, Any]:
    """Untrusted offer shown to Owner; root verifies its own immutable copy."""
    from kernel.catalog_scoped_promotion_contract import validate_offer
    if (not isinstance(release_id,str) or not release_id.startswith("release-")
            or len(release_id) != 24 or any(c not in "0123456789abcdef" for c in release_id[8:])):
        fail("RELEASE_ID_INVALID")
    path=state_root/"offers"/(release_id+".json")
    try:
        info=path.lstat()
        if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode)&0o077 or info.st_size>16384
                or info.st_nlink!=1):
            fail("OFFER_FILE_UNTRUSTED")
        offer=json.loads(path.read_bytes())
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        raise CatalogScopedApprovalDenied("CATALOG_SCOPED_APPROVAL_OFFER_NOT_AVAILABLE") from exc
    validate_offer(offer)
    if offer["release_id"]!=release_id:
        fail("OFFER_ID_MISMATCH")
    return offer


def queue_catalog_scoped_approval(
    *, state_root: Path, release_id: str, candidate_sha: str,
    manifest_sha256: str, approved_by: str, organization_id: str,
    verified_token_claims: Mapping[str,Any], service_signer: Ed25519PrivateKey,
    affirmative_decision: str,
) -> dict[str,Any]:
    """One affirmative Owner OAuth decision, bound to exact source/image pair."""
    if affirmative_decision != APPROVAL_WORDS:
        fail("EXACT_AFFIRMATIVE_DECISION_REQUIRED")
    if (not isinstance(verified_token_claims,Mapping)
            or not isinstance(service_signer,Ed25519PrivateKey)
            or organization_id!="aot"
            or verified_token_claims.get("tid")!="f7054323-d52b-4863-8c2f-1898f0b6077c"
            or verified_token_claims.get("oid") not in EXACT_OWNER_OAUTH_SUBJECTS
            or approved_by!=EXACT_OWNER_OAUTH_SUBJECTS.get(verified_token_claims.get("oid"))):
        fail("AUTHENTICATED_ENTRA_OWNER_REQUIRED")
    offer=trusted_offer_from_mcp(state_root,release_id)
    if candidate_sha!=offer["candidate_sha"] or manifest_sha256!=offer["manifest_sha256"]:
        fail("EXACT_RELEASE_OR_MANIFEST_MISMATCH")
    now=datetime.now(timezone.utc)
    signed=issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id=offer["release_id"],candidate_sha=offer["candidate_sha"],
        rollback_sha=offer["rollback_sha"],scope_sha256=offer["scope_sha256"],
        manifest_sha256=offer["manifest_sha256"],
        freeze_sha256=offer["freeze_sha256"],
        verified_tenant_id=str(verified_token_claims["tid"]),
        verified_owner_oid=str(verified_token_claims["oid"]),
        verified_principal=approved_by,verified_organization_id=organization_id,
        confirmed_decision="approve",at=now,private_key=service_signer)
    verify_exact_owner_release(signed,public_key=service_signer.public_key(),
        expected_candidate_sha=offer["candidate_sha"],
        expected_rollback_sha=offer["rollback_sha"],
        expected_release_id=offer["release_id"],
        expected_scope_sha256=offer["scope_sha256"],
        expected_manifest_sha256=offer["manifest_sha256"],
        expected_freeze_sha256=offer["freeze_sha256"],at=now)
    result={
        "schema_version":"1.0","authorization":"fresh_entra_catalog_scoped_owner",
        "release_id":offer["release_id"],"candidate_sha":offer["candidate_sha"],
        "manifest_sha256":offer["manifest_sha256"],
        "approved_by":approved_by,"organization_id":"aot",
        "signed_owner_proof":signed,
        "standing_authority":False,"production_mutation":False,
    }
    path=state_root/"owner-approvals"/(release_id+".json")
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.exists() or path.is_symlink():
        fail("APPROVAL_ALREADY_ISSUED_REPLAY_DENIED")
    raw=json.dumps(result,sort_keys=True,separators=(",", ":")).encode()+b"\n"
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=False) as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
    finally:os.close(fd)
    return {"status":"approval_queued_no_deployment",
            "release_id":release_id,"candidate_sha":candidate_sha,
            "manifest_sha256":manifest_sha256,
            "approval_id":signed["payload"]["approval_id"],
            "approved_by":approved_by,"owner_approval_is_one_use":True}
