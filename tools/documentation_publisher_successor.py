#!/usr/bin/env python3
"""Reauthorize activation of the sealed, unchanged documentation repair.

The previous attempt is immutable and its old approval has expired. Reuse the
existing exact Owner verifier, host locks, native health and override/rollback
implementation. No code replacement, new timer, provider grant or runtime deploy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

REPO = Path(__file__).resolve().parents[1]
ACTION = "REAUTHORIZE-EXACT-DOCUMENTATION-PUBLISHER"
OLD_SCOPE = "fcd803b81e61952a156387b47b9e45da4e9204237bd9f0211782c49b69c70031"
PINS = {
    "tools/parallel_development_install.py": "e38e1c4f227d9d785c5610f6dece06b16064d98e7bc1ddd9f74cbb299ed198c8",
    "tools/documentation_publisher_readback_recovery.py": "e593aafc59b9ae11351a41a6b532e714cbad05c129794dd666dabd635bfa8822",
    "tools/documentation_publisher_install.py": "31af4fcfa40e6e976c10dc2bef8709f32e542358f89929b232dc18b8295f027a",
    "tools/pmv4_e_operational_closure.py": "7b90d04e5a35a6ab01f32b09712814d805fa982f35bad3eae22b440fd71d34fa",
    "tools/pmv4_e_dispatch_install.py": "6d276b67538e1bf988a751dc9ef10ac6996cc6955ff6bc3e562a506da13282f7",
}
BRANCH = "automation/documentation-reconcile-current"


def need(ok, why):
    if not ok:
        raise PermissionError("DOCUMENTATION_SUCCESSOR_" + why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_bytes(name):
    path = REPO / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        m = os.fstat(f.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_uid == m.st_gid == 1000
             and m.st_nlink == 1 and not m.st_mode & 0o022
             and 0 < m.st_size <= 2_000_000, "SOURCE_CUSTODY:" + name)
        raw = f.read(2_000_001)
        need(len(raw) == m.st_size, "SOURCE_CHANGED:" + name)
    return raw


def load_helpers():
    # Validate all transitive Root code BEFORE executing any helper.
    raw = {name: source_bytes(name) for name in PINS}
    need(all(digest(b) == PINS[n] for n, b in raw.items()), "REVIEWED_HELPER_CHANGED")
    loaded = []
    for name in tuple(PINS)[:2]:
        ns = {"__name__": "documentation_successor_review", "__file__": str(REPO / name)}
        exec(compile(raw[name], str(REPO / name), "exec"), ns)
        loaded.append(ns)
    p, recovery = loaded
    d, c, ns = recovery["original"]()
    return p, recovery, d, c, ns


def historical(approval, failed):
    need(isinstance(approval, dict) and set(approval) == {"scope", "owner_oid", "approved_at"}
         and digest(canon(approval["scope"])) == OLD_SCOPE, "OLD_SCOPE_CHANGED")
    need(failed == {"status": "documentation_repair_requires_readback_recovery",
                    "original_service_override_restored": True}, "OLD_FAILURE_CHANGED")
    return approval["scope"]


def attested_source(candidate, p, names):
    need(p["exact_sha"](candidate)
         and p["git"](REPO, "rev-parse", "HEAD").decode().strip() == candidate
         and not p["git"](REPO, "status", "--porcelain", "--untracked-files=all").strip()
         and p["git"](REPO, "remote", "get-url", "origin").decode().strip() == p["REMOTE"],
         "EXACT_SOURCE_REQUIRED")
    native = p["NATIVE"] / "pmv4_e_ci_refresh.py"
    ci = p["native_code"](native, str(native), 0, 0o444)
    attestor = ci["load_pinned_attestor"](ci["SOURCE"], production=True)
    ci["paginate_required_checks"](attestor)
    result = attestor["verify_ci"](candidate)
    head = p["command"]([*p["USER"], "/usr/bin/git", "ls-remote", p["REMOTE"],
                         "refs/heads/main"]).decode().split()
    need(result["candidate_sha"] == candidate and result["required_ci_passed"] is True
         and result["protected_main_ancestor"] is True
         and result["protected_main"] == candidate
         and head == [candidate, "refs/heads/main"], "CURRENT_PROTECTED_CI_REQUIRED")
    files = {}
    for name in sorted(names):
        b = source_bytes(name)
        need(b == p["git"](REPO, "show", candidate + ":" + name), "SOURCE_NOT_GIT:" + name)
        files[name] = digest(b)
    return files


def service_readback(c, d):
    raw = c["systemctl"](["show", d["UNIT"].name, "--property=ActiveState,Result,"
                           "ExecMainStatus,ExecMainStartTimestampMonotonic,MainPID,ExecStart,DropInPaths"])
    return dict(row.split("=", 1) for row in raw.splitlines() if "=" in row)


def inspect(candidate, p, r, d, c, ns):
    base = d["BASE"]
    c["directory"](base, 0, 0o755)
    record = base / ("successor-" + candidate)
    need(not os.path.lexists(base / "accepted.json") and not os.path.lexists(record)
         and not os.path.lexists(d["DROPIN"]), "ALREADY_ATTEMPTED_OR_OVERRIDE_EXISTS")
    old_approval = c["read"](base / "approval.json", 0, 0o400)
    old_failure = c["read"](base / "verification-failed.json", 0, 0o400)
    prior = historical(json.loads(old_approval), json.loads(old_failure))
    need(digest(c["read"](d["UNIT"], 0, 0o644)) == prior["unit_before_sha256"],
         "ORIGINAL_UNIT_CHANGED")
    if d["DROPIN"].parent.exists():
        c["directory"](d["DROPIN"].parent, 0)
    state = service_readback(c, d)
    need(state["ActiveState"] in ("inactive", "failed") and state["MainPID"] == "0"
         and state["DropInPaths"] == "", "PUBLISHER_BUSY_OR_OVERRIDDEN")
    c["directory"](base / r["ORIGINAL_SOURCE"], 0, 0o755)
    c["directory"](base / r["ORIGINAL_SOURCE"] / "tools", 0, 0o755)
    names = set(PINS) | set(d["FILES"]) | {
        "tools/documentation_publisher_successor.py",
        "tools/tests/test_documentation_publisher_successor.py"}
    sources = attested_source(candidate, p, names)
    for name in d["FILES"]:
        raw = c["read"](base / r["ORIGINAL_SOURCE"] / name, 0, 0o444)
        need(digest(raw) == prior["source_files_sha256"][name] == sources[name],
             "SEALED_PAYLOAD_CHANGED")
    # The old publication failed before writing generated source, and the
    # corrected worktree ownership is now independently checked.
    r["require_worktree_owner"](c, d["DOC_REPO"], d["WORKTREE"])
    pending = json.loads(c["run"]([*c["USER"], "/usr/bin/gh", "pr", "list",
        "--repo", "al-teamaot-com/jason", "--state", "open", "--limit", "500",
        "--json", "headRefName"]))
    need(len(pending) < 500 and not any(x["headRefName"].startswith(
         "automation/documentation-reconcile-") for x in pending), "GENERATED_PR_PENDING")
    refs = p["git"](REPO, "ls-remote", "--heads", "origin", BRANCH).decode().split()
    need(len(refs) == 2 and p["exact_sha"](refs[0]) and refs[1] == "refs/heads/" + BRANCH,
         "GENERATED_BRANCH_UNKNOWN")
    p["git"](REPO, "merge-base", "--is-ancestor", refs[0], candidate)
    health = p["protected_health"](expected_guard_sha=p["GUARD_AFTER_SHA"])
    marker = c["read"](d["MARKER"], 0, 0o444)
    need(json.loads(marker)["state"] == "accepted", "STAGE_E_NOT_ACCEPTED")
    raw = d["dropin_bytes"](r["ORIGINAL_SOURCE"])
    need(digest(raw) == prior["dropin_sha256"], "ORIGINAL_OVERRIDE_CHANGED")
    return {
        "action": ACTION, "policy": {"candidate_sha": candidate, "rollback_sha": p["ROLLBACK"]},
        "queue_cutover": False, "standing_authority": False,
        "historical_scope_sha256": OLD_SCOPE, "historical_approval_sha256": digest(old_approval),
        "historical_failure_sha256": digest(old_failure),
        "historical_payload_revision": r["ORIGINAL_SOURCE"],
        "source_sha256": sources, "protected_health": health, "stage_e_marker_sha256": digest(marker),
        "unit_before_sha256": prior["unit_before_sha256"], "dropin_sha256": digest(raw),
        "dropin_parent_preexisting": d["DROPIN"].parent.exists(),
        "installation_targets": [str(d["DROPIN"]), str(record)],
        "existing_service_start_allowed": True, "generated_documentation_and_board_publication_allowed": True,
        "existing_worktree_head": c["git"](d["WORKTREE"], "rev-parse", "HEAD"),
        "generated_branch_before": refs[0],
        "previous_service_start": state["ExecMainStartTimestampMonotonic"],
        "runtime_or_mcp_restart_allowed": False, "provider_mutations_allowed": False,
        "pause_or_freeze_change": False, "rollback_removes_exact_override_only": True,
    }


def verify_publication(candidate, scope, p, d, c):
    deadline = time.monotonic() + 330
    while time.monotonic() < deadline:
        state = service_readback(c, d)
        fresh = state["ExecMainStartTimestampMonotonic"] != scope["previous_service_start"]
        if fresh and state["ActiveState"] == "inactive" and state["Result"] == "success" \
                and state["ExecMainStatus"] == "0":
            break
        if fresh and state["ActiveState"] == "failed":
            raise PermissionError("DOCUMENTATION_SUCCESSOR_PUBLISHER_FAILED")
        time.sleep(2)
    else:
        raise PermissionError("DOCUMENTATION_SUCCESSOR_PUBLISHER_TIMEOUT")
    need(str(d["DROPIN"]) in state["DropInPaths"], "APPROVED_OVERRIDE_NOT_ACTIVE")
    generated = json.loads((d["WORKTREE"] / "docs/control/AUTOMATED-CHANGE-STATE.json").read_bytes())
    need(generated.get("validated_source", {}).get("revision") == candidate,
         "GENERATED_SOURCE_NOT_CURRENT")
    tip = c["git"](d["WORKTREE"], "rev-parse", "HEAD")
    need(p["exact_sha"](tip) and not c["git"](d["WORKTREE"], "status", "--porcelain",
         "--untracked-files=all"), "GENERATED_WORKTREE_NOT_CLEAN")
    refs = p["git"](d["DOC_REPO"], "ls-remote", "--heads", "origin", BRANCH).decode().split()
    need(refs == [tip, "refs/heads/" + BRANCH], "GENERATED_REMOTE_NOT_CURRENT")
    p["git"](d["DOC_REPO"], "merge-base", "--is-ancestor", candidate, tip)
    return tip


def execute(candidate, expected, p, r, d, c, ns):
    actor = ns["owner"](expected)
    record = d["BASE"] / ("successor-" + candidate)
    raw = d["dropin_bytes"](r["ORIGINAL_SOURCE"])
    tx = r["Override"](c)
    started = False
    approved = False
    try:
        with ns["locks"]():
            need(inspect(candidate, p, r, d, c, ns) == expected, "APPROVED_SCOPE_CHANGED")
            record.mkdir(mode=0o700)
            c["sync_dir"](record.parent)
            c["write"](record / "approval.json", canon({"scope": expected,
                "scope_sha256": digest(canon(expected)), "owner_oid": actor,
                "approved_at": p["stamp"]()}))
            approved = True
            tx.apply(raw)
            c["systemctl"](["daemon-reload"])
        c["systemctl"](["reset-failed", d["UNIT"].name])
        c["systemctl"](["start", "--no-block", d["UNIT"].name])
        started = True
        tip = verify_publication(candidate, expected, p, d, c)
        with ns["locks"]():
            need(p["protected_health"](expected_guard_sha=p["GUARD_AFTER_SHA"])
                 == expected["protected_health"], "PROTECTED_STATE_CHANGED")
            need(digest(c["read"](d["DROPIN"], 0, 0o644)) == expected["dropin_sha256"],
                 "OVERRIDE_READBACK_CHANGED")
            result = {"status": "documentation_publisher_operationally_verified",
                      "source_sha": r["ORIGINAL_SOURCE"], "validated_revision": candidate,
                      "generated_branch_tip": tip, "scope_sha256": digest(canon(expected)),
                      "accepted_at": p["stamp"](), "provider_mutations": False}
            c["write"](record / "result.json", canon(result))
        print("DOCUMENTATION_PUBLISHER_SUCCESSOR=VERIFIED", flush=True)
    except BaseException:
        if approved:
            if started:
                c["systemctl"](["stop", d["UNIT"].name])
            with ns["locks"]():
                tx.restore(raw)
                c["systemctl"](["daemon-reload"])
                c["write"](record / "result.json", canon({"status": "rolled_back",
                    "scope_sha256": digest(canon(expected)), "at": p["stamp"]()}))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    a = parser.parse_args(argv)
    need(os.geteuid() == 0 and sys.flags.isolated == 1, "ROOT_ISOLATION_REQUIRED")
    p, r, d, c, ns = load_helpers()
    with ns["locks"]():
        scope = inspect(a.source_sha, p, r, d, c, ns)
    print(json.dumps({"status": "scope_reviewed_not_deployment_approved",
          "scope_sha256": digest(canon(scope)), "scope": scope}, sort_keys=True), flush=True)
    if a.apply:
        execute(a.source_sha, scope, p, r, d, c, ns)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("DENIED:" + type(exc).__name__ + ":" + str(exc)[:500])
