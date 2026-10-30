"""Offline, read-only evaluation of a candidate source bundle and signed CI proof.

STAGED SOURCE ONLY: this module is not imported by the installed Release
Manager and never grants release authority, approves a release, or deploys
anything. The trust root MUST come from separately approved, root-pinned
configuration, not from the bundle or submitted attestation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class OfflineAttestationError(ValueError):
    """Fail-closed signed source evidence validation."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HEX256 = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_PAYLOAD_FIELDS = frozenset({
    "schema_version", "issuer", "repository", "source_authority",
    "candidate_sha", "protected_main_sha", "rollback_sha",
    "bundle_sha256", "generated_at", "expires_at", "checks",
})
_ALLOWED_ENVELOPE_FIELDS = frozenset({"schema_version", "signer_id", "payload", "signature_b64"})


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise OfflineAttestationError("Evidence contains invalid commit SHA")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise OfflineAttestationError("Evidence timestamp must be a UTC ISO8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OfflineAttestationError("Invalid evidence timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise OfflineAttestationError("Evidence timestamp must be UTC")
    return parsed


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """Deterministic signature input; never use a caller-provided serialized blob."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def verify_signed_evidence(
    envelope: Mapping[str, object],
    *,
    trusted_signers: Mapping[str, bytes],
    expected_candidate_sha: str,
    expected_rollback_sha: str,
    expected_repository: str,
    required_checks: tuple[str, ...],
    now: datetime,
    max_age: timedelta = timedelta(hours=24),
) -> dict[str, str]:
    """Require a pinned CI key and complete, fresh, SHA-bound protected checks.

    Returns only safe metadata; it does NOT certify a source host, material
    change authorization, CCC, release-manager approval, or rollback health.
    """
    if not isinstance(envelope, Mapping) or set(envelope) != _ALLOWED_ENVELOPE_FIELDS:
        raise OfflineAttestationError("Signed evidence envelope schema mismatch")
    if envelope.get("schema_version") != "1.0":
        raise OfflineAttestationError("Unsupported signed evidence version")
    signer = envelope.get("signer_id")
    if not isinstance(signer, str) or signer not in trusted_signers:
        raise OfflineAttestationError("Signer not present in independently trusted CI keyring")
    key = trusted_signers[signer]
    if not isinstance(key, bytes) or len(key) != 32:
        raise OfflineAttestationError("Pinned CI public key must be Ed25519")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping) or set(payload) != _ALLOWED_PAYLOAD_FIELDS:
        raise OfflineAttestationError("CI evidence payload schema mismatch")
    if payload.get("schema_version") != "1.0":
        raise OfflineAttestationError("Unsupported CI evidence version")
    signature = envelope.get("signature_b64")
    if not isinstance(signature, str):
        raise OfflineAttestationError("Missing signed CI evidence")
    try:
        raw = base64.b64decode(signature, validate=True)
        if len(raw) != 64:
            raise ValueError("Invalid Ed25519 signature size")
        Ed25519PublicKey.from_public_bytes(key).verify(raw, canonical_bytes(payload))
    except (ValueError, InvalidSignature) as exc:
        raise OfflineAttestationError("CI evidence signature could not be verified") from exc

    # Check all policy inputs after authentication, but still treat them as
    # claims by the approved CI issuer, not independent online observations.
    if payload.get("issuer") != signer or payload.get("source_authority") != "aot-approved-secondary":
        raise OfflineAttestationError("CI issuer/authority mismatch")
    if payload.get("repository") != expected_repository:
        raise OfflineAttestationError("Signed repository identity mismatch")
    if _sha(payload.get("candidate_sha")) != _sha(expected_candidate_sha):
        raise OfflineAttestationError("Signed candidate SHA mismatch")
    if _sha(payload.get("rollback_sha")) != _sha(expected_rollback_sha):
        raise OfflineAttestationError("Signed rollback SHA mismatch")
    protected_main_sha = _sha(payload.get("protected_main_sha"))
    digest = payload.get("bundle_sha256")
    if not isinstance(digest, str) or _HEX256.fullmatch(digest) is None:
        raise OfflineAttestationError("Signed source bundle digest missing")

    created, expires = _time(payload.get("generated_at")), _time(payload.get("expires_at"))
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise OfflineAttestationError("UTC clock required for release evidence")
    if (created > now + timedelta(minutes=2) or expires <= now
            or expires <= created or now - created > max_age or expires - created > max_age):
        raise OfflineAttestationError("CI evidence expired, future-dated or stale")
    checks = payload.get("checks")
    if not isinstance(checks, list) or len(checks) != len(required_checks):
        raise OfflineAttestationError("Required CI check evidence incomplete")
    if len(set(required_checks)) != len(required_checks) or not required_checks:
        raise OfflineAttestationError("Invalid required-check policy")
    actual = set()
    for item in checks:
        if not isinstance(item, dict) or set(item) != {"name", "status", "conclusion", "run_id"}:
            raise OfflineAttestationError("Invalid CI check evidence shape")
        name = item["name"]
        if (not isinstance(name, str) or name in actual
                or item["status"] != "completed" or item["conclusion"] != "success"
                or not isinstance(item["run_id"], str) or not item["run_id"].strip()):
            raise OfflineAttestationError("CI check is duplicate, pending or failed")
        actual.add(name)
    if actual != set(required_checks):
        raise OfflineAttestationError("Required CI check names mismatch")
    return {
        "candidate_sha": expected_candidate_sha,
        "rollback_sha": expected_rollback_sha,
        "protected_main_sha": protected_main_sha,
        "bundle_sha256": digest,
        "signer_id": signer,
        "source_authority": "aot-approved-secondary",
    }


def verify_source_bundle(
    bundle: Path, *, expected_bundle_sha256: str,
    candidate_sha: str, protected_main_sha: str, rollback_sha: str,
) -> None:
    """Verify complete local Git bundle, SHA, and signed protected-main ancestry.

    Runs git in a newly initialized temporary repository, never in live Jason.
    Does not fetch remote source, run build hooks, or execute bundle source.
    """
    expected_sha = _sha(candidate_sha)
    protected_sha = _sha(protected_main_sha)
    rollback_sha = _sha(rollback_sha)
    if not isinstance(expected_bundle_sha256, str) or _HEX256.fullmatch(expected_bundle_sha256) is None:
        raise OfflineAttestationError("Expected source bundle digest invalid")
    if not bundle.is_file() or bundle.is_symlink():
        raise OfflineAttestationError("Source bundle missing or symlinked")
    digest = hashlib.sha256()
    with bundle.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_bundle_sha256:
        raise OfflineAttestationError("Source bundle does not match signed digest")
    try:
        with tempfile.TemporaryDirectory(prefix="jason-ci-bundle-verify-") as td:
            subprocess.run(["git", "init", "-q", td], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=20)
            # Import bundle objects without activating any hooks or checkouts.
            subprocess.run(["git", "-C", td, "fetch", "--no-tags", str(bundle)],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, timeout=90)
            for sha in (expected_sha, protected_sha, rollback_sha):
                subprocess.run(["git", "-C", td, "cat-file", "-e", sha + "^{commit}"],
                               check=True, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, timeout=20)
            for ancestor, descendant in ((expected_sha, protected_sha),
                                         (rollback_sha, expected_sha)):
                subprocess.run(["git", "-C", td, "merge-base", "--is-ancestor",
                                ancestor, descendant], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OfflineAttestationError("Source bundle commit or protected ancestry not verified") from exc


def verify_offline_release_candidate(
    *,
    envelope: Mapping[str, object],
    bundle: Path,
    trusted_signers: Mapping[str, bytes],
    expected_candidate_sha: str,
    expected_rollback_sha: str,
    expected_repository: str,
    required_checks: tuple[str, ...],
    now: datetime,
) -> dict[str, object]:
    """Combined independent CI-signature and source-bundle integrity preflight.

    This is not a release-approval or a deployment API. Only a separate,
    approved root-controlled release authority could consume its result after
    independent CCC, exact-SHA owner approval, drift and rollback gates.
    """
    evidence = verify_signed_evidence(
        envelope, trusted_signers=trusted_signers,
        expected_candidate_sha=expected_candidate_sha,
        expected_rollback_sha=expected_rollback_sha,
        expected_repository=expected_repository,
        required_checks=required_checks,
        now=now,
    )
    verify_source_bundle(
        bundle,
        expected_bundle_sha256=evidence["bundle_sha256"],
        candidate_sha=evidence["candidate_sha"],
        protected_main_sha=evidence["protected_main_sha"],
        rollback_sha=evidence["rollback_sha"],
    )
    return {
        "source_integrity": "verified",
        "signed_ci_evidence": "verified",
        "candidate_sha": evidence["candidate_sha"],
        "signer_id": evidence["signer_id"],
        "required_check_count": len(required_checks),
        "production_approval": False,
        "production_deployed": False,
    }
