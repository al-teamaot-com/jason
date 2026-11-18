#!/usr/bin/env python3
"""Stage C existing-canonical state handoff: no database move, one signed Owner."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys
import time

# The release launcher stages this source and dependencies root-owned, mode 0400.
# An al-owned source worktree is never a root code or approval source.
HERE = Path(__file__).resolve()
if HERE.parent.name == "tools":
    sys.path.insert(0, str(HERE.parents[1]))
else:
    sys.path.insert(0, str(HERE.parent / "src"))

from tools import pmv4_c_atomic_root as c
from tools import pmv4_c_service_manifest as service
from tools import pmv4_host_release_guard as guard
from tools import pmv4_shadow_ci as protected_ci

ACTION = "pmv4-c-one-owner-existing-canonical-worker-handoff-v1"
PREVIOUS = "13917410bb0ea1d5d37a314b3a3f131d416bf154"
PRIOR = Path("/srv/jason/archive/engineering-artifacts") / ("pmv4-c-" + PREVIOUS)
ARTIFACTS = Path("/srv/jason/archive/engineering-artifacts")
CATALOG_SOURCE = "769d8cad698d092779def1dcfb8ba5e1fc896a9d"
CATALOG_PACKET = ARTIFACTS / ("pmv4-catalog-drift-" + CATALOG_SOURCE)
CATALOG_AUDIT = Path("/etc/jason-owner-release/pmv4-catalog-unit-drift-reconciliation")
CATALOG_UNITS = (
    "jason-catalog-root-bootstrap-recovery.service",
    "jason-catalog-root-bootstrap-recovery.timer",
    "jason-catalog-scoped-recovery.service",
    "jason-catalog-scoped-recovery.timer",
)
SOURCE_FILES = (
    "tools/pmv4_c_atomic_root.py",
    "tools/pmv4_c_sqlite_family_handoff.py",
    "tools/pmv4_c_service_manifest.py",
    "tools/pmv4_ticket_core_exact_projection.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_ci.py",
    "tools/deploy_live_container.py",
    "tools/pmv4_mcp_projection.py",
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise c.StageCRootDenied("C_RESUME_" + why)


def original() -> dict:
    old = c.read_json(PRIOR / "root-release-plan.json")
    need(old.get("candidate_sha") == PREVIOUS, "PREVIOUS_PLAN_MISMATCH")
    need((PRIOR / "root-oneowner-proof.json").is_file(), "PREVIOUS_OWNER_PROOF_MISSING")
    return old


def accepted_catalog_policy() -> tuple[bytes, bytes]:
    """Exact prior Owner-signed four-unit policy, not a new policy guess."""
    prior = original()
    base = (PRIOR / "production-desired-state.base.json").read_bytes()
    need(c.sha(base) == prior["watchdog_base_sha256"], "ORIGINAL_POLICY_CHANGED")
    catalog_baseline = (CATALOG_PACKET / "baseline.json").read_bytes()
    need(catalog_baseline == base, "CATALOG_BASELINE_NOT_ORIGINAL")
    source = c.read_json(CATALOG_PACKET / "root-release-plan.json")
    unsigned = dict(source)
    scope = unsigned.pop("scope_sha256", None)
    need(source.get("action") ==
         "pmv4-catalog-four-unit-drift-policy-reconcile-v1" and
         source.get("source_sha") == CATALOG_SOURCE and
         source.get("candidate_sha") == CATALOG_SOURCE and
         source.get("rollback_sha") == prior["production_lkg_sha"] and
         source.get("catalog_unit_names") == list(CATALOG_UNITS) and
         source.get("baseline_policy_sha256") == c.sha(base) and
         source.get("owner_consents") == 1 and
         source.get("restart_containers") == [] and
         isinstance(scope, str) and c.sha(c.canon(unsigned)) == scope,
         "CATALOG_SIGNED_POLICY_SCOPE_UNTRUSTED")
    proof_bytes = (CATALOG_PACKET / "root-oneowner-proof.json").read_bytes()
    proof = c.read_json(CATALOG_PACKET / "root-oneowner-proof.json")
    need(proof.get("action") == source["action"] and
         proof.get("source_sha") == CATALOG_SOURCE and
         proof.get("scope_sha256") == scope and
         proof.get("plan_sha256") == c.sha(c.canon(source)) and
         isinstance(proof.get("approval_id"), str) and
         isinstance(proof.get("signed_release"), dict),
         "CATALOG_PRIOR_OWNER_PROOF_INVALID")
    new = (CATALOG_PACKET / "candidate.json").read_bytes()
    baseline = json.loads(base)
    expect = dict(baseline)
    allowed = baseline.get("allowed_system_units")
    need(isinstance(allowed, list) and
         not any(unit in allowed for unit in CATALOG_UNITS),
         "CATALOG_BASELINE_UNEXPECTED")
    expect["allowed_system_units"] = sorted(allowed + list(CATALOG_UNITS))
    need(new == (json.dumps(expect, indent=2, sort_keys=True) + "\n").encode() and
         c.sha(new) == source["candidate_policy_sha256"],
         "CATALOG_POLICY_NOT_EXACT_FOUR_UNITS")
    return new, proof_bytes


def reviewed_candidate_policy(approved: bytes) -> bytes:
    """Add original Ticket Core worker + one rollback slot; preserve catalog units."""
    prior = original()
    original_base = json.loads((PRIOR / "production-desired-state.base.json").read_bytes())
    original_worker = json.loads(
        (PRIOR / "production-desired-state.stage-c.json").read_bytes())
    before = original_base.get("allowed_running_containers")
    after = original_worker.get("allowed_running_containers")
    need(isinstance(before, list) and isinstance(after, list) and
         after == before + [c.WORKER] and
         {k: v for k, v in original_base.items() if k != "allowed_running_containers"} ==
         {k: v for k, v in original_worker.items() if k != "allowed_running_containers"} and
         c.sha((PRIOR / "production-desired-state.stage-c.json").read_bytes()) ==
         prior["watchdog_candidate_sha256"], "ORIGINAL_WORKER_SCOPE_CHANGED")
    policy = json.loads(approved)
    need(policy.get("max_stopped_rollback_containers") == 20 and
         policy.get("allowed_running_containers") == before and
         set(CATALOG_UNITS).issubset(set(policy.get("allowed_system_units", []))),
         "CATALOG_STAGE_C_BASELINE_UNEXPECTED")
    policy["allowed_running_containers"] = after
    policy["max_stopped_rollback_containers"] = 21
    return (json.dumps(policy, indent=2, sort_keys=True) + "\n").encode()


def packet(plan_path: Path) -> tuple[dict, dict]:
    need(os.geteuid() == 0, "ROOT_REQUIRED")
    plan = c.read_json(plan_path)
    need(plan_path.parent == ARTIFACTS / ("pmv4-c-resume-" + str(plan.get("candidate_sha"))) and
         plan_path.name == "root-release-plan.json", "ARTIFACT_PATH_NOT_PINNED")
    need(plan.get("schema_version") == "1.0" and plan.get("action") == ACTION and
         plan.get("owner_consents") == 1 and
         plan.get("standing_authority") is False and
         plan.get("later_stages_authorized") is False and
         plan.get("no_database_relocation") is True and
         plan.get("service_restarts") == ["jason-runtime"] and
         plan.get("two_scan_acceptance") is True, "SCOPE_INVALID")
    unsigned = dict(plan)
    scope = unsigned.pop("scope_sha256", None)
    need(isinstance(scope, str) and c.sha(c.canon(unsigned)) == scope, "SCOPE_HASH_INVALID")
    prior = original()
    approved_policy, approved_proof = accepted_catalog_policy()
    need(plan.get("catalog_policy_source_sha") == CATALOG_SOURCE and
         plan.get("catalog_policy_proof_sha256") == c.sha(approved_proof) and
         plan.get("catalog_policy_sha256") == c.sha(approved_policy),
         "APPROVED_CATALOG_POLICY_BINDING_INVALID")
    # The installed root-owned receipt proves this prior Owner-signed action
    # was actually accepted, not merely approved in a developer packet.
    receipt = c.read_json(CATALOG_AUDIT / (CATALOG_SOURCE + "-accepted.json"))
    source_proof = c.read_json(CATALOG_PACKET / "root-oneowner-proof.json")
    need(receipt.get("status") == "four_unit_catalog_policy_reconciled" and
         receipt.get("action") ==
           "pmv4-catalog-four-unit-drift-policy-reconcile-v1" and
         receipt.get("source_sha") == CATALOG_SOURCE and
         receipt.get("owner_approval_id") == source_proof["approval_id"] and
         receipt.get("candidate_policy_sha256") == c.sha(approved_policy) and
         receipt.get("breaker_override") is False and
         receipt.get("ticket_core_restarts") == 0 and
         receipt.get("mcp_restarts") == 0,
         "CATALOG_PRIOR_ROOT_ACCEPTANCE_NOT_PROVEN")
    need(plan["previous_plan_sha256"] == c.sha((PRIOR / "root-release-plan.json").read_bytes()) and
         plan["previous_proof_sha256"] == c.sha((PRIOR / "root-oneowner-proof.json").read_bytes()),
         "PREVIOUS_PLAN_OR_APPROVAL_CHANGED")
    need(plan["rollback_sha"] == plan["production_lkg_sha"] ==
         prior["production_lkg_sha"] and
         plan["runtime_image_digest"] == prior["runtime_image_digest"] and
         plan["mcp_image_digest"] == prior["mcp_image_digest"] and
         plan["worker_image_digest"] == prior["worker_image_digest"] and
         plan["watchdog_base_sha256"] == c.sha(approved_policy) and
         plan["watchdog_candidate_sha256"] ==
             c.sha(reviewed_candidate_policy(approved_policy)) and
         plan["service_manifest_sha256"] == prior["service_manifest_sha256"],
         "UNREVIEWED_PREVIOUS_RESOURCE_SCOPE")
    # The old approved data identity is the only state source. No copy/rename.
    for original_name, old_meta in prior["db_identities"].items():
        source = Path(original_name)
        target = (c.TICKET_TARGET if source.name in
                  c.sqlite_handoff.ALLOWED_TICKET else c.SHARED_TARGET) / source.name
        meta = target.lstat()
        need(not source.exists() and not source.is_symlink() and
             not target.is_symlink() and stat.S_ISREG(meta.st_mode) and
             meta.st_uid == meta.st_gid == 1000 and
             meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == 0o600 and
             meta.st_dev == old_meta["device"] and meta.st_ino == old_meta["inode"],
             "CANONICAL_INODE_CHANGED:" + source.name)
    return plan, prior


def release_sources(plan: dict) -> None:
    stage = HERE.parent / "src"
    for rel in SOURCE_FILES:
        item = stage / rel
        meta = item.lstat()
        need(not item.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_uid == meta.st_gid == 0 and stat.S_IMODE(meta.st_mode) == 0o400
             and c.sha(item.read_bytes()) == plan["source_hashes"][rel],
             "ROOT_SOURCE_CHANGED:" + rel)
    self_meta = HERE.lstat()
    need(self_meta.st_uid == self_meta.st_gid == 0 and stat.S_IMODE(self_meta.st_mode) == 0o400 and
         c.sha(HERE.read_bytes()) == plan["root_sha256"], "ROOT_EXECUTOR_CHANGED")


def verify_owner(plan: dict, path: Path, *, recovery: bool = False) -> str:
    proof = c.read_json(path.parent / "root-oneowner-proof.json")
    need(proof.get("action") == ACTION and
         proof.get("source_sha") == plan["candidate_sha"] and
         proof.get("scope_sha256") == plan["scope_sha256"] and
         proof.get("plan_sha256") == c.sha(c.canon(plan)), "OWNER_PROOF_INVALID")
    signer = c._trusted_module(c.OWNER_SIGNER, c.OWNER_SIGNER_SHA, "c_resume_owner_signer")
    public = signer.read_pinned_root_owner_public_key(c.OWNER_PUBLIC_KEY)
    at = datetime.now(timezone.utc)
    if recovery:
        rows = c._audit_rows(plan)
        need(bool(rows), "PRIOR_AUDIT_MISSING")
        at = datetime.fromisoformat(rows[0]["occurred_at"])
    verified = signer.verify_exact_owner_release(
        proof["signed_release"], public_key=public, at=at,
        expected_candidate_sha=plan["candidate_sha"],
        expected_rollback_sha=plan["rollback_sha"],
        expected_release_id="release-" + plan["candidate_sha"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=c.sha(c.canon(plan)),
        expected_freeze_sha256=plan["freeze_sha256"],
    )
    need(verified["approval_id"] == proof["approval_id"], "OWNER_SIGNATURE_INVALID")
    return verified["approval_id"]


def preflight(path: Path) -> tuple[dict, guard.IndependentHostGuard]:
    plan, prior = packet(path)
    release_sources(plan)
    need(c.sha(c.FREEZE.read_bytes()) == plan["freeze_sha256"] and
         c.sha(c.HOLD.read_bytes()) == plan["hold_sha256"] and
         c.sha(c.WATCHDOG.read_bytes()) == plan["watchdog_base_sha256"], "PROTECTED_CONTROLS_CHANGED")
    need(Path("/opt/jason/current").resolve(strict=True).name ==
         plan["production_lkg_sha"], "PRODUCTION_ROOT_CHANGED")
    need(c.sha((path.parent / "service-manifest.json").read_bytes()) ==
         plan["service_manifest_sha256"], "SERVICE_MANIFEST_CHANGED")
    accepted_policy, _ = accepted_catalog_policy()
    need((path.parent / "watchdog-base.json").read_bytes() == accepted_policy and
         (path.parent / "watchdog-candidate.json").read_bytes() ==
           reviewed_candidate_policy(accepted_policy),
         "UNREVIEWED_WATCHDOG_CHANGE")
    need(c.sha((path.parent / "watchdog-base.json").read_bytes()) ==
         plan["watchdog_base_sha256"] and
         c.sha((path.parent / "watchdog-candidate.json").read_bytes()) ==
         plan["watchdog_candidate_sha256"], "WATCHDOG_PLAN_CHANGED")
    current = c._docker_json("jason-runtime")
    mcp = c._docker_json("jason-mcp-pilot")
    env = c._container_env(current)
    need(current["Id"] == plan["runtime_container_id"] and
         current["Image"] == plan["runtime_image_digest"] and
         current["State"]["Running"] is True and
         current["State"]["Health"]["Status"] == "healthy" and
         env.get("JASON_TICKET_WORKER_HOSTING") == "embedded" and
         env.get("JASON_AUTONOMY_WORKER_DB") ==
         str(c.TICKET_TARGET / "autonomy-operational-work.sqlite3") and
         mcp["Id"] == plan["mcp_container_id"] and
         mcp["Image"] == plan["mcp_image_digest"] and
         mcp["State"]["Running"] is True, "CONTAINER_BASELINE_CHANGED")
    mounts = {item["Destination"]: item["Source"]
              for item in current.get("Mounts", []) if item.get("Type") == "bind"}
    need(mounts.get(str(c.TICKET_TARGET)) == str(c.TICKET_TARGET) and
         mounts.get(str(c.SHARED_TARGET)) == str(c.SHARED_TARGET),
         "RUNTIME_CANONICAL_MOUNTS_UNVERIFIED")
    need(not c._docker_exists(c.WORKER), "EXTERNAL_WORKER_ALREADY_EXISTS")
    need(not c._docker_exists("jason-runtime-rollback-pmv4cresume-" +
                             plan["candidate_sha"][:12]), "ROLLBACK_CONTAINER_COLLISION")
    worker = c._run(["/usr/bin/docker", "image", "inspect", plan["worker_image_digest"]],
                    check=False, capture=True)
    need(worker.returncode == 0, "WORKER_IMAGE_NOT_LOCAL")
    labels = json.loads(worker.stdout)[0]["Config"]["Labels"]
    need(labels.get("com.aot.jason.source_revision") == PREVIOUS and
         labels.get("com.aot.jason.component") == "pmv4-ticket-core",
         "WORKER_IMAGE_NOT_APPROVED")
    # Preserve the original root hash chain and its canonical fallback.
    rows = c._audit_rows(prior)
    need(bool(rows) and any(x["event"] == "rolled_back_to_embedded_new_canonical"
                            for x in rows) and
         rows[-1]["event"] == "rolled_back_to_embedded_new_canonical",
         "PREVIOUS_POSTWRITE_FALLBACK_UNVERIFIED")
    host = guard.IndependentHostGuard()
    host._assert_protected_release_state()
    need(host.preexisting_core_health() is True, "TICKET_CORE_HEALTH_FAILED")
    c._source_and_ci(plan)
    need(not c._audit_path(plan).exists(), "RELEASE_ALREADY_CONSUMED")
    return plan, host


def rollback(plan: dict, approval: str, *, policy_changed: bool) -> None:
    # No data moves, deletes or copies. Existing verified embedded runtime
    # is always recovered before any fresh provider admission.
    backup = "jason-runtime-rollback-pmv4cresume-" + plan["candidate_sha"][:12]
    c._stop(c.WORKER)
    c._rm(c.WORKER)
    if c._docker_exists(backup):
        c._stop("jason-runtime")
        c._rm("jason-runtime")
        c._run(["/usr/bin/docker", "rename", backup, "jason-runtime"])
        c._run(["/usr/bin/docker", "start", "jason-runtime"])
    elif c._docker_exists("jason-runtime") and not c._container_running("jason-runtime"):
        c._run(["/usr/bin/docker", "start", "jason-runtime"])
    c._wait_container("jason-runtime", healthy=True, seconds=120)
    if policy_changed:
        meta = c.WATCHDOG.lstat()
        c._atomic_policy((ARTIFACTS / ("pmv4-c-resume-" + plan["candidate_sha"]) /
                          "watchdog-base.json").read_bytes(), meta=meta)
        need(c.sha(c.WATCHDOG.read_bytes()) == plan["watchdog_base_sha256"],
             "WATCHDOG_ROLLBACK_FAILED")
    c._append(plan, approval, "rolled_back_embedded_canonical", {
        "no_database_relocation": True, "mcp_untouched": True})


def execute(path: Path) -> None:
    plan, host = preflight(path)
    approval = verify_owner(plan, path)
    manifest = c.read_json(path.parent / "service-manifest.json")
    backup = "jason-runtime-rollback-pmv4cresume-" + plan["candidate_sha"][:12]
    # Reuse the previously proven native exact Docker clone and worker manifest.
    command, environment, networks = c._clone_command(
        plan, "jason-runtime", "jason-runtime", "runtime",
        {"JASON_TICKET_WORKER_HOSTING": "external"}, ())
    worker_command = c._worker_create(manifest)
    policy_changed = False
    with host.host_release_transaction():
        host._assert_protected_release_state()
        preflight(path)
        c._ensure_root_state()
        baseline_id, baseline_at = c._wait_ticket_idle(
            c.TICKET_TARGET / "autonomy-operational-work.sqlite3")
        c._append(plan, approval, "begin", {
            "baseline_id": baseline_id, "baseline_at": baseline_at,
            "no_database_relocation": True, "mcp_untouched": True,
            "runtime_restart_only": True})
        try:
            c._stop("jason-runtime")
            c._run(["/usr/bin/docker", "rename", "jason-runtime", backup])
            policy_meta = c.WATCHDOG.lstat()
            policy_changed = True
            reviewed_policy = (path.parent / "watchdog-candidate.json").read_bytes()
            need(c.sha(reviewed_policy) == plan["watchdog_candidate_sha256"],
                 "WATCHDOG_PACKET_CHANGED_DURING_CUTOVER")
            c._atomic_policy(reviewed_policy, meta=policy_meta)
            need(c.sha(c.WATCHDOG.read_bytes()) == plan["watchdog_candidate_sha256"],
                 "WATCHDOG_NOT_EXACT_AFTER_WRITE")
            c._run(command, env=environment)
            c._connect_and_start("jason-runtime", networks, env=environment)
            c._wait_container("jason-runtime", healthy=True, seconds=120)
            c._run(worker_command)
            c._run(["/usr/bin/docker", "start", c.WORKER])
            item = c._wait_container(c.WORKER, healthy=True, seconds=180)
            service.validate_effective_inspect(item, manifest)
            need(c._docker_json("jason-mcp-pilot")["Id"] ==
                 plan["mcp_container_id"], "MCP_CHANGED_DURING_CUTOVER")
            c._append(plan, approval, "activated", {
                "new_state": "external_worker", "db_migrations": 0,
                "mcp_restarts": 0})
        except BaseException:
            try:
                rollback(plan, approval, policy_changed=policy_changed)
            except BaseException:
                c._append(plan, approval, "requires_review", {
                    "reason": "POSTMIGRATION_ROLLBACK_UNVERIFIED"})
            raise
    print("PMV4_C_CANONICAL_WORKER_HANDOFF=ACTIVATED_PENDING_POSTFLIGHT", flush=True)


def postflight(path: Path) -> None:
    plan, prior = packet(path)
    release_sources(plan)
    approval = verify_owner(plan, path, recovery=True)
    rows = c._audit_rows(plan)
    need(rows and rows[-1]["event"] == "activated", "POSTFLIGHT_NOT_ACTIVATED")
    try:
        runtime = c._wait_container("jason-runtime", healthy=True, seconds=30)
        mcp = c._wait_container("jason-mcp-pilot", healthy=False, seconds=30)
        worker = c._wait_container(c.WORKER, healthy=True, seconds=60)
        manifest = c.read_json(path.parent / "service-manifest.json")
        service.validate_effective_inspect(worker, manifest)
        need(runtime["Image"] == plan["runtime_image_digest"] and
             mcp["Id"] == plan["mcp_container_id"] and
             mcp["Image"] == plan["mcp_image_digest"], "POSTFLIGHT_PROTECTED_CORE_CHANGED")
        # Startup/transitional drift is not a production acceptance signal.
        # Require two authoritative ticket scans before evaluating the exact
        # final state. Do NOT weaken the actual native drift/watchdog gate.
        baseline = rows[0]["details"]["baseline_at"]
        scans = c._wait_two_scans(baseline)
        # The live protected policy is root-only. A standalone drift probe
        # against its path has failed with exit 1 and no structured drift
        # report even though the native watchdog independently passed.
        # Run this redundant read-only probe on the exact SHA-reviewed
        # candidate bytes, but REQUIRE the installed root policy to match.
        candidate_path = path.parent / "watchdog-candidate.json"
        candidate_bytes = candidate_path.read_bytes()
        need(c.sha(candidate_bytes) == plan["watchdog_candidate_sha256"] and
             c.WATCHDOG.read_bytes() == candidate_bytes,
             "POSTFLIGHT_INSTALLED_POLICY_NOT_EXACT")
        # Root's exact release process may inherit a restricted PATH without
        # /usr/sbin. The native guard invokes runuser for user-systemd reads;
        # without /usr/sbin this raises FileNotFoundError, not host drift.
        # Keep all subprocess executables within trusted root-owned dirs.
        native_probe_env = os.environ.copy()
        native_probe_env["PATH"] = "/usr/sbin:/usr/bin:/bin"
        drift = c._run([
            "/usr/bin/python3", "/opt/jason/current/tools/production_drift_guard.py",
            "--config", str(candidate_path)], check=False, capture=True,
            timeout=45, env=native_probe_env)
        if drift.returncode != 0:
            # Preserve a bounded, structural reason in the visible failed
            # postflight. No secrets, credentials or provider payloads.
            try:
                observed = json.loads(drift.stdout)
                kinds = [
                    {key: val for key, val in item.items()
                     if key in ("kind", "unit", "container", "count", "maximum", "state")}
                    for item in observed.get("problems", [])
                    if isinstance(item, dict)
                ]
                print("PMV4_C_FINAL_DRIFT_PROBLEMS=" +
                      json.dumps(kinds[:12], sort_keys=True)[:2400],
                      file=sys.stderr, flush=True)
            except (ValueError, TypeError, AttributeError):
                # Only the exception class; never emit paths, credentials, or
                # arbitrary stderr payloads from the native probe.
                lines = (getattr(drift, "stderr", None) or "").strip().splitlines()
                fault = lines[-1].split(":", 1)[0] if lines else "unknown"
                if not fault.isidentifier() or len(fault) > 64:
                    fault = "unknown"
                print("PMV4_C_FINAL_DRIFT_PROBE_FAILED=" +
                      str(drift.returncode) + ";exception=" + fault,
                      file=sys.stderr, flush=True)
        need(drift.returncode == 0, "POSTFLIGHT_FINAL_DRIFT_DENIED")
        watchdog = c._run([
            "/usr/bin/python3", "/opt/jason/current/tools/production_drift_watchdog.py",
            "--config", str(c.WATCHDOG)], check=False, capture=True,
            timeout=45, env=native_probe_env)
        need(watchdog.returncode == 0, "POSTFLIGHT_WATCHDOG_FAILED")
        need(c.sha(c.FREEZE.read_bytes()) == plan["freeze_sha256"] and
             c.sha(c.HOLD.read_bytes()) == plan["hold_sha256"], "PROTECTED_FREEZE_CHANGED")
        with guard.IndependentHostGuard().host_release_transaction():
            host = guard.IndependentHostGuard()
            host._assert_protected_release_state()
            c._append(plan, approval, "committed", {
                "scan_cycle_ids": [scans[0][0], scans[1][0]],
                "duplicate_items": [scans[0][4], scans[1][4]],
                "no_database_relocation": True, "mcp_untouched": True})
            receipt_path = c._receipt_path(plan, approval)
            need(not receipt_path.exists() and not receipt_path.is_symlink(),
                 "ACCEPTANCE_RECEIPT_EXISTS")
            receipt = {
                "schema_version": "1.0",
                "status": "postmigration_stage_c_accepted",
                "approval_id": approval,
                "candidate_sha": plan["candidate_sha"],
                "plan_sha256": c.sha(c.canon(plan)),
                "scan_cycle_ids": [scans[0][0], scans[1][0]],
                "no_database_relocation": True,
                "mcp_restarts": 0,
                "committed_at": datetime.now(timezone.utc).isoformat(),
            }
            fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(c.canon(receipt))
                out.flush()
                os.fsync(out.fileno())
        print("PMV4_C_TWO_REAL_SCANS=PASS", flush=True)
        print("PMV4_C_INDEPENDENT_WORKER=ACCEPTED", flush=True)
    except BaseException:
        with guard.IndependentHostGuard().host_release_transaction():
            rollback(plan, approval, policy_changed=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--postflight", action="store_true")
    args = parser.parse_args()
    try:
        if args.preflight:
            preflight(args.plan)
            print("PMV4_C_CANONICAL_ROOT_PREFLIGHT=PASS")
        elif args.execute:
            execute(args.plan)
        else:
            postflight(args.plan)
        return 0
    except BaseException as exc:
        print("PMV4_C_CANONICAL_ROOT_DENIED:" + type(exc).__name__ +
              ":" + str(exc)[:200], file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
