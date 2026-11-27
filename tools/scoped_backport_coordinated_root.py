#!/usr/bin/env python3
"""Root-installed coordinated stage/promotion/recovery entry point.

Uses the existing signed Owner proof format and shared consumption ledger.
Source engineering never creates a native eligibility record. Installation
and approval-issuer routing require independent exact source authorization.
No arbitrary paths, Docker arguments, credentials, or commands are accepted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import sys
import stat
import tempfile

INSTALL = Path("/usr/local/lib/jason/scoped-backport")
ENTRY = INSTALL / "tools/scoped_backport_coordinated_root.py"
if os.geteuid() == 0 and Path(__file__).resolve() == ENTRY:
    sys.path.insert(0, str(INSTALL))

from tools import scoped_backport_coordinated as co
from tools.scoped_backport_coordinated_host import CoordinatedHost, MANIFEST, PROFILE, PRIVATE, trusted_directory
from tools.scoped_backport_native_host import exact_file, root_json, atomic_root_json, utcnow
from tools.scoped_backport_release import digest, deny

AUTH = Path("/var/lib/jason/authority/scoped-backport-release")


def load_installed():
    if os.geteuid() != 0 or not sys.flags.isolated or Path(__file__).resolve() != ENTRY:
        deny("COORDINATED_INSTALLED_ROOT_ENTRY_REQUIRED")
    profile, manifest = root_json(PROFILE), root_json(MANIFEST)
    host = CoordinatedHost()
    host.enforce_installed_root_trust(profile)
    return host, co.validate_manifest(manifest), profile


PUBLIC_VIEW = Path("/etc/jason-owner-release/normal-release-policy")


def publish_normal_eligibility(record):
    if record["schema_version"] != "3.0":
        return
    trusted_directory(PUBLIC_VIEW)
    path = PUBLIC_VIEW / ("eligible-" + record["release_id"] + ".json")
    raw = json.dumps(record,sort_keys=True,separators=(",", ":")).encode()+b"\n"
    if path.exists() or path.is_symlink():
        if exact_file(path,uid=0,mode=0o644,max_size=16384) != raw:
            deny("COORDINATED_PUBLIC_ELIGIBILITY_DRIFT")
        return
    fd,temp = tempfile.mkstemp(prefix=".eligible-",dir=PUBLIC_VIEW)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.chown(temp,0,0);os.chmod(temp,0o644)
        os.link(temp,path,follow_symlinks=False)
    finally:
        os.unlink(temp)
    fd=os.open(PUBLIC_VIEW,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def stage(host, m):
    with host.release_lock(m):
        host.freshly_validate_live_scope(m)
        host.ensure_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_attempt(m)
        record = {
            "schema_version":m["schema_version"], "release_id":m["release_id"],
            "candidate_sha":m["candidate_sha"], "rollback_sha":m["rollback_sha"],
            "manifest_sha256":digest(m), "scope_sha256":m["scope_sha256"],
            **co.binding(m),
            "status":"native_coordinated_eligible_not_approved",
            "production_mutations":False,"provider_writes":False,
            "owner_approval_recorded":False,"observed_at":utcnow(),
        }
        # The immutable private offer is the authority. The public file is only
        # a display/issuer input, never trusted by the root promotion path.
        path = PRIVATE / "eligible.json"
        if path.exists():
            existing = root_json(path)
            if any(existing.get(k) != v for k,v in record.items() if k != "observed_at"):
                deny("COORDINATED_ELIGIBILITY_DRIFT")
            publish_normal_eligibility(existing)
            return existing
        atomic_root_json(path, record)
        publish_normal_eligibility(record)
        return record


def promote(host, m, profile):
    stage_record = root_json(PRIVATE / "eligible.json")
    if (stage_record.get("status") != "native_coordinated_eligible_not_approved"
            or stage_record.get("release_id") != m["release_id"]
            or stage_record.get("manifest_sha256") != digest(m)
            or stage_record.get("scope_sha256") != m["scope_sha256"]
            or stage_record.get("schema_version") != m["schema_version"]
            or stage_record.get(co.binding_field(m)) != m[co.binding_field(m)]
            or ("freeze_sha256" if m["schema_version"] == "3.0" else "release_policy_sha256") in stage_record):
        deny("COORDINATED_NATIVE_ELIGIBILITY_REQUIRED")
    # Read only this exact canonical proof envelope. The cryptographic binding,
    # actual Owner identity, expiry and one-use checks are in governed_promote.
    folder = AUTH / "owner-approvals"
    uid = pwd.getpwnam("al").pw_uid
    meta = folder.lstat()
    if folder.is_symlink() or not folder.is_dir() or meta.st_uid != uid or meta.st_mode & 0o077:
        deny("COORDINATED_OWNER_PROOF_DIRECTORY")
    proof = json.loads(exact_file(folder / (m["release_id"] + ".json"),
                                 uid=uid, mode=0o600, max_size=32768))
    if (proof.get("release_id") != m["release_id"] or proof.get("candidate_sha") != m["candidate_sha"]
            or proof.get("manifest_sha256") != digest(m)
            or proof.get("standing_authority") is not False
            or proof.get("provider_mutations_approved") is not False
            or not isinstance(proof.get("signed_owner_proof"), dict)):
        deny("COORDINATED_OWNER_PROOF_ENVELOPE")
    return co.governed_promote(m, profile, proof["signed_owner_proof"], host=host)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("stage", "promote", "recover"))
    args = p.parse_args()
    host, m, profile = load_installed()
    if args.action == "stage":
        result = stage(host,m)
    elif args.action == "promote":
        result = promote(host,m,profile)
    elif not host._journal_path(m).exists():
        result = {"status":"no_coordinated_journal"}
    else:
        result = host.recover(m)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
