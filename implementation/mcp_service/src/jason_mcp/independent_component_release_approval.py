"""Entra-authenticated Owner approval for a prepared independent-component release.

The signed request is nonexecuting. A separately installed root-controller must
revalidate every field against protected source, root-owned staging, CI, current
freeze, site boundary, locks, and the live runtime before consuming it.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
    verify_exact_owner_release, canonical,
)

SHA = re.compile(r"^[a-f0-9]{40}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
FIELDS = {
    "schema_version", "state", "component_id", "candidate_sha", "rollback_sha",
    "scope_sha256", "manifest_sha256", "freeze_sha256", "image_digest",
    "source_and_ci_verified", "preproduction_verified", "rollback_ready",
    "no_protected_services_changed", "prepared_at",
}


def _offer(path: Path) -> dict[str, Any]:
    try:
        meta = path.lstat()
        if (
            path.is_symlink() or not path.is_file() or meta.st_nlink != 1
            or meta.st_size < 1 or meta.st_size > 16384 or meta.st_mode & 0o002
        ):
            raise ValueError("COMPONENT_OWNER_OFFER_UNTRUSTED")
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("COMPONENT_OWNER_OFFER_UNAVAILABLE") from exc
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("COMPONENT_OWNER_OFFER_SCHEMA")
    if (
        value["schema_version"] != "1.0"
        or value["state"] != "production_eligible"
        or not isinstance(value["component_id"], str)
        or SLUG.fullmatch(value["component_id"]) is None
        or not isinstance(value["candidate_sha"], str)
        or SHA.fullmatch(value["candidate_sha"]) is None
        or not isinstance(value["rollback_sha"], str)
        or SHA.fullmatch(value["rollback_sha"]) is None
        or not isinstance(value["image_digest"], str)
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", value["image_digest"])
        or any(
            not isinstance(value[k], str) or DIGEST.fullmatch(value[k]) is None
            for k in ("scope_sha256", "manifest_sha256", "freeze_sha256")
        )
        or any(value[k] is not True for k in (
            "source_and_ci_verified", "preproduction_verified",
            "rollback_ready", "no_protected_services_changed",
        ))
    ):
        raise ValueError("COMPONENT_OWNER_OFFER_NOT_ELIGIBLE")
    try:
        offered = datetime.fromisoformat(value["prepared_at"])
        now = datetime.now(timezone.utc)
        if offered.tzinfo is None or not timedelta(0) <= now - offered <= timedelta(hours=1):
            raise ValueError("freshness")
    except (TypeError, ValueError) as exc:
        raise ValueError("COMPONENT_OWNER_OFFER_STALE") from exc
    return value


def queue_component_release_approval(
    *, state_root: Path, component_id: str, candidate_sha: str,
    image_digest: str, approved_by: str, organization_id: str,
    verified_token_claims: Mapping[str, Any] | None,
    service_signer: Ed25519PrivateKey | None,
    confirmed_decision: str, reason: str = "",
) -> dict[str, Any]:
    """One-use exact-action signed receipt for a root-prepared component offer."""
    if (
        not isinstance(component_id, str) or SLUG.fullmatch(component_id) is None
        or not isinstance(candidate_sha, str) or SHA.fullmatch(candidate_sha) is None
        or not isinstance(image_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_digest)
        or confirmed_decision != "approve"
    ):
        raise ValueError("COMPONENT_OWNER_EXACT_APPROVAL_REQUIRED")
    if (
        not isinstance(verified_token_claims, Mapping)
        or verified_token_claims.get("tid") != "f7054323-d52b-4863-8c2f-1898f0b6077c"
        or verified_token_claims.get("oid") not in EXACT_OWNER_OAUTH_SUBJECTS
        or approved_by != EXACT_OWNER_OAUTH_SUBJECTS[verified_token_claims["oid"]]
        or organization_id != "aot"
        or not isinstance(service_signer, Ed25519PrivateKey)
    ):
        raise ValueError("COMPONENT_SIGNED_OWNER_EVIDENCE_REQUIRED")
    root = Path(state_root)
    offer_path = root / "independent-component-offers" / ("release-" + candidate_sha[:16] + ".json")
    offer = _offer(offer_path)
    if (
        offer["candidate_sha"] != candidate_sha
        or offer["component_id"] != component_id
        or offer["image_digest"] != image_digest
    ):
        raise ValueError("COMPONENT_OWNER_OFFER_IDENTITY_MISMATCH")
    freeze = root / "production-deployment-freeze"
    if freeze.is_symlink() or not freeze.is_file():
        raise ValueError("COMPONENT_OWNER_FREEZE_UNAVAILABLE")
    if sha256(freeze.read_bytes()).hexdigest() != offer["freeze_sha256"]:
        raise ValueError("COMPONENT_OWNER_FREEZE_DRIFT")
    release_id = "release-" + candidate_sha[:16]
    request = root / "independent-component-owner-approvals" / (release_id + ".json")
    if request.exists() or request.is_symlink():
        raise ValueError("COMPONENT_OWNER_APPROVAL_ALREADY_ISSUED")
    signed = issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id=release_id,
        candidate_sha=candidate_sha,
        rollback_sha=offer["rollback_sha"],
        scope_sha256=offer["scope_sha256"],
        manifest_sha256=offer["manifest_sha256"],
        freeze_sha256=offer["freeze_sha256"],
        verified_tenant_id=str(verified_token_claims["tid"]),
        verified_owner_oid=str(verified_token_claims["oid"]),
        verified_principal=approved_by,
        verified_organization_id=organization_id,
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=service_signer,
    )
    verify_exact_owner_release(
        signed, public_key=service_signer.public_key(),
        expected_candidate_sha=candidate_sha, expected_rollback_sha=offer["rollback_sha"],
        expected_release_id=release_id, expected_scope_sha256=offer["scope_sha256"],
        expected_manifest_sha256=offer["manifest_sha256"],
        expected_freeze_sha256=offer["freeze_sha256"],
        at=datetime.now(timezone.utc),
    )
    payload = {
        "schema_version": "1.0",
        "component_id": component_id,
        "image_digest": image_digest,
        "release_id": release_id,
        "candidate_sha": candidate_sha,
        "approved_by": approved_by,
        "organization_id": organization_id,
        "source": "authenticated_jason_mcp_owner:" + signed["payload"]["approval_id"],
        "reason": str(reason)[:1000],
        "signed_owner_proof": signed,
    }
    request.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(request, flags, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(canonical(payload) + b"\n")
        out.flush()
        os.fsync(out.fileno())
    return payload
