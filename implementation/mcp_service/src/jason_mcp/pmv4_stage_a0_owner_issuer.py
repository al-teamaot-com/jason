"""Existing authenticated MCP -> exact one-use Stage A0 native root request.

Feature OFF until governed exact source/MCP release. No standing approval,
new signer, Teams card, provider mutation or direct privileged execution.
The root host independently revalidates the entire request and live gates.
"""
from __future__ import annotations

import ctypes
import errno
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping
from uuid import uuid4

from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, TID, canonical, issue_exact_owner_release,
    read_service_owner_signing_key, verify_exact_owner_release,
)

REQUESTS = Path(
    "/var/lib/jason/openclaw/release-manager/host-reconcile/requests"
)
FREEZE = Path(
    "/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
)
SIGNER = Path("/run/jason-secrets/owner-release/private_key")
REPO_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
APP_ID = "9b9996e9-5c34-48b7-948c-f44f89352f89"
ISSUER = "https://login.microsoftonline.com/" + TID + "/v2.0"
ZERO = "0" * 40


class StageA0OwnerIssuerDenied(PermissionError):
    pass


def _trusted_freeze(path: Path, *, production: bool) -> str:
    try:
        info = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise StageA0OwnerIssuerDenied("STAGE_A0_FREEZE_UNAVAILABLE") from exc
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1 or len(raw) > 4096
            or (production and (info.st_uid != 1000
                                or stat.S_IMODE(info.st_mode) != 0o600))):
        raise StageA0OwnerIssuerDenied("STAGE_A0_FREEZE_UNTRUSTED")
    return sha256(raw).hexdigest()


