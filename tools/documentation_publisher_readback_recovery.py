#!/usr/bin/env python3
"""Finish only the unchanged, already-approved documentation configuration step.

The initial installation nonce and approval remain intact. This continuation
requires the root-sealed failed-attempt record, exact original payload/scope,
fresh protected state and repaired Git ownership. It never reinstalls code,
mints a grant, requests another Owner decision, or changes other services.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import time

from_source = Path(__file__).resolve().parents[1]
ORIGINAL_SOURCE = "49d386bf9472c5b2adc78499fe5d6041e6167ebe"
ORIGINAL_EXECUTOR = "31af4fcfa40e6e976c10dc2bef8709f32e542358f89929b232dc18b8295f027a"
MAX_RECOVERY_AGE_SECONDS = 7200


class DocumentationRecoveryDenied(PermissionError):
    pass


def need(ok, code):
    if not ok:
        raise DocumentationRecoveryDenied("DOCUMENTATION_RECOVERY_" + code)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def original():
    path = from_source / "tools/documentation_publisher_install.py"
    raw = path.read_bytes()
    need(digest(raw) == ORIGINAL_EXECUTOR, "ORIGINAL_EXECUTOR_CHANGED")
    d = {"__name__": "approved_documentation_transaction", "__file__": str(path)}
    exec(compile(raw, str(path), "exec"), d)
    c, ns = d["primitives"]()
    return d, c, ns


def validate_approval(approval, failed, *, scope_sha256, owners, now):
    need(isinstance(approval, dict) and set(approval) == {"scope", "owner_oid", "approved_at"},
         "APPROVAL_RECORD_SCHEMA")
    scope = approval["scope"]
    need(digest(canon(scope)) == scope_sha256, "ORIGINAL_SCOPE_CHANGED")
    need(approval["owner_oid"] in owners, "ORIGINAL_OWNER_NOT_TRUSTED")
    at = datetime.fromisoformat(approval["approved_at"])
    need(at.tzinfo is not None and 0 <= (now - at).total_seconds() <= MAX_RECOVERY_AGE_SECONDS,
         "ORIGINAL_DECISION_OUTSIDE_RECOVERY_WINDOW")
    need(scope["action"] == "INSTALL-EXACT-DOCUMENTATION-PUBLISHER-REPAIR"
         and scope["policy"]["candidate_sha"] == ORIGINAL_SOURCE
         and scope["policy"]["rollback_sha"] == "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
         and scope["executor_sha256"] == ORIGINAL_EXECUTOR
         and scope["queue_cutover"] is False
         and scope["runtime_or_mcp_restart_allowed"] is False
         and scope["provider_mutations_allowed"] is False
         and scope["standing_authority"] is False, "ORIGINAL_ACTION_NOT_EXACT")
    need(failed == {"status": "documentation_repair_requires_readback_recovery",
                    "original_service_override_restored": True}, "NOT_FAILED_VERIFICATION_PHASE")
    return scope


def require_worktree_owner(c, repo, work):
    expected = c["git"](repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    observed = c["git"](work, "rev-parse", "--path-format=absolute", "--git-common-dir")
    need(observed == expected, "WORKTREE_BELONGS_TO_DIFFERENT_REPOSITORY")
    need(c["git"](repo, "status", "--porcelain", "--untracked-files=all") == ""
         and c["git"](work, "status", "--porcelain", "--untracked-files=all") == "",
         "PUBLISHER_WORK_NOT_CLEAN")


def inspect(d, c, ns, *, source_sha, scope_sha256):
    base = d["BASE"]
    c["directory"](base, 0, 0o755)
    need(not os.path.lexists(base / "accepted.json"), "ALREADY_ACCEPTED")
    need(not os.path.lexists(base / "recovery-started.json"), "RECOVERY_ALREADY_ATTEMPTED")
    raw = ns["read"](ns["OAUTH"], 0, 0o555, 60_000)
    need(digest(raw) == ns["OAUTH_HASH"], "PINNED_OWNER_VERIFIER_CHANGED")
    auth = ns["load_code"](raw, "historical_documentation_owner_policy", ns["OAUTH"])
    approval = json.loads(c["read"](base / "approval.json", 0, 0o400))
    failed = json.loads(c["read"](base / "verification-failed.json", 0, 0o400))
    scope = validate_approval(approval, failed, scope_sha256=scope_sha256,
                              owners=auth["OWNERS"], now=datetime.now(timezone.utc))
    need(scope["installation_targets"] == [str(base), str(base / ORIGINAL_SOURCE), str(d["DROPIN"])],
         "ORIGINAL_TARGETS_CHANGED")
    need(not os.path.lexists(d["DROPIN"]), "FOREIGN_OVERRIDE_PRESENT")
    need(digest(c["read"](d["UNIT"], 0, 0o644)) == scope["unit_before_sha256"],
         "ORIGINAL_UNIT_CHANGED")
    state = c["props"](d["UNIT"].name, False)
    need(state["ActiveState"] in ("inactive", "failed") and state.get("DropInPaths", "") == "",
         "SERVICE_BUSY_OR_OVERRIDDEN")
    payload = {}
    need(set(scope["source_files_sha256"]) == set(d["FILES"]), "ORIGINAL_FILE_SCOPE_CHANGED")
    for name in d["FILES"]:
        raw = c["read"](base / ORIGINAL_SOURCE / name, 0, 0o444)
        need(digest(raw) == scope["source_files_sha256"][name]
             and raw == (from_source / name).read_bytes(), "ORIGINAL_PAYLOAD_CHANGED")
        payload[name] = raw
    need(digest(d["dropin_bytes"](ORIGINAL_SOURCE)) == scope["dropin_sha256"],
         "ORIGINAL_OVERRIDE_CHANGED")
    need(c["peers"]() == scope["protected_peers"], "PROTECTED_PEERS_CHANGED")
    need(Path("/opt/jason/current").resolve().name == scope["policy"]["rollback_sha"],
         "RUNTIME_SOURCE_CHANGED")
    need(digest(c["read"](c["ROOT_POLICY"], 0, 0o600)) == scope["root_policy_sha256"]
         and digest(c["read"](d["MARKER"], 0, 0o444)) == scope["accepted_marker_sha256"],
         "PROTECTED_POLICY_OR_STAGE_E_CHANGED")
    for path, uid, mode, expected in (
        (ns["FREEZE"], 1000, 0o600, scope["freeze_sha256"]),
        (ns["HOLD"], 1000, 0o664, scope["hold_sha256"]),
        (ns["WORKER"], 0, 0o755, ns["WORKER_BEFORE"]),
    ):
        need(digest(c["read"](path, uid, mode)) == expected, "PROTECTED_BASELINE_CHANGED")
    control = json.loads(c["read"](d["MANAGER"] / "production-control-state.json", 0, 0o600))
    drift = json.loads(c["read"](d["MANAGER"] / "production-drift.json", 0, 0o600))
    need(control["circuit_breaker"]["state"] == "closed" and drift["status"] == "pass"
         and drift["problems"] == [], "PRODUCTION_GATE")
    at = datetime.fromisoformat(drift["observed_at"])
    need(0 <= (datetime.now(timezone.utc) - at).total_seconds() <= 180, "DRIFT_STALE")
    require_worktree_owner(c, d["DOC_REPO"], d["WORKTREE"])
    records = Path("/var/lib/jason/independent-component-release/releases") / c["CONTROL_SHA"]
    inventory = json.loads(c["read"](records / "source-scope.json", 0, 0o444))
    need(digest(canon(inventory)) == c["ACCEPTED_SCOPE"], "NATIVE_SCOPE_CHANGED")
    hashes = inventory["exact_replacement_files_sha256"]
    need(len(hashes) == 64, "NATIVE_INVENTORY_CHANGED")
    code = {name: c["read"](c["NATIVE"] / name, 0, 0o444) for name in hashes}
    need(all(digest(raw) == hashes[name] for name, raw in code.items()), "NATIVE_CODE_CHANGED")
    code.update(payload)
    for name in ("tools/documentation_publisher_install.py",
                 "tools/pmv4_e_operational_closure.py",
                 "tools/documentation_publisher_readback_recovery.py"):
        code[name] = (from_source / name).read_bytes()
    ns["current_ci"](code, source_sha)
    return scope, approval


class Override:
    def __init__(self, c, *, path=None, production=True):
        original_path = Path("/etc/systemd/system/jason-documentation-reconciliation.service.d/20-reviewed-publisher.conf")
        self.path = original_path if path is None else path
        need(not production or (os.geteuid() == 0 and self.path == original_path),
             "PRODUCTION_PATH_OVERRIDE")
        self.c, self.created, self.parent_created = c, False, False

    def apply(self, raw):
        if not self.path.parent.exists():
            self.path.parent.mkdir(mode=0o755)
            self.parent_created = True
        self.c["directory"](self.path.parent, 0)
        self.c["write"](self.path, raw, 0o644)
        self.created = True

    def restore(self, raw):
        if self.created:
            need(self.c["read"](self.path, 0, 0o644) == raw, "FOREIGN_OVERRIDE_ON_ROLLBACK")
            self.path.unlink()
        if self.parent_created and not any(self.path.parent.iterdir()):
            self.path.parent.rmdir()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--source-sha", required=True)
    p.add_argument("--approval-scope-sha256", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    need(os.geteuid() == 0 and sys.flags.isolated == 1
         and os.environ.get("SUDO_USER") == "al" and os.environ.get("SUDO_UID") == "1000",
         "AUTHENTICATED_AL_ROOT_REQUIRED")
    need(re.fullmatch("[0-9a-f]{40}", a.source_sha)
         and re.fullmatch("[0-9a-f]{64}", a.approval_scope_sha256), "EXACT_DIGESTS_REQUIRED")
    d, c, ns = original()
    with ns["locks"]():
        scope, approval = inspect(d, c, ns, source_sha=a.source_sha,
                                  scope_sha256=a.approval_scope_sha256)
    if not a.apply:
        print(json.dumps({"status": "original_approved_recovery_readback_passed",
                          "scope_sha256": a.approval_scope_sha256, "new_authority": False}))
        return
    tx = Override(c)
    raw = d["dropin_bytes"](ORIGINAL_SOURCE)
    started = False
    attempted = False
    try:
        with ns["locks"]():
            again, _ = inspect(d, c, ns, source_sha=a.source_sha,
                               scope_sha256=a.approval_scope_sha256)
            need(again == scope, "ORIGINAL_SCOPE_CHANGED_DURING_RECOVERY")
            c["write"](d["BASE"] / "recovery-started.json", canon({
                "original_scope_sha256": a.approval_scope_sha256,
                "original_owner_oid": approval["owner_oid"],
                "original_publisher_source": ORIGINAL_SOURCE,
                "reviewed_recovery_source": a.source_sha,
                "new_authority": False, "started_at": datetime.now(timezone.utc).isoformat(),
            }))
            attempted = True
            tx.apply(raw)
            c["systemctl"](["daemon-reload"])
        c["systemctl"](["reset-failed", d["UNIT"].name])
        c["systemctl"](["start", "--no-block", d["UNIT"].name])
        started = True
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = c["props"](d["UNIT"].name, False)
            if state["ActiveState"] not in ("active", "activating", "deactivating"):
                break
            time.sleep(2)
        result = c["run"](["/usr/bin/systemctl", "show", d["UNIT"].name,
                          "--property=Result,ExecMainStatus"])
        need(state["ActiveState"] == "inactive" and "Result=success" in result
             and "ExecMainStatus=0" in result, "PUBLISHER_JOB_FAILED")
        need(str(d["BASE"] / ORIGINAL_SOURCE / d["FILES"][0])
             in c["props"](d["UNIT"].name, False)["ExecStart"], "APPROVED_SOURCE_NOT_ACTIVE")
        generated = json.loads((d["WORKTREE"] / "docs/control/AUTOMATED-CHANGE-STATE.json").read_bytes())
        need(generated["validated_source"]["revision"] == a.source_sha,
             "GENERATED_SOURCE_NOT_RECONCILED")
        c["systemctl"](["start", "jason-production-drift-watchdog.service"])
        drift = json.loads(c["read"](d["MANAGER"] / "production-drift.json", 0, 0o600))
        need(drift["status"] == "pass" and drift["problems"] == [], "POST_RECOVERY_DRIFT")
        need(c["peers"]() == scope["protected_peers"], "PROTECTED_PEERS_CHANGED")
        for path, uid, mode, expected in (
            (ns["FREEZE"], 1000, 0o600, scope["freeze_sha256"]),
            (ns["HOLD"], 1000, 0o664, scope["hold_sha256"]),
            (c["ROOT_POLICY"], 0, 0o600, scope["root_policy_sha256"]),
            (d["MARKER"], 0, 0o444, scope["accepted_marker_sha256"]),
        ):
            need(digest(c["read"](path, uid, mode)) == expected, "PROTECTION_CHANGED")
        c["write"](d["BASE"] / "accepted.json", canon({
            "status": "documentation_publisher_operationally_verified",
            "source_sha": ORIGINAL_SOURCE, "scope_sha256": a.approval_scope_sha256,
            "recovery_source_sha": a.source_sha, "protected_services_changed": False,
            "provider_mutations": False, "accepted_at": datetime.now(timezone.utc).isoformat(),
        }))
        print("DOCUMENTATION_PUBLISHER_REPAIR=VERIFIED")
    except BaseException:
        if attempted:
            if started:
                c["systemctl"](["stop", d["UNIT"].name])
            with ns["locks"]():
                tx.restore(raw)
                c["systemctl"](["daemon-reload"])
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("DENIED:" + type(exc).__name__ + ":" + str(exc)[:500])
