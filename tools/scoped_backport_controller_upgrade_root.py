"""Root entry for exact coordinated-controller maintenance.

Run from a sealed, root-owned source bundle after protected-main review.
Apply requires an independently issued signed decision for this maintenance
scope. The entry point does not issue approvals or promote a release.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

# Isolated interpreter; trust neither the caller's PYTHONPATH nor their cwd.
NATIVE = Path("/usr/local/lib/jason/scoped-backport")
if __name__ == "__main__":
    bundle = Path(__file__).absolute().parents[1]
    for path in (Path(__file__), bundle / "tools", bundle, *bundle.parents):
        info = path.lstat()
        if path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise SystemExit("CONTROLLER_UPGRADE_UNTRUSTED_SOURCE_BUNDLE")
    if os.geteuid() != 0 or not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit("CONTROLLER_UPGRADE_REQUIRES_ISOLATED_ROOT")
    sys.path[:0] = [str(NATIVE), str(bundle)]

from implementation.kernel.signed_owner_release import read_pinned_root_owner_public_key
from implementation.kernel.signed_owner_release_v2 import (
    read_retired_release_policy,
    require_normal_deployment_enabled,
    verify_exact_owner_release,
)
from tools import scoped_backport_coordinated_host as live
from tools import scoped_backport_coordinated_root as dispatcher
from tools import scoped_backport_controller_upgrade as upgrade
from tools.scoped_backport_four_unit_drift_reconcile import (
    atomic_exact_root_file,
    require_ci_green, restore_attempted_root_files,
)
from tools.scoped_backport_release import deny, digest, require_hash, require_sha

LEDGER = live.PRIVATE / "controller-maintenance"
REQUEST = "jason-scoped-backport-requests.service"
RECOVERY = "jason-scoped-backport-recovery.service"
TRIGGERS = ("jason-scoped-backport-requests.path", "jason-scoped-backport-recovery.timer")
SOURCE = "tools/scoped_backport_coordinated_host.py"
BUNDLE_FILES = (
    "tools/scoped_backport_controller_upgrade_root.py",
    "tools/scoped_backport_controller_upgrade.py",
    "tools/scoped_backport_four_unit_drift_reconcile.py",
)


def git(*args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(live.REPO), "-c", "core.hooksPath=/dev/null", *args],
        env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"},
        check=True, capture_output=True, timeout=30,
    ).stdout


def verified_source(installer: str, reviewed: str, candidate: str, rollback: str) -> None:
    for revision in (installer, reviewed, candidate, rollback):
        require_sha(revision, "CONTROLLER_UPGRADE_SOURCE")
    live.trusted_directory(live.REPO)
    if git("remote", "get-url", "origin").strip() != b"https://github.com/al-teamaot-com/jason.git":
        deny("CONTROLLER_UPGRADE_ORIGIN")
    remote = git("ls-remote", "origin", "refs/heads/main").decode().split()
    if len(remote) != 2 or remote[1] != "refs/heads/main":
        deny("CONTROLLER_UPGRADE_PROTECTED_MAIN")
    require_sha(remote[0], "CONTROLLER_UPGRADE_PROTECTED_MAIN")
    git("merge-base", "--is-ancestor", installer, remote[0])
    git("merge-base", "--is-ancestor", candidate, installer)
    git("merge-base", "--is-ancestor", rollback, candidate)
    if git("rev-parse", installer + "^{tree}") != git("rev-parse", reviewed + "^{tree}"):
        deny("CONTROLLER_UPGRADE_REVIEWED_TREE_MISMATCH")
    require_ci_green(reviewed)
    source = Path(__file__).absolute().parents[1]
    for name in BUNDLE_FILES:
        if live.trusted_bytes(source / name) != git("show", installer + ":" + name):
            deny("CONTROLLER_UPGRADE_INSTALLER_BYTES_CHANGED")


def verify_successful_predecessor(manifest, journal):
    # The native readback includes authenticated post-boot identity repairs.
    # It independently checks current container IDs, health, host and policy.
    current = live.readback.verify_live()
    original = live.readback.validate(journal["proposed_readback"])
    if (not current or journal.get("mutation_attempted") is not True
            or current["release_id"] != manifest["release_id"]
            or current["manifest_sha256"] != digest(manifest)
            or current["scope_sha256"] != manifest["scope_sha256"]
            or current["release_policy_sha256"] != manifest["release_policy_sha256"]
            or {k:v for k,v in current.items() if k != "components"} !=
               {k:v for k,v in original.items() if k != "components"}):
        deny("CONTROLLER_UPGRADE_VERIFIED_RELEASE_MISMATCH")
    expected = journal.get("candidate_configs", journal["original_configs"])
    targets = {target["name"] for target in manifest["targets"]}
    protected = journal["protected_before"]
    protected_names = set(manifest["protected_services"])
    components = set(current["components"])
    if (set(expected) != targets or set(journal["original_configs"]) != targets
            or set(protected) != protected_names or targets & protected_names
            or not targets <= components or not components <= targets | protected_names):
        deny("CONTROLLER_UPGRADE_COMPONENT_SET")
    for name, row in current["components"].items():
        prior = original["components"][name]
        item = live.required_container(name)
        if name in targets:
            configuration = expected[name]
        else:
            # Unchanged coordinated peers have their own protected snapshot,
            # not a target candidate fingerprint. Retain exact original image
            # and ID evidence; a current ID may only come from verified root
            # readback (including an authenticated post-boot reconciliation).
            peer = protected[name]
            if (peer["id"] != prior["container_id"] or peer["image"] != prior["image_id"]
                    or peer["running"] is not True or peer["status"] != "running"
                    or peer["oom"] is True):
                deny("CONTROLLER_UPGRADE_PROTECTED_PEER_EVIDENCE")
            configuration = peer["configuration_sha256"]
        if (row["revision"] != prior["revision"] or row["image_id"] != prior["image_id"]
                or item["Id"] != row["container_id"]
                or live.config_fingerprint(item) != configuration):
            deny("CONTROLLER_UPGRADE_COMPONENT_DRIFT")


def terminal_offer():
    host, manifest, _ = dispatcher.load_installed()
    # A maintenance preflight can inspect the prior transaction, never run it.
    path = host._journal_path(manifest)
    if manifest["schema_version"] != "3.0" or not os.path.lexists(path):
        deny("CONTROLLER_UPGRADE_ACTIVE_RELEASE")
    require_normal_deployment_enabled(live.FREEZE.parent, manifest["release_policy_sha256"])
    journal = live.root_json(path)
    if (journal.get("release_id") != manifest["release_id"]
            or journal.get("manifest_sha256") != digest(manifest)
            or journal.get("scope_sha256") != manifest["scope_sha256"]):
        deny("CONTROLLER_UPGRADE_PRIOR_SCOPE_MISMATCH")
    if journal.get("outcome") == "production_components_verified":
        verify_successful_predecessor(manifest, journal)
    elif journal.get("outcome") != "rollback_verified":
        deny("CONTROLLER_UPGRADE_UNRESOLVED_PREDECESSOR")
    if any((dispatcher.AUTH / "requests").glob("*.json")):
        deny("CONTROLLER_UPGRADE_PENDING_REQUESTS")
    return host, manifest


def maintenance_scope(plan, installer, reviewed, manifest):
    mode = read_retired_release_policy()
    if mode is None:
        deny("CONTROLLER_UPGRADE_NORMAL_POLICY_REQUIRED")
    require_normal_deployment_enabled(live.FREEZE.parent, mode)
    return dict(plan.scope(), installer_sha=installer, reviewed_sha=reviewed,
                prior_release_id=manifest["release_id"], release_policy_sha256=mode)


def state(unit: str) -> str:
    return live.run("systemctl", "show", unit, "-p", "ActiveState",
                    "--value", timeout=12).stdout.decode().strip()


def set_triggers(command: str) -> None:
    live.run("systemctl", command, *TRIGGERS, timeout=45)
    expected = "active" if command == "start" else "inactive"
    if any(state(unit) != expected for unit in TRIGGERS):
        deny("CONTROLLER_UPGRADE_TRIGGER_STATE")


def check_workers() -> None:
    if state(REQUEST) not in ("failed", "inactive") or state(RECOVERY) != "inactive":
        deny("CONTROLLER_UPGRADE_WORKER_NOT_QUIESCENT")


def verify_files(plan: upgrade.Upgrade, rolled_back: bool) -> None:
    policy = live.verify_installed_policy()
    for item in plan.files:
        expected = item.before if rolled_back else item.after
        if live.exact_file(item.path, uid=0, mode=item.mode) != expected:
            deny("CONTROLLER_UPGRADE_FILE_READBACK")
    if policy["per_release_review_required"] is not True:
        deny("CONTROLLER_UPGRADE_POLICY_READBACK")


def make_plan(candidate: str, rollback: str) -> upgrade.Upgrade:
    live.verify_installed_policy()
    return upgrade.plan_upgrade(
        candidate, rollback, live.exact_file(live.INSTALLED, uid=0, mode=0o444),
        git("show", rollback + ":" + SOURCE), git("show", candidate + ":" + SOURCE),
        live.exact_file(live.POLICY, uid=0, mode=0o600),
    )


def verify_decision(plan, scope, proof, host):
    scope_hash = digest(scope)
    decision = verify_exact_owner_release(
        proof, public_key=read_pinned_root_owner_public_key(live.TRUST_KEY),
        expected_candidate_sha=plan.candidate_sha,
        expected_rollback_sha=plan.rollback_sha,
        expected_release_id="release-" + plan.candidate_sha[:16],
        expected_scope_sha256=scope_hash, expected_manifest_sha256=scope_hash,
        expected_release_policy_sha256=scope["release_policy_sha256"],
        at=datetime.now(timezone.utc), consumed_ids=host.consumed_approvals(),
    )
    if not live.APPROVAL.fullmatch(decision["approval_id"]):
        deny("CONTROLLER_UPGRADE_APPROVAL_ID")
    return decision["approval_id"]


def attempt_paths(scope_hash):
    require_hash(scope_hash, "CONTROLLER_UPGRADE_SCOPE")
    return (LEDGER / (scope_hash + ".intent.json"), LEDGER / (scope_hash + ".result.json"))


def consumption_path(approval_id):
    if not live.APPROVAL.fullmatch(approval_id):
        deny("CONTROLLER_UPGRADE_APPROVAL_ID")
    return live.ROOT_STATE / "consumed-owner-approvals" / (approval_id + ".json")


def apply(plan, scope, proof, host, manifest):
    scope_hash = digest(scope)
    with host.release_lock(manifest):
        protected = host.snapshot_protected()
        live.readback.verify_live()
        if any(state(unit) != "active" for unit in TRIGGERS):
            deny("CONTROLLER_UPGRADE_UNEXPECTED_TRIGGER_BASELINE")

        def revalidate():
            _, current = terminal_offer()
            current_plan = make_plan(plan.candidate_sha, plan.rollback_sha)
            if maintenance_scope(current_plan, scope["installer_sha"], scope["reviewed_sha"], current) != scope:
                deny("CONTROLLER_UPGRADE_LIVE_SCOPE_CHANGED")
            return current_plan

        intent, result = attempt_paths(scope_hash)
        triggers_touched = False

        def claim(current):
            nonlocal triggers_touched
            approval_id = verify_decision(current, scope, proof, host)
            if not os.path.lexists(LEDGER):
                LEDGER.mkdir(mode=0o700)
            live.root_directory(LEDGER)
            if os.path.lexists(intent) or os.path.lexists(result):
                deny("CONTROLLER_UPGRADE_SCOPE_ALREADY_ATTEMPTED")
            live.atomic_root_json(intent, {
                "scope": scope, "scope_sha256": scope_hash, "approval_id": approval_id,
                "before_images": [base64.b64encode(file.before).decode() for file in current.files],
            })
            live.atomic_root_json(consumption_path(approval_id), {
                "schema_version": "2.0", "approval_id": approval_id,
                "release_id": "release-" + plan.candidate_sha[:16],
                "action": upgrade.ACTION, "scope_sha256": scope_hash,
                "consumed_at": live.utcnow(), "one_use": True,
            })
            triggers_touched = True
            set_triggers("stop")
            check_workers()

        def restore(changes):
            set_triggers("stop")
            check_workers()
            restore_attempted_root_files(changes)

        def verify(current, rolled_back):
            set_triggers("start")
            verify_files(current, rolled_back)
            host.verify_protected_unchanged(protected)
            live.readback.verify_live()
            if maintenance_scope(current, scope["installer_sha"], scope["reviewed_sha"], manifest) != scope:
                deny("CONTROLLER_UPGRADE_POLICY_CHANGED")
            live.atomic_root_json(result, {
                "status": "controller_rollback_verified" if rolled_back else "controller_installed_verified",
                "scope_sha256": scope_hash,
            })

        try:
            upgrade.apply_under_held_transaction(
                plan, revalidate=revalidate, consume_and_record_rollback=claim,
                replace=atomic_exact_root_file, restore=restore, verify=verify,
            )
        finally:
            if triggers_touched and any(state(unit) != "active" for unit in TRIGGERS):
                # An unresolved intent remains recoverable under the existing
                # shared locks even after the process dies between the writes.
                set_triggers("start")


def recover(installer, reviewed, candidate, rollback, scope_hash):
    """Restore before-images from an authenticated interrupted transaction."""
    with live.IndependentHostGuard().host_release_transaction():
        live.root_directory(LEDGER)
        intent, result = attempt_paths(scope_hash)
        if os.path.lexists(result):
            deny("CONTROLLER_UPGRADE_ALREADY_RESOLVED")
        row = live.root_json(intent, max_size=2_000_000)
        scope = row["scope"]
        if row["scope_sha256"] != scope_hash or digest(scope) != scope_hash:
            deny("CONTROLLER_UPGRADE_RECOVERY_SCOPE")
        consumption = live.root_json(consumption_path(row["approval_id"]))
        if (consumption.get("action") != upgrade.ACTION
                or consumption.get("scope_sha256") != scope_hash
                or consumption.get("approval_id") != row["approval_id"]):
            deny("CONTROLLER_UPGRADE_RECOVERY_AUTHORITY")
        old_controller, old_policy = [base64.b64decode(raw, validate=True)
                                      for raw in row["before_images"]]
        plan = upgrade.plan_upgrade(
            candidate, rollback, old_controller, git("show", rollback + ":" + SOURCE),
            git("show", candidate + ":" + SOURCE), old_policy,
        )
        offer = live.active_staged_offer()
        if offer is None or maintenance_scope(plan, installer, reviewed, offer["manifest"]) != scope:
            deny("CONTROLLER_UPGRADE_RECOVERY_SCOPE_CHANGED")
        # Validate every before/after identity before touching either file.
        for item in plan.files:
            if live.exact_file(item.path, uid=0, mode=item.mode) not in (item.before, item.after):
                deny("CONTROLLER_UPGRADE_RECOVERY_FOREIGN_FILE")
        try:
            set_triggers("stop")
            check_workers()
            restore_attempted_root_files([(f.path, f.before, f.after, f.mode) for f in plan.files])
        finally:
            set_triggers("start")
        verify_files(plan, True)
        live.readback.verify_live()
        live.atomic_root_json(result, {"status": "controller_interrupted_rollback_verified",
                                      "scope_sha256": scope_hash})


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--installer-sha", required=True)
    cli.add_argument("--reviewed-sha", required=True)
    cli.add_argument("--candidate-sha", required=True)
    cli.add_argument("--rollback-sha", required=True)
    action = cli.add_mutually_exclusive_group()
    action.add_argument("--apply-scope")
    action.add_argument("--recover-scope")
    args = cli.parse_args()
    verified_source(args.installer_sha, args.reviewed_sha, args.candidate_sha, args.rollback_sha)
    if args.recover_scope is not None:
        recover(args.installer_sha, args.reviewed_sha, args.candidate_sha, args.rollback_sha, args.recover_scope)
        return
    host, manifest = terminal_offer()
    plan = make_plan(args.candidate_sha, args.rollback_sha)
    scope = maintenance_scope(plan, args.installer_sha, args.reviewed_sha, manifest)
    if args.apply_scope is None:
        print(json.dumps({"scope": scope, "scope_sha256": digest(scope)}, sort_keys=True))
        return
    if args.apply_scope != digest(scope):
        deny("CONTROLLER_UPGRADE_OPERATOR_SCOPE_MISMATCH")
    apply(plan, scope, json.loads(sys.stdin.buffer.read(32769)), host, manifest)


if __name__ == "__main__":
    main()
