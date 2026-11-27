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
import re
import sys
import stat
import tempfile

INSTALL = Path("/usr/local/lib/jason/scoped-backport")
ENTRY = INSTALL / "tools/scoped_backport_coordinated_root.py"
if os.geteuid() == 0 and Path(__file__).resolve() == ENTRY:
    sys.path.insert(0, str(INSTALL))

from tools import scoped_backport_coordinated as co
from tools.scoped_backport_coordinated_host import CoordinatedHost, MANIFEST, PROFILE, PRIVATE, trusted_directory, POLICY, RESOLVED, active_staged_offer, validate_staged_offer, verify_installed_policy
from tools.scoped_backport_native_host import exact_file, root_json, atomic_root_json, root_directory, utcnow
from tools.scoped_backport_release import digest, deny

AUTH = Path("/var/lib/jason/authority/scoped-backport-release")


def load_installed():
    if os.geteuid() != 0 or not sys.flags.isolated or Path(__file__).resolve() != ENTRY:
        deny("COORDINATED_INSTALLED_ROOT_ENTRY_REQUIRED")
    policy = root_json(POLICY)
    if policy.get("schema_version") == "3.0":
        offer = active_staged_offer()
        if offer is None:
            deny("COORDINATED_ROOT_STAGED_OFFER_REQUIRED")
        profile, manifest = offer["profile"], offer["manifest"]
    else:
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


def eligibility_record(m):
    return {
        "schema_version": m["schema_version"], "release_id": m["release_id"],
        "candidate_sha": m["candidate_sha"], "rollback_sha": m["rollback_sha"],
        "manifest_sha256": digest(m), "scope_sha256": m["scope_sha256"],
        **co.binding(m), "status": "native_coordinated_eligible_not_approved",
        "production_mutations": False, "provider_writes": False,
        "owner_approval_recorded": False, "observed_at": utcnow(),
    }


def exact_public_offer(release_id):
    if not isinstance(release_id, str) or not re.fullmatch(r"release-[0-9a-f]{16}", release_id):
        deny("COORDINATED_STAGE_RELEASE_ID")
    folder = AUTH / "offers"
    uid = pwd.getpwnam("al").pw_uid
    meta = folder.lstat()
    if folder.is_symlink() or not stat.S_ISDIR(meta.st_mode) or meta.st_uid != uid or stat.S_IMODE(meta.st_mode) != 0o700:
        deny("COORDINATED_STAGE_OFFER_DIRECTORY")
    data = json.loads(exact_file(folder / (release_id + ".json"), uid=uid, mode=0o600, max_size=2_000_000))
    if not isinstance(data, dict) or set(data) != {"schema_version", "manifest", "profile", "review_source_sha"} or data["schema_version"] != "3.0":
        deny("COORDINATED_STAGE_OFFER_SCHEMA")
    m = co.validate_manifest(data["manifest"])
    p = co.validate_profile(data["profile"], m)
    if m["schema_version"] != "3.0" or m["release_id"] != release_id:
        deny("COORDINATED_STAGE_OFFER_SCOPE")
    return m, p, data["review_source_sha"]