def _trusted_requests(path: Path, *, production: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise StageA0OwnerIssuerDenied("STAGE_A0_REQUEST_SPOOL_UNAVAILABLE") from exc
    if (path.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or info.st_mode & 0o002
            or (production and (info.st_uid != 1000
                                or stat.S_IMODE(info.st_mode) != 0o750))):
        raise StageA0OwnerIssuerDenied("STAGE_A0_REQUEST_SPOOL_UNTRUSTED")


def _rename_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a complete request without an observable hardlink race.

    The root worker requires st_nlink=1. link()/unlink() has a window where
    a concurrent DirectoryNotEmpty activation sees st_nlink=2 and rejects
    an otherwise valid Owner action. Linux renameat2(RENAME_NOREPLACE)
    prevents both that race and overwriting prior one-use decisions.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise StageA0OwnerIssuerDenied("STAGE_A0_ATOMIC_PUBLISH_UNAVAILABLE")
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    result = renameat2(
        at_fdcwd, os.fsencode(source), at_fdcwd, os.fsencode(target),
        rename_noreplace,
    )
    if result != 0:
        issue = ctypes.get_errno()
        if issue == errno.EEXIST:
            raise StageA0OwnerIssuerDenied(
                "STAGE_A0_ONE_SOURCE_REQUEST_ALREADY_EXISTS"
            )
        raise StageA0OwnerIssuerDenied(
            "STAGE_A0_ATOMIC_PUBLISH_FAILED"
        )


def _publish_exact_request(path: Path, payload: Mapping[str, Any]) -> None:
    """Write complete private 0600 request before atomic no-replace publish.

    The temporary is written in the adjacent spool parent OUTSIDE the
    watched requests directory. This guarantees DirectoryNotEmpty cannot
    trigger on a .tmp before the complete .json request is published.
    No overwrite of a prior Owner decision.
    """
    _trusted_requests(path.parent, production=False)
    _trusted_requests(path.parent.parent, production=False)
    encoded = canonical(payload)
    if len(encoded) > 16384 or path.suffix != ".json":
        raise StageA0OwnerIssuerDenied("STAGE_A0_REQUEST_OVERSIZE")
    temporary = path.parent.parent / (
        "." + path.stem + "." + uuid4().hex + ".tmp"
    )
    fd = -1
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb", closefd=False) as output:
            output.write(encoded)
            output.flush()
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        _rename_noreplace(temporary, path)
        dirfd = os.open(path.parent, os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except FileExistsError as exc:
        raise StageA0OwnerIssuerDenied(
            "STAGE_A0_ONE_SOURCE_REQUEST_ALREADY_EXISTS"
        ) from exc
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def issue_stage_a0_request(
    *, bearer_token: str,
    verified_principal: str, verified_organization: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    protected_main_check: Callable[[str], bool],
    candidate_sha: str, reviewed_scope_sha256: str,
    manifest_sha256: str, freeze_sha256: str,
    affirmative_decision: str,
    production: bool = True,
    requests_path: Path = REQUESTS, freeze_path: Path = FREEZE,
    signer_path: Path = SIGNER,
    at: datetime | None = None,
) -> dict[str, Any]:
    if production and (
        Path(requests_path) != REQUESTS
        or Path(freeze_path) != FREEZE
        or Path(signer_path) != SIGNER
        or at is not None
        or os.geteuid() != 1000
    ):
        raise StageA0OwnerIssuerDenied("STAGE_A0_PRODUCTION_PATH_OR_IDENTITY_OVERRIDE")
    if (verified_organization != "aot"
            or verified_principal not in EXACT_OWNER_OAUTH_SUBJECTS.values()
            or affirmative_decision != "approve_exact_pmv4_stage_a0_install"
            or not isinstance(bearer_token, str) or len(bearer_token) < 16
            or any(not callable(x) for x in (
                verify_entra_bearer, exact_owner_consent, protected_main_check
            ))):
        raise StageA0OwnerIssuerDenied("STAGE_A0_EXPLICIT_OWNER_AUTH_REQUIRED")
    if (not isinstance(candidate_sha, str)
            or REPO_SHA.fullmatch(candidate_sha) is None
            or any(not isinstance(k, str) or DIGEST.fullmatch(k) is None
                   for k in (reviewed_scope_sha256, manifest_sha256,
                             freeze_sha256))):
        raise StageA0OwnerIssuerDenied("STAGE_A0_EXACT_REVIEW_REQUIRED")
    if protected_main_check(candidate_sha) is not True:
        raise StageA0OwnerIssuerDenied("STAGE_A0_CURRENT_PROTECTED_MAIN_REQUIRED")
    _trusted_requests(Path(requests_path), production=production)
    actual_freeze = _trusted_freeze(Path(freeze_path), production=production)
    if actual_freeze != freeze_sha256:
        raise StageA0OwnerIssuerDenied("STAGE_A0_FREEZE_BINDING_MISMATCH")
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise StageA0OwnerIssuerDenied("STAGE_A0_INVALID_CLOCK")
    try:
        claims = verify_entra_bearer(bearer_token)
    except (ValueError, TypeError, RuntimeError, OSError, PermissionError) as exc:
        raise StageA0OwnerIssuerDenied("STAGE_A0_VERIFIED_ENTRA_REQUIRED") from exc
    t = int(now.timestamp())
    if (not isinstance(claims, Mapping)
            or claims.get("tid") != TID
            or claims.get("iss") != ISSUER
            or claims.get("aud") != APP_ID
            or EXACT_OWNER_OAUTH_SUBJECTS.get(claims.get("oid")) != verified_principal
            or any(type(claims.get(k)) is not int for k in ("iat", "nbf", "exp"))
            or not claims["iat"] <= t
            or not claims["nbf"] <= t < claims["exp"]
            or t - claims["iat"] > 900):
        raise StageA0OwnerIssuerDenied("STAGE_A0_ENTRA_OWNER_CLAIMS_DENIED")
    binding = {
        "service": "pmv4-stage-a0-host-bootstrap",
        "candidate_sha": candidate_sha,
        "rollback_sha": ZERO,
        "scope_sha256": reviewed_scope_sha256,
        "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
        "owner_principal": verified_principal,
    }
    if exact_owner_consent(binding) is not True:
        raise StageA0OwnerIssuerDenied("STAGE_A0_EXACT_CONFIRMATION_REQUIRED")
    signing_key = read_service_owner_signing_key(Path(signer_path))
    proof = issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id="release-" + candidate_sha[:16],
        candidate_sha=candidate_sha, rollback_sha=ZERO,
        scope_sha256=reviewed_scope_sha256,
        manifest_sha256=manifest_sha256,
        freeze_sha256=freeze_sha256,
        verified_tenant_id=TID, verified_owner_oid=claims["oid"],
        verified_principal=verified_principal,
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=signing_key,
    )
    verify_exact_owner_release(
        proof, public_key=signing_key.public_key(),
        expected_candidate_sha=candidate_sha, expected_rollback_sha=ZERO,
        expected_release_id="release-" + candidate_sha[:16],
        expected_scope_sha256=reviewed_scope_sha256,
        expected_manifest_sha256=manifest_sha256,
        expected_freeze_sha256=freeze_sha256, at=now,
    )
    request_id = "pmv4-stage-a0-" + candidate_sha[:16]
    payload = {
        "request_id": request_id,
        "source_revision": candidate_sha,
        "action": "pmv4_stage_a0_install",
        "scope_sha256": reviewed_scope_sha256,
        "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
        "signed_owner_proof": proof,
    }
    _publish_exact_request(
        Path(requests_path) / (request_id + ".json"), payload,
    )
    return {
        "status": "signed_exact_stage_a0_request_queued",
        "request_id": request_id,
        "candidate_sha": candidate_sha,
        "approval_id": proof["payload"]["approval_id"],
        "rollback_sha": ZERO,
        "standing_authority": False,
        "production_installed": False,
        "production_deployment": False,
    }
