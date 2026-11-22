#!/usr/bin/env python3
"""Immutable, root-only request consumer for a signed scoped-backport release.

NOT INSTALLED. It MUST run as root from its exact source-pinned installed path
through the dedicated systemd worker. It never treats an al-owned request as
Owner approval, and stage never starts a production deployment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
from typing import Any, Mapping

# Trust begins only at the future independently root-pinned installation.
INSTALLED_ROOT = Path("/usr/local/lib/jason/scoped-backport")
INSTALLED_ENTRY = INSTALLED_ROOT / "tools/scoped_backport_native_root.py"
if os.geteuid() == 0 and Path(__file__).resolve() == INSTALLED_ENTRY:
    sys.path.insert(0, str(INSTALLED_ROOT))

from tools.scoped_backport_release import (
    GROUP_BIND_DESTINATIONS, ENV, ScopedBackportDenied, canonical, deny,
    make_offer, validate_offer, source_admission, RELEASE_MANIFEST, _git,
    governed_promote,
)
from tools.scoped_backport_native_host import (
    NativeScopedBackportHost, ROOT_STATE, NATIVE, APPROLE_PATHS,
    atomic_root_json, root_json, root_directory, exact_file,
    run, utcnow, SOURCE_REPO,
)
from tools.scoped_backport_release_request import (
    ACTIONS, SPOOL, installed_attestation, request,
)

AUTH_ROOT = Path("/var/lib/jason/authority/scoped-backport-release")
ID = re.compile(r"^release-[a-f0-9]{16}$")
REQUEST_ID = re.compile(r"^[a-f0-9]{32}$")
HASH = re.compile(r"^[a-f0-9]{64}$")


def _public_dir(name: str) -> Path:
    if name not in ("offers", "eligibility", "owner-approvals", "results",
                     "requests", "processed"):
        deny("PUBLIC_RELEASE_DIRECTORY_NOT_ALLOWED")
    target = AUTH_ROOT / name
    if target.is_symlink() or not target.is_dir():
        deny("PUBLIC_SPOOL_MISSING")
    uid = pwd.getpwnam("al").pw_uid
    m = target.stat()
    if m.st_uid != uid or stat.S_IMODE(m.st_mode) != 0o700:
        deny("PUBLIC_SPOOL_UNTRUSTED")
    return target


def _public_json(name: str, release_id: str) -> dict:
    if not ID.fullmatch(release_id):
        deny("PUBLIC_RELEASE_ID_INVALID")
    path = _public_dir(name) / (release_id + ".json")
    raw = exact_file(path, uid=pwd.getpwnam("al").pw_uid,
                     mode=0o600, max_size=32768)
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ScopedBackportDenied("SCOPED_BACKPORT_PUBLIC_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        deny("PUBLIC_JSON_NOT_OBJECT")
    return obj


def _publish_public(name: str, release_id: str, payload: Mapping) -> None:
    expected = REQUEST_ID if name == "results" else ID
    if not expected.fullmatch(release_id):
        deny("PUBLIC_RECEIPT_ID_INVALID")
    folder = _public_dir(name)
    path = folder / (release_id + ".json")
    if path.exists() or path.is_symlink():
        deny("PUBLIC_RELEASE_RECEIPT_REPLAY")
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        owner = pwd.getpwnam("al")
        os.chown(path, owner.pw_uid, owner.pw_gid, follow_symlinks=False)
    finally:
        # os.fdopen() owns the descriptor once entered. Never retry a
        # partially published release offer silently.
        pass


def _read_request(request_id: str) -> dict[str, Any]:
    if not REQUEST_ID.fullmatch(request_id):
        deny("ROOT_REQUEST_ID_INVALID")
    folder = _public_dir("requests")
    path = folder / (request_id + ".json")
    raw = exact_file(path, uid=pwd.getpwnam("al").pw_uid,
                     mode=0o600, max_size=4096)
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ScopedBackportDenied("SCOPED_BACKPORT_ROOT_REQUEST_JSON_INVALID") from exc
    if not isinstance(doc, dict) or doc.get("request_id") != request_id:
        deny("ROOT_REQUEST_ID_MISMATCH")
    return doc


def _offer_from_protected_source(host: NativeScopedBackportHost,
                                 main_sha: str) -> dict[str, Any]:
    source = source_admission(host.repo, trusted_main_sha=main_sha)
    manifest = json.loads(_git(host.repo, "show", main_sha + ":" + RELEASE_MANIFEST))
    offer = make_offer(manifest, main_sha=main_sha)
    if (source["candidate_sha"] != offer["candidate_sha"]
            or source["manifest_sha256"] != offer["manifest_sha256"]
            or source["scope_sha256"] != offer["scope_sha256"]):
        deny("LIVE_SCOPED_SOURCE_OFFER_MISMATCH")
    return offer


def _verify_typed_request(doc: Mapping, offer: Mapping) -> str:
    action = str(doc.get("action") or "")
    if action not in ACTIONS:
        deny("NATIVE_BACKPORT_REQUEST_ACTION")
    # request() generates a fresh ID. Compare all invariant fields except
    # the random ID, plus the exact source / offer hash from protected root.
    if action != "scoped_backport_stage":
        if doc.get("offer_sha256") != sha256(canonical(offer)).hexdigest():
            deny("NATIVE_BACKPORT_OFFER_HASH_MISMATCH")
    payload = request(action, offer, offer_sha256=doc.get("offer_sha256"))
    adjusted = dict(payload, request_id=doc.get("request_id"))
    if dict(doc) != adjusted:
        deny("NATIVE_BACKPORT_REQUEST_SCOPE_DRIFT")
    return action


def _native_preflight(offer: Mapping, host: NativeScopedBackportHost) -> None:
    mounts = host._group_mounts()
    for name, key in (
        ("jason-runtime", "runtime_image_id"),
        ("jason-mcp-pilot", "mcp_image_id"),
    ):
        argv = [
            "python3", str(NATIVE), "--preflight", "--live", name,
            "--image", offer[key],
            "--rollback", name + "-rollback-scoped-" + offer["candidate_sha"][:12],
            "--source-revision", offer["candidate_sha"],
            "--health-url", ("http://127.0.0.1:8080/healthz"
                             if name == "jason-runtime" else
                             "http://127.0.0.1:8000/healthz"),
            "--harden", "--set-env",
            "JASON_M365_GROUP_ADMIN_PROFILE=" + ENV["JASON_M365_GROUP_ADMIN_PROFILE"],
        ]
        for bind in mounts:
            argv.extend(("--add-readonly-bind", bind))
        result = run(*argv, timeout=60, allow_failure=True)
        if result.returncode or b"PREFLIGHT=PASS" not in result.stdout:
            deny("NATIVE_SCOPED_DEPLOY_PREFLIGHT_FAILED")


def _offer_record(offer: Mapping, *, stage_receipt: Mapping) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "release_kind": "governed_scoped_backport",
        "release_id": offer["release_id"],
        "candidate_sha": offer["candidate_sha"],
        "rollback_sha": offer["rollback_sha"],
        "scope_sha256": offer["scope_sha256"],
        "manifest_sha256": offer["manifest_sha256"],
        "freeze_sha256": offer["freeze_sha256"],
        "runtime_image_id": offer["runtime_image_id"],
        "mcp_image_id": offer["mcp_image_id"],
        "rollback_runtime_image_id": offer["rollback_runtime_image_id"],
        "rollback_mcp_image_id": offer["rollback_mcp_image_id"],
        "status": "native_scoped_preproduction_eligible_not_approved",
        "stage_evidence_sha256": sha256(canonical(stage_receipt)).hexdigest(),
        "owner_approval_recorded": False,
        "production_mutations": False,
        "provider_writes": False,
        "owner_approval_is_one_use": True,
        "recorded_at": utcnow(),
    }


def stage(host: NativeScopedBackportHost, offer: dict) -> dict:
    """Only the immutable root handler may create a separate scoped record.

    This is NOT the ordinary Release Manager's production_eligible record.
    """
    with host.release_lock(offer):
        host.freshly_validate_live_scope(offer)
        host.ensure_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_attempt(offer)
        _native_preflight(offer, host)
        # Source-only Docker rollback rehearsal already tested this exact
        # digest pair. The native root preflights and image checks revalidate
        # the actual candidate/rollback images before offering Owner approval.
        receipt = {
            "schema_version": "1.0", "release_id": offer["release_id"],
            "candidate_sha": offer["candidate_sha"],
            "rollback_sha": offer["rollback_sha"],
            "scope_sha256": offer["scope_sha256"],
            "manifest_sha256": offer["manifest_sha256"],
            "runtime_image_id": offer["runtime_image_id"],
            "mcp_image_id": offer["mcp_image_id"],
            "preflight": "both_native_image_preflights_pass",
            "observed_at": utcnow(),
            "production_mutations": False,
            "provider_writes": False,
        }
        path = host.root / "offers" / (offer["release_id"] + ".json")
        # One canonical eligibility record across the root-private and
        # public receipt; a second timestamp can otherwise differ and make
        # a valid later signed promotion fail its equality gate.
        record = _offer_record(offer, stage_receipt=receipt)
        atomic_root_json(path, {"source_offer": offer, "stage_receipt": receipt,
                                "eligible": record})
        # Public offer/status is display material, never release authority.
        _publish_public("offers", offer["release_id"], offer)
        _publish_public("eligibility", offer["release_id"], record)
        return record


def promote(host: NativeScopedBackportHost, offer: dict) -> dict:
    """Execute only after a separately OAuth-verified exact signed Owner proof."""
    root_record = root_json(host.root / "offers" / (offer["release_id"] + ".json"),
                            max_size=32768)
    stage_doc = root_record.get("eligible") or {}
    if (root_record.get("source_offer") != offer
            or stage_doc.get("status") != "native_scoped_preproduction_eligible_not_approved"
            or stage_doc.get("release_id") != offer["release_id"]
            or stage_doc.get("manifest_sha256") != offer["manifest_sha256"]):
        deny("ROOT_SCOPED_OFFER_NOT_ELIGIBLE")
    if _public_json("eligibility", offer["release_id"]) != stage_doc:
        deny("PUBLIC_SCOPED_ELIGIBILITY_REPLACED")
    signed = _public_json("owner-approvals", offer["release_id"])
    if (signed.get("release_id") != offer["release_id"]
            or signed.get("candidate_sha") != offer["candidate_sha"]
            or signed.get("manifest_sha256") != offer["manifest_sha256"]
            or signed.get("standing_authority") is not False
            or not isinstance(signed.get("signed_owner_proof"), dict)):
        deny("ROOT_SCOPED_OWNER_PROOF_NOT_EXACT")
    # All authoritative cryptographic checks, live source revalidation,
    # durable one-use consumption, production lock, freeze and exact paired
    # rollback are performed by governed_promote.
    return governed_promote(offer, signed["signed_owner_proof"], host=host)


def dispatch_one(request_id: str) -> dict:
    if os.geteuid() != 0 or Path(__file__).resolve(strict=True) != INSTALLED_ENTRY:
        deny("INSTALLED_NATIVE_ROOT_WORKER_REQUIRED")
    host = NativeScopedBackportHost()
    host.enforce_installed_root_trust()
    doc = _read_request(request_id)
    main = str(doc.get("protected_main_sha") or "")
    offer = _offer_from_protected_source(host, main)
    action = _verify_typed_request(doc, offer)
    if action == "scoped_backport_stage":
        result = stage(host, offer)
    elif action == "scoped_backport_promote":
        result = promote(host, offer)
    else:
        deny("RECOVERY_REQUIRES_SEPARATE_EXACT_CRASH_HANDLER")
    # A root-origin result does not expand privileges; the Owner still needs
    # an independently verified signature and provider writes remain separate.
    _publish_public("results", request_id, {
        "schema_version": "1.0", "request_id": request_id,
        "release_id": offer["release_id"], "status": result["status"],
        "production_mutations": result.get("status") == "production_pair_verified",
        "recorded_at": utcnow(),
    })
    return result


def bounded_stage_denial_code(exc: BaseException) -> str:
    """No caller-controlled error detail crosses from root to operator."""
    if isinstance(exc, ScopedBackportDenied):
        msg = str(exc)
        if re.fullmatch(r"SCOPED_BACKPORT_[A-Z0-9_]{2,96}", msg):
            return msg
    return "SCOPED_BACKPORT_UNCLASSIFIED_DENIAL"


def probe_stage_read_only() -> dict:
    """Prove native admission and Docker preflight with zero release mutation.

    A root provenance attestation and existing production transaction lock
    are required, but the breaker is deliberately NOT revalidated/closed by
    this diagnostic. Normal stage still requires a closed breaker and fresh
    independently clean drift.
    """
    if os.geteuid() != 0 or Path(__file__).resolve(strict=True) != INSTALLED_ENTRY:
        deny("INSTALLED_NATIVE_ROOT_WORKER_REQUIRED")
    host = NativeScopedBackportHost()
    host.enforce_installed_root_trust()
    offer = _offer_from_protected_source(
        host, host.policy["trusted_source_sha"])
    with host.release_lock(offer):
        host.freshly_validate_live_scope(offer)
        _native_preflight(offer, host)
    return {
        "schema_version": "1.0",
        "status": "scoped_native_readonly_stage_preflight_pass",
        "release_id": offer["release_id"],
        "candidate_sha": offer["candidate_sha"],
        "protected_main_sha": offer["protected_main_sha"],
        "production_mutations": False,
        "provider_writes": False,
        "release_eligibility_created": False,
        "owner_approval_recorded": False,
    }


def drain() -> dict:
    """Consume bounded one-use request files; no blind side-effect retry."""
    if os.geteuid() != 0 or Path(__file__).resolve(strict=True) != INSTALLED_ENTRY:
        deny("INSTALLED_NATIVE_ROOT_WORKER_REQUIRED")
    host = NativeScopedBackportHost()
    host.enforce_installed_root_trust()
    source = _public_dir("requests")
    completed = _public_dir("processed")
    queued = sorted(source.glob("*.json"))
    if len(queued) > 30:
        deny("NATIVE_BACKPORT_QUEUE_CAPACITY_EXCEEDED")
    results = []
    for path in queued:
        if path.is_symlink() or not REQUEST_ID.fullmatch(path.stem):
            deny("NATIVE_BACKPORT_QUEUE_UNTRUSTED_FILE")
        item = path.stem
        if (completed / path.name).exists():
            deny("NATIVE_BACKPORT_QUEUE_REPLAY_FILE")
        try:
            result = dispatch_one(item)
            status = "handled_" + str(result.get("status"))
        except (ScopedBackportDenied, PermissionError, ValueError,
                OSError, subprocess.SubprocessError) as exc:
            # Report only exact, bounded *constant* gate codes. No raw
            # provider errors, paths, stdout, OAuth tokens or secrets.
            status = "denied_" + type(exc).__name__
            denial = bounded_stage_denial_code(exc)
        else:
            denial = None
        receipt = {
            "schema_version": "1.0", "request_id": item,
            "status": status, "processed_at": utcnow(),
            "owner_approval_issued": False,
            "provider_mutations_approved": False,
            "denial_code": denial,
        }
        atomic_root_json(host.root / "requests" / (item + ".json"), receipt)
        os.replace(path, completed / path.name)
        results.append(receipt)
    return {"status": "bounded_scoped_request_drain", "count": len(results),
            "results": results}


def main() -> int:
    args = argparse.ArgumentParser()
    group = args.add_mutually_exclusive_group(required=True)
    group.add_argument("--request-id")
    group.add_argument("--drain", action="store_true")
    group.add_argument("--probe-stage", action="store_true")
    o = args.parse_args()
    if not sys.flags.isolated:
        deny("ROOT_WORKER_ISOLATED_PYTHON_REQUIRED")
    if o.probe_stage:
        try:
            result = probe_stage_read_only()
        except (ScopedBackportDenied, PermissionError, ValueError,
                OSError, subprocess.SubprocessError) as exc:
            result = {
                "status": "scoped_native_readonly_stage_preflight_denied",
                "denial_code": bounded_stage_denial_code(exc),
                "production_mutations": False,
                "provider_writes": False,
            }
            print(json.dumps(result, sort_keys=True))
            return 2
    elif o.drain:
        result = drain()
    else:
        result = dispatch_one(o.request_id)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