def persist_reviewed_offer(host, m, profile, review_source_sha):
    # A static, independently installed code policy is reused for successive
    # exact reviewed scopes. No caller-supplied path can select root code.
    # Every active offer and historical receipt is private and root-owned.
    host.bind_for_stage(m, profile, review_source_sha)
    with host.release_lock(m):
        host.freshly_validate_live_scope(m)
        host.ensure_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_attempt(m)
        prior = active_staged_offer()
        if prior is not None and prior["manifest"]["release_id"] != m["release_id"]:
            old = prior["manifest"]
            journal = host._journal_path(old)
            proof = AUTH / "owner-approvals" / (old["release_id"] + ".json")
            if os.path.lexists(journal):
                receipt = root_json(journal)
                if (receipt.get("outcome") not in RESOLVED
                        or receipt.get("manifest_sha256") != digest(old)
                        or receipt.get("scope_sha256") != old["scope_sha256"]):
                    deny("COORDINATED_PRIOR_OFFER_NOT_RESOLVED")
            elif os.path.lexists(proof):
                deny("COORDINATED_PRIOR_SIGNED_OFFER_PENDING")
        folder = PRIVATE / "offers"
        root_directory(folder)
        path = folder / (m["release_id"] + ".json")
        expected = validate_staged_offer({
            "schema_version": "3.0", "manifest": m, "profile": profile,
            "review_source_sha": review_source_sha, "eligibility": eligibility_record(m),
        })
        if os.path.lexists(path):
            offer = validate_staged_offer(root_json(path, max_size=2_000_000))
            if any(offer[k] != expected[k] for k in ("manifest", "profile", "review_source_sha")):
                deny("COORDINATED_HISTORICAL_OFFER_CHANGED")
        else:
            offer = expected
            atomic_root_json(path, offer)
        if prior is not None and prior["manifest"]["release_id"] != m["release_id"]:
            # Remove only the old read-only eligibility projection. The exact
            # root-private offer and every signature/journal stay immutable.
            old_view = PUBLIC_VIEW / ("eligible-" + prior["manifest"]["release_id"] + ".json")
            if os.path.lexists(old_view):
                projected = json.loads(exact_file(old_view, uid=0, mode=0o644, max_size=16384))
                if projected != prior["eligibility"]:
                    deny("COORDINATED_PRIOR_PUBLIC_ELIGIBILITY_CHANGED")
                old_view.unlink()
                fd = os.open(PUBLIC_VIEW, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
        pointer = PRIVATE / "active-offer.json"
        data = {"schema_version": "3.0", "release_id": m["release_id"], "offer_sha256": digest(offer)}
        if not os.path.lexists(pointer):
            atomic_root_json(pointer, data)
        elif root_json(pointer) != data:
            atomic_root_json(pointer, data, replace=True)
        publish_normal_eligibility(offer["eligibility"])
        return offer["eligibility"]


def stage_reviewed_normal(release_id):
    if os.geteuid() != 0 or not sys.flags.isolated or Path(__file__).resolve() != ENTRY:
        deny("COORDINATED_INSTALLED_ROOT_ENTRY_REQUIRED")
    m, profile, review_source_sha = exact_public_offer(release_id)
    return persist_reviewed_offer(CoordinatedHost(), m, profile, review_source_sha)


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
    if host is not None and getattr(host, "policy", {}).get("schema_version") == "3.0":
        offer = active_staged_offer()
        if offer is None or offer["manifest"] != m or offer["profile"] != profile:
            deny("COORDINATED_ROOT_STAGED_OFFER_REQUIRED")
        stage_record = offer["eligibility"]
    else:
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


def scheduled_approved(host, m, profile):
    """Execute only the exact root-admitted offer with its existing explicit
    signed Owner decision. Never select a candidate, issue approval, or retry
    an interrupted mutation. The same native promotion function revalidates
    source, proof, consumption, lock, breaker, drift and rollback.
    """
    if m["schema_version"] != "3.0":
        return {"status": "legacy_offer_not_scheduled"}
    journal = host._journal_path(m)
    if os.path.lexists(journal):
        prior = root_json(journal)
        if (prior.get("manifest_sha256") != digest(m)
                or prior.get("scope_sha256") != m["scope_sha256"]):
            deny("COORDINATED_SCHEDULED_JOURNAL_SCOPE")
        if prior.get("outcome") in RESOLVED:
            return {"status": "resolved_prior_attempt_no_action"}
        return {"status": "interrupted_attempt_recovery_only"}
    proof = AUTH / "owner-approvals" / (m["release_id"] + ".json")
    if not os.path.lexists(proof):
        return {"status": "exact_owner_decision_not_present"}
    return promote(host, m, profile)


def run_scheduled(action):
    # A missing successor policy is not an implicit authorization and must
    # not interfere with the unchanged legacy v1 unit. Any present but
    # invalid successor policy is a hard denial through load_installed().
    if action not in ("promote-approved", "recover-scheduled"):
        deny("COORDINATED_SCHEDULED_ACTION")
    if os.geteuid() != 0 or not sys.flags.isolated or Path(__file__).resolve() != ENTRY:
        deny("COORDINATED_INSTALLED_ROOT_ENTRY_REQUIRED")
    try:
        POLICY.lstat()
    except FileNotFoundError:
        return {"status": "coordinated_successor_not_installed"}
    policy = root_json(POLICY)
    if policy.get("schema_version") == "3.0" and active_staged_offer() is None:
        verify_installed_policy()
        for journal in (PRIVATE / "transactions").glob("release-*.json"):
            if root_json(journal).get("outcome") not in RESOLVED:
                deny("COORDINATED_UNRESOLVED_JOURNAL_WITHOUT_ACTIVE_OFFER")
        return {"status": "no_root_reviewed_active_offer"}
    host,m,profile=load_installed()
    if action == "promote-approved":
        return scheduled_approved(host,m,profile)
    if not os.path.lexists(host._journal_path(m)):
        return {"status":"no_coordinated_journal"}
    return host.recover(m)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("stage", "promote", "recover",
                                      "promote-approved", "recover-scheduled"))
    p.add_argument("--release-id")
    args = p.parse_args()
    if args.release_id is not None:
        if args.action != "stage":
            p.error("--release-id is permitted only for exact native stage")
        print(json.dumps(stage_reviewed_normal(args.release_id), sort_keys=True))
        return 0
    if args.action in ("promote-approved", "recover-scheduled"):
        print(json.dumps(run_scheduled(args.action), sort_keys=True))
        return 0
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
