#!/usr/bin/env python3
"""Standalone PMv4 Entra Owner proof issuer adapter — SOURCE ONLY.

An independently installed trusted OAuth middleware supplies a freshly
cryptographically verified AOT Entra token and exact-user-confirmation
callback. Neither can be supplied through a client-controlled argument in
production. This module never verifies OAuth JWTs itself; absent the trusted
middleware the issuance path is unavailable, not implicitly authorized.

Reuses the existing Jason provider-neutral Ed25519 release proof format,
without any PMV3 release queue or Teams dependency.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, OWNER_PRINCIPAL, TID,
    canonical, issue_exact_owner_release, read_service_owner_signing_key,
    verify_exact_owner_release,
)

from tools.pmv4_shadow_release import (
    PRODUCTION_ROOT, ShadowReleaseDenied, digest_file, manifest_check,
    read_json, write_json_exclusive,
)

ISSUER = "https://login.microsoftonline.com/" + TID + "/v2.0"
# The real audience comes ONLY from a root-owned, separately approved
# authentication configuration. No default client-ID or bypass is provided.
AUDIENCE_PATH = Path("/etc/jason/pmv4-shadow/entra-audience.json")
SIGNER_PATH = Path("/etc/jason/pmv4-shadow/owner-release-signer.key")


def issue_shadow_owner_proof(
    *,
    root: Path,
    bearer_token: str,
    jwt_verifier: Callable[[str], Mapping[str, Any]],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    protected_main_check: Callable[[str], bool],
    audience_path: Path = AUDIENCE_PATH,
    signer_path: Path = SIGNER_PATH,
    at: datetime | None = None,
    production: bool = True,
) -> dict[str, Any]:
    """Create one Owner decision only after independent OAuth and user consent.

    No production OAuth verifier, routing endpoint, secret or trust root is
    provisioned by this source file. A test may inject offline fixtures, but a
    production host must pin every path and own both trusted callbacks.
    """
    from tools.pmv4_shadow_release import safe_root
    shadow_root = safe_root(root, production=production)
    if production and (
        Path(audience_path) != AUDIENCE_PATH or Path(signer_path) != SIGNER_PATH
    ):
        raise ShadowReleaseDenied("SHADOW_OWNER_IDENTITY_CONFIG_NOT_PINNED")
    if not isinstance(bearer_token, str) or len(bearer_token) < 16:
        raise ShadowReleaseDenied("SHADOW_ENTRA_BEARER_MISSING")
    if not all(callable(x) for x in (jwt_verifier, exact_owner_consent, protected_main_check)):
        raise ShadowReleaseDenied("SHADOW_TRUSTED_OWNER_ISSUER_UNAVAILABLE")
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ShadowReleaseDenied("SHADOW_APPROVAL_TIME_INVALID")
    now_unix = int(now.timestamp())
    audience_doc = read_json(Path(audience_path))
    if production:
        audience_file = Path(audience_path)
        meta = audience_file.lstat()
        parent = audience_file.parent.lstat()
        if (meta.st_uid != 0 or parent.st_uid != 0
            or stat.S_IMODE(meta.st_mode) & 0o022
            or stat.S_IMODE(parent.st_mode) & 0o022
            or audience_file.is_symlink() or audience_file.parent.is_symlink()):
            raise ShadowReleaseDenied("SHADOW_OWNER_AUDIENCE_POLICY_UNTRUSTED")
    if set(audience_doc) != {"schema_version", "service", "audience"} or (
        audience_doc["schema_version"] != "1.0"
        or audience_doc["service"] != "jason-pmv4-shadow"
        or not isinstance(audience_doc["audience"], str)
        or not audience_doc["audience"].strip()
    ):
        raise ShadowReleaseDenied("SHADOW_OWNER_AUDIENCE_INVALID")
    try:
        claims = jwt_verifier(bearer_token)
    except (ValueError, TypeError, RuntimeError, OSError, PermissionError) as exc:
        raise ShadowReleaseDenied("SHADOW_ENTRA_TOKEN_VERIFICATION_FAILED") from exc
    if not isinstance(claims, Mapping):
        raise ShadowReleaseDenied("SHADOW_ENTRA_TOKEN_UNVERIFIED")
    subject = claims.get("oid")
    if (claims.get("iss") != ISSUER
        or claims.get("tid") != TID
        or claims.get("aud") != audience_doc["audience"]
        or subject not in EXACT_OWNER_OAUTH_SUBJECTS
        or type(claims.get("iat")) is not int
        or type(claims.get("nbf")) is not int
        or type(claims.get("exp")) is not int
        or not claims["iat"] <= now_unix
        or not claims["nbf"] <= now_unix < claims["exp"]
        or now_unix - claims["iat"] > 900):
        raise ShadowReleaseDenied("SHADOW_ENTRA_OWNER_IDENTITY_NOT_VERIFIED")
    control = shadow_root / "control"
    manifest = read_json(control / "approved-manifest.json")
    manifest_check(manifest)
    if protected_main_check(manifest["candidate_sha"]) is not True:
        raise ShadowReleaseDenied("SHADOW_PROTECTED_MAIN_UNVERIFIED")
    scope = read_json(control / "reviewed-scope.json")
    if sha256(canonical(scope)).hexdigest() != manifest["scope_sha256"]:
        raise ShadowReleaseDenied("SHADOW_OWNER_REVIEWED_SCOPE_CHANGED")
    freeze = read_json(control / "shadow-freeze.json")
    if freeze != {"schema_version": "1.0", "status": "active",
                  "service": "jason-pmv4-shadow"}:
        raise ShadowReleaseDenied("SHADOW_OWNER_FREEZE_INVALID")
    binding = {
        "service": "jason-pmv4-shadow",
        "release_id": "release-" + manifest["candidate_sha"][:16],
        "candidate_sha": manifest["candidate_sha"],
        "rollback_sha": manifest["rollback_sha"],
        "scope_sha256": manifest["scope_sha256"],
        "manifest_sha256": sha256(canonical(manifest)).hexdigest(),
        "freeze_sha256": digest_file(control / "shadow-freeze.json"),
        "owner_principal": EXACT_OWNER_OAUTH_SUBJECTS[subject],
    }
    # Exact confirmation must be obtained from trusted Owner-authenticated
    # middleware in the same live session, not from chat text or JSON.
    if exact_owner_consent(binding) is not True:
        raise ShadowReleaseDenied("SHADOW_EXACT_OWNER_CONFIRMATION_MISSING")
    signing_key = read_service_owner_signing_key(signer_path)
    proof = issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id=binding["release_id"],
        candidate_sha=binding["candidate_sha"],
        rollback_sha=binding["rollback_sha"],
        scope_sha256=binding["scope_sha256"],
        manifest_sha256=binding["manifest_sha256"],
        freeze_sha256=binding["freeze_sha256"],
        verified_tenant_id=TID, verified_owner_oid=subject,
        verified_principal=binding["owner_principal"],
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=signing_key,
    )
    verify_exact_owner_release(
        proof, public_key=signing_key.public_key(),
        expected_candidate_sha=binding["candidate_sha"],
        expected_rollback_sha=binding["rollback_sha"],
        expected_release_id=binding["release_id"],
        expected_scope_sha256=binding["scope_sha256"],
        expected_manifest_sha256=binding["manifest_sha256"],
        expected_freeze_sha256=binding["freeze_sha256"],
        at=now,
    )
    folder = control / "signed-owner-decisions"
    if not folder.is_dir() or folder.is_symlink():
        raise ShadowReleaseDenied("SHADOW_OWNER_DECISION_STORE_UNAVAILABLE")
    path = folder / (binding["release_id"] + ".json")
    write_json_exclusive(path, {
        "schema_version": "1.0",
        "service": "jason-pmv4-shadow",
        "source": "independently_verified_entra_owner",
        "release_id": binding["release_id"],
        "owner_principal": binding["owner_principal"],
        "signed_owner_proof": proof,
    })
    return {
        "status": "owner_decision_signed_for_exact_shadow_release",
        "release_id": binding["release_id"],
        "candidate_sha": binding["candidate_sha"],
        "approval_id": proof["payload"]["approval_id"],
        "teams_required": False,
        "standing_authority": False,
    }


if __name__ == "__main__":
    raise SystemExit("No live issuer: approved Entra OAuth middleware must be installed.")
