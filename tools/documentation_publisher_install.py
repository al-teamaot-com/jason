#!/usr/bin/env python3
"""One exact Owner-authenticated deployment of the existing documentation publisher.

Reuses the reviewed Entra verifier, protected source/CI attestor and host locks.
No runtime/MCP restart, production promotion, provider grant or policy change.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
BASE = Path("/usr/local/lib/jason/documentation-reconciliation")
DROPIN = Path("/etc/systemd/system/jason-documentation-reconciliation.service.d/20-reviewed-publisher.conf")
UNIT = Path("/etc/systemd/system/jason-documentation-reconciliation.service")
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
MARKER = Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
DOC_REPO = Path("/home/al/.local/lib/jason/documentation-source-repo")
WORKTREE = Path("/home/al/jason-worktrees/documentation-reconcile-current")
ACTION = "INSTALL-EXACT-DOCUMENTATION-PUBLISHER-REPAIR"
PRIMITIVES = "7b90d04e5a35a6ab01f32b09712814d805fa982f35bad3eae22b440fd71d34fa"
FILES = ("tools/documentation_source_reconciler.py", "tools/publish_documentation_reconciliation.sh")


class DocumentationInstallDenied(PermissionError):
    pass


def need(ok, code):
    if not ok:
        raise DocumentationInstallDenied("DOCUMENTATION_INSTALL_" + code)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def primitives():
    path = REPO / "tools/pmv4_e_operational_closure.py"
    raw = path.read_bytes()
    need(digest(raw) == PRIMITIVES, "REVIEWED_PRIMITIVES_CHANGED")
    ns = {"__name__": "documentation_reviewed_primitives", "__file__": str(path)}
    exec(compile(raw, str(path), "exec"), ns)
    return ns, ns["approved_namespace"]()


def dropin_bytes(source_sha):
    return ("[Service]\nExecStart=\nExecStart=/usr/bin/python3 -B "
            + str(BASE / source_sha / "tools/documentation_source_reconciler.py")
            + "\n").encode()


def inspect(source_sha, c, ns):
    need(not os.path.lexists(BASE) and not os.path.lexists(DROPIN), "ONE_USE_TARGET_ALREADY_PRESENT")
    c["directory"](BASE.parent, 0)
    unit_raw = c["read"](UNIT, 0, 0o644)
    need(b"User=al\n" in unit_raw and b"Group=al\n" in unit_raw
         and b"ProtectSystem=strict\n" in unit_raw
         and b"ExecStart=/usr/bin/python3 /opt/jason/current/tools/documentation_source_reconciler.py\n" in unit_raw,
         "EXISTING_SERVICE_CHANGED")
    if DROPIN.parent.exists():
        c["directory"](DROPIN.parent, 0)
    state = c["props"](UNIT.name, False)
    need(state["ActiveState"] in ("failed", "inactive") and state.get("DropInPaths", "") == "",
         "SERVICE_BUSY_OR_OVERRIDDEN")
    marker = json.loads(c["read"](MARKER, 0, 0o444))
    need(marker["state"] == "accepted" and marker["source_sha"] == c["CONTROL_SHA"],
         "STAGE_E_NOT_ACCEPTED")
    need(digest(c["read"](c["ROOT_POLICY"], 0, 0o600)) == c["ACCEPTED_POLICY"], "ROOT_POLICY_CHANGED")
    control = json.loads(c["read"](MANAGER / "production-control-state.json", 0, 0o600))
    drift = json.loads(c["read"](MANAGER / "production-drift.json", 0, 0o600))
    need(control["circuit_breaker"]["state"] == "closed" and drift["status"] == "pass"
         and drift["problems"] == [], "PRODUCTION_GATE")
    observed = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
    need(0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= 180, "DRIFT_STALE")
    need(Path("/opt/jason/current").resolve().name == c["ROLLBACK"], "RUNTIME_SOURCE_CHANGED")
    for path, uid, mode, expected in (
        (ns["FREEZE"], 1000, 0o600, ns["FREEZE_HASH"]),
        (ns["HOLD"], 1000, 0o664, ns["HOLD_HASH"]),
        (ns["WORKER"], 0, 0o755, ns["WORKER_BEFORE"]),
    ):
        need(digest(c["read"](path, uid, mode)) == expected, "PROTECTED_BASELINE_CHANGED")
    records = Path("/var/lib/jason/independent-component-release/releases") / c["CONTROL_SHA"]
    inventory = json.loads(c["read"](records / "source-scope.json", 0, 0o444))
    need(digest(canon(inventory)) == c["ACCEPTED_SCOPE"], "ACCEPTED_SCOPE_CHANGED")
    hashes = inventory["exact_replacement_files_sha256"]
    need(len(hashes) == 64, "NATIVE_INVENTORY_CHANGED")
    code = {name: c["read"](c["NATIVE"] / name, 0, 0o444) for name in hashes}
    need(all(digest(raw) == hashes[name] for name, raw in code.items()), "NATIVE_CODE_CHANGED")
    payload = {name: (REPO / name).read_bytes() for name in FILES}
    code.update(payload)
    code["tools/documentation_publisher_install.py"] = Path(__file__).read_bytes()
    code["tools/pmv4_e_operational_closure.py"] = (REPO / "tools/pmv4_e_operational_closure.py").read_bytes()
    ns["current_ci"](code, source_sha)
    # Source repository and existing publisher work are inspected as their owner.
    c["directory"](DOC_REPO, 1000)
    need(c["git"](DOC_REPO, "status", "--porcelain", "--untracked-files=all") == "",
         "SOURCE_REPOSITORY_DIRTY")
    pending = json.loads(c["run"]([
        *c["USER"], "/usr/bin/gh", "pr", "list", "--repo", "al-teamaot-com/jason",
        "--state", "open", "--limit", "500", "--json", "title,headRefName",
    ]))
    need(not any(row.get("title", "").startswith("Reconcile automated documentation state for ")
                 and row.get("headRefName", "").startswith("automation/documentation-reconcile-")
                 for row in pending), "RECONCILE_EXISTING_GENERATED_PR_FIRST")
    if WORKTREE.exists():
        need((WORKTREE / ".git").is_file(), "UNREGISTERED_WORKTREE")
        need(c["git"](WORKTREE, "status", "--porcelain", "--untracked-files=all") == "",
             "PUBLISHER_WORKTREE_DIRTY")
    scope = {
        "action": ACTION,
        "policy": {"candidate_sha": source_sha, "rollback_sha": c["ROLLBACK"]},
        "queue_cutover": False,
        "installation_targets": [str(BASE), str(BASE / source_sha), str(DROPIN)],
        "source_files_sha256": {name: digest(raw) for name, raw in payload.items()},
        "executor_sha256": digest(Path(__file__).read_bytes()),
        "unit_before_sha256": digest(unit_raw),
        "dropin_sha256": digest(dropin_bytes(source_sha)),
        "protected_peers": c["peers"](),
        "root_policy_sha256": c["ACCEPTED_POLICY"],
        "accepted_marker_sha256": digest(c["read"](MARKER, 0, 0o444)),
        "freeze_sha256": ns["FREEZE_HASH"], "hold_sha256": ns["HOLD_HASH"],
        "existing_documentation_service_start_allowed": True,
        "existing_source_documentation_publication_allowed": True,
        "runtime_or_mcp_restart_allowed": False,
        "provider_mutations_allowed": False, "standing_authority": False,
    }
    return scope, payload


class Package:
    def __init__(self, c, source_sha, *, base=BASE, dropin=DROPIN, production=True):
        need(not production or (os.geteuid() == 0 and base == BASE and dropin == DROPIN),
             "PRODUCTION_PATH_OVERRIDE")
        self.c, self.source_sha, self.base, self.dropin = c, source_sha, base, dropin
        self.created = False
        self.base_created = False
        self.parent_created = False

    def apply(self, payload, approval):
        self.base.mkdir(mode=0o700)
        self.base_created = True
        self.c["write"](self.base / "approval.json", canon(approval))
        source = self.base / self.source_sha
        source.mkdir(mode=0o755)
        (source / "tools").mkdir(mode=0o755)
        for name, raw in payload.items():
            self.c["write"](source / name, raw, 0o444)
        # Root journals are private; the service needs only traversal of source.
        self.base.chmod(0o755)
        if not self.dropin.parent.exists():
            self.dropin.parent.mkdir(mode=0o755)
            self.parent_created = True
        self.c["directory"](self.dropin.parent, 0)
        self.c["write"](self.dropin, dropin_bytes(self.source_sha), 0o644)
        self.created = True

    def restore(self):
        if self.created:
            need(self.c["read"](self.dropin, 0, 0o644) == dropin_bytes(self.source_sha),
                 "FOREIGN_SERVICE_OVERRIDE")
            self.dropin.unlink()
        if self.parent_created and not any(self.dropin.parent.iterdir()):
            self.dropin.parent.rmdir()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--source-sha", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    need(os.geteuid() == 0 and sys.flags.isolated == 1
         and re.fullmatch("[0-9a-f]{40}", a.source_sha), "ISOLATED_ROOT_REQUIRED")
    c, ns = primitives()
    with ns["locks"]():
        scope, payload = inspect(a.source_sha, c, ns)
    if not a.apply:
        print(json.dumps({"status": "documentation_read_only_root_preflight_passed",
                          "scope_sha256": digest(canon(scope)), "scope": scope}, sort_keys=True))
        return
    actor = ns["owner"](scope)
    tx = Package(c, a.source_sha)
    started = False
    try:
        with ns["locks"]():
            again, _ = inspect(a.source_sha, c, ns)
            need(again == scope, "APPROVED_SCOPE_CHANGED")
            tx.apply(payload, {"scope": scope, "owner_oid": actor,
                              "approved_at": datetime.now(timezone.utc).isoformat()})
            c["systemctl"](["daemon-reload"])
        c["systemctl"](["reset-failed", UNIT.name])
        c["systemctl"](["start", "--no-block", UNIT.name])
        started = True
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = c["props"](UNIT.name, False)
            if state["ActiveState"] not in ("active", "activating", "deactivating"):
                break
            time.sleep(2)
        result = c["run"](["/usr/bin/systemctl", "show", UNIT.name,
                          "--property=Result,ExecMainStatus"])
        need(state["ActiveState"] == "inactive" and "Result=success" in result
             and "ExecMainStatus=0" in result, "SCHEDULED_PUBLISHER_DID_NOT_PASS")
        generated = json.loads((WORKTREE / "docs/control/AUTOMATED-CHANGE-STATE.json").read_bytes())
        need(generated.get("validated_source", {}).get("revision") == a.source_sha,
             "GENERATED_SOURCE_READBACK_NOT_CURRENT")
        c["systemctl"](["start", "jason-production-drift-watchdog.service"])
        drift = json.loads(c["read"](MANAGER / "production-drift.json", 0, 0o600))
        need(drift["status"] == "pass" and drift["problems"] == [], "POST_INSTALL_DRIFT")
        need(c["peers"]() == scope["protected_peers"], "PROTECTED_PEERS_CHANGED")
        need(digest(c["read"](c["ROOT_POLICY"], 0, 0o600)) == scope["root_policy_sha256"]
             and digest(c["read"](MARKER, 0, 0o444)) == scope["accepted_marker_sha256"],
             "PROTECTED_POLICY_CHANGED")
        need(digest(c["read"](ns["FREEZE"], 1000, 0o600)) == ns["FREEZE_HASH"]
             and digest(c["read"](ns["HOLD"], 1000, 0o664)) == ns["HOLD_HASH"],
             "FREEZE_OR_HOLD_CHANGED")
        c["write"](BASE / "accepted.json", canon({
            "status": "documentation_publisher_operationally_verified",
            "source_sha": a.source_sha, "scope_sha256": digest(canon(scope)),
            "protected_services_changed": False, "provider_mutations": False,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        }))
        print("DOCUMENTATION_PUBLISHER_REPAIR=VERIFIED")
    except BaseException:
        # Restore only this exact override. Preserve source, approvals and
        # generated PRs for reconciliation; never overwrite foreign work.
        if tx.base_created:
            if started:
                c["systemctl"](["stop", UNIT.name])
            with ns["locks"]():
                tx.restore()
                c["systemctl"](["daemon-reload"])
            c["write"](BASE / "verification-failed.json", canon({
                "status": "documentation_repair_requires_readback_recovery",
                "original_service_override_restored": True,
            }))
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("DENIED:" + type(exc).__name__ + ":" + str(exc)[:500])
