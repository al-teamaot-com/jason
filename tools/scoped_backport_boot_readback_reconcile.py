#!/usr/bin/env python3
"""Exact signed maintenance of boot-recreated Runtime readback.

Uses the existing coordinated release trust, locks, historical proof, signer,
one-use ledger and native byte replacement. No deployment, grant, policy change,
container restart, or breaker transition. Run only from a sealed reviewed bundle.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from uuid import uuid4

NATIVE = Path("/usr/local/lib/jason/scoped-backport")
BUNDLE = Path(__file__).absolute().parents[1]
if __name__ == "__main__":
    for path in (Path(__file__).absolute(), BUNDLE / "tools", BUNDLE, *BUNDLE.parents):
        s = path.lstat()
        if path.is_symlink() or s.st_uid != 0 or s.st_mode & 0o022:
            raise SystemExit("BOOT_READBACK_UNTRUSTED_SOURCE_BUNDLE")
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit("BOOT_READBACK_ISOLATED_SOURCE_REQUIRED")
    sys.path[:0] = [str(NATIVE), str(BUNDLE)]

from tools import scoped_backport_coordinated_host as live
from tools import scoped_backport_coordinated_root as dispatcher
from tools import scoped_backport_component_readback as readback
from tools.scoped_backport_release import canonical, digest, deny, require_hash, require_sha
from tools.scoped_backport_four_unit_drift_reconcile import (
    atomic_exact_root_file, require_ci_green, restore_attempted_root_files,
)
from implementation.kernel import signed_owner_release_v2 as signing

ACTION = "reconcile_boot_recreated_runtime_identity"
DESCRIPTION = ("change only runtime container_id; preserve images, revisions, original "
               "signed release, all other evidence and controls; native breaker revalidation required")
RUNTIME = "jason-runtime"
LEDGER = live.PRIVATE / "controller-maintenance"
CONSUMED = live.ROOT_STATE / "consumed-owner-approvals"
OFFER = BUNDLE / "boot-readback-maintenance-offer.json"
FILES = ("tools/scoped_backport_boot_readback_reconcile.py",
         "tools/scoped_backport_four_unit_drift_reconcile.py")
CONFIRM = "AUTHORIZE-EXACT-BOOT-READBACK-RECOVERY"
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")


def need(ok, code):
    if not ok:
        deny("BOOT_READBACK_" + code)


def make_plan(before, historical, actual, fingerprints, *, host_revision,
              policy_sha256, manifest, consumed):
    """Pure reduction of independently observed, root-custodied evidence."""
    old = readback.validate(json.loads(before))
    j = json.loads(historical)
    need(old["schema_version"] == manifest["schema_version"] == "3.0",
         "NORMAL_MODE_REQUIRED")
    need(j["outcome"] == "production_components_verified"
         and j["mutation_attempted"] is True
         and j["proposed_readback"] == old
         and j["release_id"] == old["release_id"] == manifest["release_id"]
         and j["manifest_sha256"] == old["manifest_sha256"] == digest(manifest)
         and j["scope_sha256"] == old["scope_sha256"] == manifest["scope_sha256"]
         and j["candidate_ids"] == {k: v["container_id"] for k, v in old["components"].items()},
         "ORIGINAL_TRANSACTION_MISMATCH")
    need(consumed["schema_version"] == "2.0"
         and consumed["one_use"] is True
         and consumed["release_id"] == old["release_id"]
         and consumed["approval_id"] == j["approval_id"], "ORIGINAL_APPROVAL_MISMATCH")
    need(set(actual) == set(readback.COMPONENTS)
         and fingerprints == j.get("candidate_configs", j["original_configs"]),
         "CONFIGURATION_DRIFT")
    need(all(actual[k] == old["components"][k] for k in actual if k != RUNTIME),
         "OTHER_COMPONENT_DRIFT")
    a, b = old["components"][RUNTIME], actual[RUNTIME]
    need(a["image_id"] == b["image_id"] and a["revision"] == b["revision"]
         and a["container_id"] != b["container_id"], "RUNTIME_SCOPE")
    new = deepcopy(old)
    new["components"][RUNTIME]["container_id"] = b["container_id"]
    need(readback.verify(new, actual, host_revision=host_revision,
                         release_policy_sha256=policy_sha256) == new,
         "PROPOSED_NATIVE_VERIFICATION")
    plan = {"action": ACTION, "release_id": old["release_id"],
            "approved_record_sha256": sha256(before).hexdigest(),
            "transaction_sha256": sha256(historical).hexdigest(),
            "old_runtime": a, "new_runtime": b,
            "proposed_readback_canonical_sha256": readback.digest(new),
            "host_revision": host_revision, "policy_sha256": policy_sha256,
            "scope": DESCRIPTION}
    return plan, new


def git(*args):
    return subprocess.run(
        ["/usr/bin/git", "-C", str(live.REPO), "-c", "core.hooksPath=/dev/null", *args],
        env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True, check=True, timeout=30).stdout


def verify_source(installer, reviewed, rollback):
    for value in (installer, reviewed, rollback):
        require_sha(value, "BOOT_READBACK_SOURCE")
    live.trusted_directory(live.REPO)
    need(git("remote", "get-url", "origin").strip() ==
         b"https://github.com/al-teamaot-com/jason.git", "SOURCE_ORIGIN")
    remote = git("ls-remote", "origin", "refs/heads/main").decode().split()
    need(len(remote) == 2 and remote[1] == "refs/heads/main", "PROTECTED_MAIN")
    require_sha(remote[0], "BOOT_READBACK_MAIN")
    git("merge-base", "--is-ancestor", installer, remote[0])
    git("merge-base", "--is-ancestor", reviewed, installer)
    git("merge-base", "--is-ancestor", rollback, reviewed)
    need(git("rev-parse", installer + "^{tree}") ==
         git("rev-parse", reviewed + "^{tree}"), "REVIEWED_TREE")
    require_ci_green(reviewed)
    for rel in FILES:
        need(live.trusted_bytes(BUNDLE / rel) == git("show", installer + ":" + rel),
             "BUNDLE_SOURCE_CHANGED")


def boot_evidence(runtime, old_id):
    """Require the actual current-boot remount completion, not merely an ID mismatch."""
    ids = live.run("/usr/bin/docker", "ps", "-a", "--no-trunc",
                   "--format", "{{.ID}}", timeout=20).stdout.decode().splitlines()
    need(old_id not in ids, "ORIGINAL_RUNTIME_STILL_PRESENT")
    raw = live.run("/usr/bin/journalctl", "-b", "-u", "jason-boot-recovery.service",
                   "--no-pager", "--output=json", "--grep=RUNTIME_CREDENTIAL_REMOUNT=PASS",
                   timeout=20).stdout
    created = datetime.fromisoformat(runtime["Created"].replace("Z", "+00:00"))
    matching = []
    for line in raw.splitlines():
        row = json.loads(line)
        if row.get("MESSAGE") == "RUNTIME_CREDENTIAL_REMOUNT=PASS" and row.get("_SYSTEMD_UNIT") == "jason-boot-recovery.service":
            observed = datetime.fromtimestamp(int(row["__REALTIME_TIMESTAMP"]) / 1_000_000, timezone.utc)
            if 0 <= (observed - created).total_seconds() <= 120:
                matching.append(observed)
    need(len(matching) == 1, "BOOT_REMOUNT_EVIDENCE_MISSING")


def live_plan(host, m):
    host._require_current_staged_scope()
    need(not any((dispatcher.AUTH / "requests").glob("*.json")), "PENDING_RELEASE_REQUEST")
    # Only the completed, already signed active release can be reconciled.
    jpath = host._journal_path(m)
    historical = live.exact_file(jpath, uid=0, mode=0o600, max_size=131072)
    j = json.loads(historical)
    need(j.get("outcome") == "production_components_verified"
         and live.APPROVAL.fullmatch(j.get("approval_id", "")), "UNRESOLVED_RELEASE")
    receipt = live.root_json(CONSUMED / (j["approval_id"] + ".json"))
    # Validate the historical signature at its original consumption time. It
    # is evidence only and is NEVER reused to authorize this maintenance.
    envelope = json.loads(live.exact_file(
        dispatcher.AUTH / "owner-approvals" / (m["release_id"] + ".json"),
        uid=pwd.getpwnam("al").pw_uid, mode=0o600, max_size=32768))
    signed = signing.verify_exact_owner_release(
        envelope["signed_owner_proof"],
        public_key=signing.read_pinned_root_owner_public_key(live.TRUST_KEY),
        expected_candidate_sha=m["candidate_sha"], expected_rollback_sha=m["rollback_sha"],
        expected_release_id=m["release_id"], expected_scope_sha256=m["scope_sha256"],
        expected_manifest_sha256=digest(m),
        expected_release_policy_sha256=m["release_policy_sha256"],
        at=datetime.fromisoformat(receipt["consumed_at"]))
    need(signed["approval_id"] == receipt["approval_id"] == j["approval_id"],
         "HISTORICAL_SIGNED_DECISION_MISMATCH")
    before = live.exact_file(readback.READBACK, uid=0, mode=0o644, max_size=65536)
    old = readback.read()
    need(json.loads(before) == old, "BEFORE_IMAGE_CHANGED")
    host_path = readback.HOST_CURRENT.resolve(strict=True)
    need(readback.HOST_CURRENT.is_symlink() and host_path.parent == Path("/opt/jason/releases"),
         "HOST_ANCHOR")
    policy = sha256(readback._root_read(readback.NORMAL_POLICY)).hexdigest()
    signing.require_normal_deployment_enabled(live.FREEZE.parent, policy)
    guard = host.guard
    control = live.root_json(guard.control_path)
    drift = live.root_json(guard.drift_path)
    breaker = control.get("circuit_breaker") or {}
    age = (datetime.now(timezone.utc) -
           datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))).total_seconds()
    need(breaker.get("state") == "open"
         and breaker.get("reason") == "continuous_production_drift_detected"
         and drift.get("status") == "pass" and drift.get("problems") == []
         and 0 <= age <= 180, "NATIVE_HEALTH_BOUNDARY")
    readback.verify_legacy_anchor(old, control["last_known_good"]["manifest"])
    actual = readback.inspect_components()
    items = {k: live.required_container(k) for k in readback.COMPONENTS}
    need(all(items[k]["Id"] == actual[k]["container_id"] for k in items),
         "LIVE_OBSERVATION_CHANGED")
    plan, new = make_plan(before, historical, actual,
                          {k: live.config_fingerprint(v) for k, v in items.items()},
                          host_revision=host_path.name, policy_sha256=policy,
                          manifest=m, consumed=receipt)
    boot_evidence(items[RUNTIME], plan["old_runtime"]["container_id"])
    return plan, new, before, historical


def maintenance_offer(plan, installer, reviewed, rollback, approved_scope):
    need(digest(plan) == approved_scope, "PREVIOUS_APPROVED_SCOPE_CHANGED")
    return {"schema_version": "1.0", "action": ACTION, "recovery_scope": plan,
            "recovery_scope_sha256": approved_scope, "installer_sha": installer,
            "candidate_sha": reviewed, "rollback_sha": rollback,
            "release_policy_sha256": plan["policy_sha256"],
            "release_id": "release-" + reviewed[:16]}


def signature_binding(offer):
    return {"expected_candidate_sha": offer["candidate_sha"],
            "expected_rollback_sha": offer["rollback_sha"],
            "expected_release_id": offer["release_id"],
            "expected_scope_sha256": digest(offer),
            "expected_manifest_sha256": digest(offer),
            "expected_release_policy_sha256": offer["release_policy_sha256"]}


def verify_decision(proof, offer, *, key, at, consumed):
    decision = signing.verify_exact_owner_release(
        proof, public_key=key, at=at, consumed_ids=consumed, **signature_binding(offer))
    need(decision["owner_oid"] == signing.OWNER_OID
         and decision["owner_principal"] == signing.OWNER_PRINCIPAL, "LICENSED_OWNER_REQUIRED")
    return decision


def publish_offer(offer):
    raw = canonical(offer)
    if os.path.lexists(OFFER):
        need(live.exact_file(OFFER, uid=0, mode=0o644) == raw, "OFFER_CHANGED")
        return
    fd = os.open(OFFER, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as out:
        os.fchmod(out.fileno(), 0o644)
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def read_offer():
    live.trusted_directory(BUNDLE)
    return json.loads(live.exact_file(OFFER, uid=0, mode=0o644))


def authorize_locally():
    # The already installed Owner verifier does the real Entra authentication.
    # No ChatGPT assertion, caller-supplied identity, or historical proof is accepted.
    need(os.geteuid() == pwd.getpwnam("al").pw_uid and sys.stdin.isatty()
         and sys.stderr.isatty(), "INTERACTIVE_OWNER_REQUIRED")
    from tools import scoped_backport_owner_local_approval as local
    local.installed()
    offer = read_offer()
    p = offer["recovery_scope"]
    need(offer == maintenance_offer(p, offer["installer_sha"], offer["candidate_sha"],
                                     offer["rollback_sha"], offer["recovery_scope_sha256"])
         and p["action"] == ACTION, "OFFER_SCOPE")
    with redirect_stdout(sys.stderr):
        print("EXACT_ACTION=" + ACTION)
        print("PREVIOUS_APPROVED_SCOPE_SHA256=" + offer["recovery_scope_sha256"])
        print("SIGNED_MAINTENANCE_SCOPE_SHA256=" + digest(offer))
        print("SOURCE_CANDIDATE=" + offer["candidate_sha"])
        oid = local.authenticated_owner()
        need(oid == signing.OWNER_OID, "LICENSED_OWNER_REQUIRED")
        need(input("Type " + CONFIRM + " to authenticate this exact recovery: ").strip()
             == CONFIRM, "OWNER_DECISION_NOT_CONFIRMED")
    key = signing.read_service_owner_signing_key(SIGNER)
    at = datetime.now(timezone.utc)
    proof = signing.issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex, release_id=offer["release_id"],
        candidate_sha=offer["candidate_sha"], rollback_sha=offer["rollback_sha"],
        scope_sha256=digest(offer), manifest_sha256=digest(offer),
        release_policy_sha256=offer["release_policy_sha256"],
        verified_tenant_id=signing.TID, verified_owner_oid=oid,
        verified_principal=signing.OWNER_PRINCIPAL, verified_organization_id="aot",
        confirmed_decision="approve", at=at, private_key=key)
    verify_decision(proof, offer, key=signing.read_pinned_root_owner_public_key(live.TRUST_KEY),
                    at=at, consumed=frozenset())
    print(json.dumps(proof, sort_keys=True))


def apply_exact(host, m, offer, plan, new, before, historical, proof):
    """Under the existing shared native lock, consume once, publish and verify."""
    host._locked()
    host._require_current_staged_scope()
    need(read_offer() == offer and offer["recovery_scope"] == plan
         and offer["recovery_scope_sha256"] == digest(plan)
         and plan["approved_record_sha256"] == sha256(before).hexdigest()
         and plan["transaction_sha256"] == sha256(historical).hexdigest()
         and plan["proposed_readback_canonical_sha256"] == readback.digest(new),
         "ROOT_OFFER_MISMATCH")
    decision = verify_decision(proof, offer,
        key=signing.read_pinned_root_owner_public_key(live.TRUST_KEY),
        at=datetime.now(timezone.utc), consumed=host.consumed_approvals())
    approval_id = decision["approval_id"]
    scope_hash = digest(offer)
    live.root_directory(LEDGER)
    intent = LEDGER / (scope_hash + ".intent.json")
    result = LEDGER / (scope_hash + ".result.json")
    need(not os.path.lexists(intent) and not os.path.lexists(result), "SCOPE_ALREADY_ATTEMPTED")
    peers = host.snapshot_protected()
    after = canonical(new)
    live.atomic_root_json(intent, {"scope": offer, "scope_sha256": scope_hash,
        "approval_id": approval_id, "signed_owner_proof": proof,
        "before": base64.b64encode(before).decode(),
        "after": base64.b64encode(after).decode(), "historical_transaction_sha256":
        sha256(historical).hexdigest()})
    live.atomic_root_json(CONSUMED / (approval_id + ".json"), {
        "schema_version": "2.0", "approval_id": approval_id, "release_id": offer["release_id"],
        "action": ACTION, "scope_sha256": scope_hash, "consumed_at": live.utcnow(), "one_use": True})
    try:
        atomic_exact_root_file(readback.READBACK, before, after, 0o644)
        need(readback.verify_live() == new, "NATIVE_READBACK_FAILED")
        need(live.exact_file(host._journal_path(m), uid=0, mode=0o600) == historical,
             "ORIGINAL_TRANSACTION_CHANGED")
        host.verify_protected_unchanged(peers)
        historical_record = json.loads(historical)
        fingerprints = {k: live.config_fingerprint(live.required_container(k))
                        for k in readback.COMPONENTS}
        need(fingerprints == historical_record.get("candidate_configs",
                                                   historical_record["original_configs"]),
             "POSTFLIGHT_CONFIGURATION_CHANGED")
        need(sha256(readback._root_read(readback.NORMAL_POLICY)).hexdigest() == plan["policy_sha256"],
             "POLICY_CHANGED")
    except Exception:
        restore_attempted_root_files([(readback.READBACK, before, after, 0o644)])
        live.atomic_root_json(result, {"scope_sha256": scope_hash,
            "status": "boot_readback_rollback_verified", "breaker_transition_performed": False})
        raise
    live.atomic_root_json(result, {"scope_sha256": scope_hash, "approval_id": approval_id,
        "status": "boot_runtime_identity_reconciled_verified",
        "recovery_scope_sha256": offer["recovery_scope_sha256"],
        "breaker_transition_performed": False, "application_changes": False})
    return {"status": "boot_runtime_identity_reconciled_verified",
            "scope_sha256": scope_hash, "native_breaker_revalidation_required": True}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    group = cli.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--authorize", action="store_true")
    group.add_argument("--apply", action="store_true")
    cli.add_argument("--installer-sha")
    cli.add_argument("--reviewed-sha")
    cli.add_argument("--rollback-sha")
    cli.add_argument("--approved-scope")
    args = cli.parse_args()
    if args.authorize:
        need(not any((args.installer_sha, args.reviewed_sha, args.rollback_sha, args.approved_scope)),
             "AUTHORIZATION_CALLER_SCOPE_FORBIDDEN")
        authorize_locally()
        return
    need(os.geteuid() == 0, "ROOT_NATIVE_REQUIRED")
    require_hash(args.approved_scope, "BOOT_READBACK_PREVIOUS_SCOPE")
    verify_source(args.installer_sha, args.reviewed_sha, args.rollback_sha)
    host, m, _ = dispatcher.load_installed()
    with host.release_lock(m):
        plan, new, before, historical = live_plan(host, m)
        offer = maintenance_offer(plan, args.installer_sha, args.reviewed_sha,
                                  args.rollback_sha, args.approved_scope)
        if args.prepare:
            publish_offer(offer)
            print(json.dumps({"offer": offer, "scope_sha256": digest(offer),
                              "production_mutation_performed": False}, sort_keys=True))
            return
        raw = sys.stdin.buffer.read(32769)
        need(0 < len(raw) <= 32768, "SIGNED_PROOF_REQUIRED")
        print(json.dumps(apply_exact(host, m, offer, plan, new, before,
                                    historical, json.loads(raw)), sort_keys=True))


if __name__ == "__main__":
    main()

