#!/usr/bin/env python3
"""Low-privilege typed request to an independently installed native root handler.

No root handler currently exists for this profile. Request files are NOT
authority, signed Owner approval, a release record, or deployment. The root
worker must independently prove its own source, offer, CI, rollback image
pair, Owner signature, locks, freeze, protected services and audit.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
from typing import Mapping
from uuid import uuid4

from tools.scoped_backport_release import validate_offer, ScopedBackportDenied, deny

ROOT_HANDLER = Path("/usr/local/lib/jason/scoped-backport/host_request_worker.py")
ROOT_POLICY = Path("/etc/jason-owner-release/scoped-backport-installed.json")
SPOOL = Path("/var/lib/jason/authority/scoped-backport-release/requests")
ACTIONS = frozenset({"scoped_backport_stage", "scoped_backport_promote",
                     "scoped_backport_recover"})
HEX = re.compile(r"^[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
IDENTITY = re.compile(r"^release-[0-9a-f]{16}$")


def _root_file(path: Path, *, max_bytes=200000) -> bytes:
    if path.is_symlink() or not path.is_file():
        deny("ROOT_HANDLER_OR_POLICY_UNAVAILABLE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_nlink != 1
                or not 1 <= info.st_size <= max_bytes):
            deny("ROOT_HANDLER_OR_POLICY_UNTRUSTED")
        raw = os.read(fd, max_bytes + 1)
        if len(raw) != info.st_size:
            deny("ROOT_HANDLER_OR_POLICY_CHANGED")
        return raw
    finally:
        os.close(fd)


def installed_attestation(*, handler: Path = ROOT_HANDLER,
                          policy: Path = ROOT_POLICY) -> dict[str, str]:
    """No installation or authority is inferred from a caller-controlled path."""
    try:
        doc = json.loads(_root_file(policy, max_bytes=8192))
    except ScopedBackportDenied:
        raise
    except (ValueError, OSError) as exc:
        raise ScopedBackportDenied("SCOPED_BACKPORT_ROOT_POLICY_UNREADABLE") from exc
    expected = {"schema_version", "profile", "trusted_source_sha",
                "root_handler_sha256", "native_root_control_supported",
                "automatic_rollback_recovery_installed",
                "exact_signed_owner_approval_required"}
    if (not isinstance(doc, dict) or set(doc) != expected
            or doc["schema_version"] != "1.0"
            or doc["profile"] != "governed-scoped-backport-v1"
            or not isinstance(doc["trusted_source_sha"], str)
            or not SHA.fullmatch(doc["trusted_source_sha"])
            or not isinstance(doc["root_handler_sha256"], str)
            or not HEX.fullmatch(doc["root_handler_sha256"])
            or doc["native_root_control_supported"] is not True
            or doc["automatic_rollback_recovery_installed"] is not True
            or doc["exact_signed_owner_approval_required"] is not True):
        deny("ROOT_HANDLER_INSTALL_SCOPE_INVALID")
    if sha256(_root_file(handler)).hexdigest() != doc["root_handler_sha256"]:
        deny("ROOT_HANDLER_SHA256_DRIFT")
    return doc


def request(action: str, offer: Mapping, *,
            offer_sha256: str | None = None) -> dict:
    o = validate_offer(offer)
    if action not in ACTIONS:
        deny("ROOT_ACTION_NOT_ALLOWED")
    if action == "scoped_backport_stage":
        if offer_sha256 is not None:
            deny("STAGE_HAS_NO_PREAPPROVED_OFFER")
    elif not isinstance(offer_sha256, str) or not HEX.fullmatch(offer_sha256):
        deny("EXACT_OFFER_SHA256_REQUIRED")
    payload = {
        "schema_version": "1.0", "action": action,
        "request_id": uuid4().hex, "release_id": o["release_id"],
        "candidate_sha": o["candidate_sha"],
        "rollback_sha": o["rollback_sha"],
        "scope_sha256": o["scope_sha256"],
        "manifest_sha256": o["manifest_sha256"],
        "protected_main_sha": o["protected_main_sha"],
    }
    if action != "scoped_backport_stage":
        payload["offer_sha256"] = offer_sha256
    return payload


def aot_operator_uid() -> int:
    """Only the installed AOT host operator may own the request spool."""
    try:
        return pwd.getpwnam("al").pw_uid
    except KeyError:
        deny("HOST_OPERATOR_NOT_FOUND")


def submit(payload: Mapping, *, handler: Path = ROOT_HANDLER,
           policy: Path = ROOT_POLICY, spool: Path = SPOOL) -> dict:
    """Queue only after independent root trust installation; never auto-create."""
    if not isinstance(payload, Mapping):
        deny("ROOT_REQUEST_INVALID")
    required = {"schema_version", "action", "request_id", "release_id",
                "candidate_sha", "rollback_sha", "scope_sha256",
                "manifest_sha256", "protected_main_sha"}
    if payload.get("action") not in ACTIONS:
        deny("ROOT_REQUEST_ACTION_INVALID")
    if payload["action"] != "scoped_backport_stage":
        required.add("offer_sha256")
    if (set(payload) != required or payload["schema_version"] != "1.0"
            or not isinstance(payload["request_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", payload["request_id"]) is None
            or not isinstance(payload["release_id"], str)
            or IDENTITY.fullmatch(payload["release_id"]) is None
            or any(not isinstance(payload[k], str) or not SHA.fullmatch(payload[k])
                   for k in ("candidate_sha", "rollback_sha", "protected_main_sha"))
            or payload["release_id"] != "release-" + payload["candidate_sha"][:16]
            or any(not isinstance(payload[k], str) or not HEX.fullmatch(payload[k])
                   for k in ("scope_sha256", "manifest_sha256"))
            or ("offer_sha256" in required and
                (not isinstance(payload["offer_sha256"], str)
                 or not HEX.fullmatch(payload["offer_sha256"])))):
        deny("ROOT_REQUEST_SCHEMA_OR_BINDING_INVALID")
    installed_attestation(handler=handler, policy=policy)
    if spool.is_symlink() or not spool.is_dir():
        deny("ROOT_REQUEST_SPOOL_NOT_INSTALLED")
    uid = aot_operator_uid()
    mode = stat.S_IMODE(spool.stat().st_mode)
    if spool.stat().st_uid != uid or mode != 0o700:
        deny("ROOT_REQUEST_SPOOL_UNTRUSTED")
    files = tuple(spool.iterdir())
    if len(files) > 80 or any(not p.is_file() or p.is_symlink() for p in files):
        deny("ROOT_REQUEST_SPOOL_CAPACITY_OR_DRIFT")
    dest = spool / (payload["request_id"] + ".json")
    if dest.exists() or dest.is_symlink():
        deny("ROOT_REQUEST_REPLAY")
    raw = json.dumps(dict(payload), separators=(",", ":"),
                     sort_keys=True).encode() + b"\n"
    if len(raw) > 4096:
        deny("ROOT_REQUEST_SIZE")
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    return {
        "status": "queued_for_independent_root_validation_not_approved",
        "request_id": payload["request_id"],
        "release_id": payload["release_id"],
        "action": payload["action"],
        "production_mutations": False,
        "native_release_record_created": False,
        "owner_approval_recorded": False,
    }
