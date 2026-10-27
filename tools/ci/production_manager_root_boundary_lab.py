#!/usr/bin/env python3
"""Disposable root-worker + systemd request/response/rollback acceptance.

Only for an ephemeral, credential-free GitHub-hosted Ubuntu runner. Never run
on an operational Jason host. This uses the real root-owned reconciliation
worker and circuit transition processor with *lab-scoped* authority inputs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone

HOST_UNIT = "jason-pm-lab-root-reconcile.service"
HOST_PATH = "jason-pm-lab-root-reconcile.path"
BASE_UNIT = "jason-pm-lab-root-baseline.service"
CAND_UNIT = "jason-pm-lab-root-candidate.service"
LAB_MCP = "jason-pm-lab-root-mcp"
UNITS = (HOST_PATH, HOST_UNIT, BASE_UNIT, CAND_UNIT)
SYSTEMD = Path("/etc/systemd/system")
GITHUB = Path(os.environ.get("GITHUB_WORKSPACE", "/unavailable"))


def run(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(arg) for arg in args],
        check=check, text=True, capture_output=capture,
    )


def assert_disposable() -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("JASON_PM_LAB") != "1"
            or os.geteuid() != 0 or not GITHUB.is_dir()
            or not Path("/run/systemd/system").is_dir()):
        raise RuntimeError("only disposable GitHub Actions Ubuntu root systemd runner permitted")
    if any(Path(p).exists() for p in (
        "/opt/jason/current", "/var/lib/jason/openclaw", "/home/al/projects/jason",
    )):
        raise RuntimeError("production/developer Jason paths detected")
    if not GITHUB.joinpath("tools/release_host_reconcile_worker.py").is_file():
        raise RuntimeError("canonical release host worker absent")


def module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, data: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    os.chmod(path, mode)


def write_json(path: Path, value: dict, mode: int = 0o600, uid: int = 0, gid: int = 0):
    write(path, json.dumps(value, sort_keys=True, indent=2) + "\n", mode)
    os.chown(path, uid, gid)


def git(repo: Path, *args: str) -> str:
    return run("git", "-C", str(repo), *args).stdout.strip()


def status(unit: str) -> bool:
    return run("systemctl", "is-active", "--quiet", unit, check=False).returncode == 0


def docker_mcp_revision() -> str:
    result = run(
        "docker", "inspect", LAB_MCP, "--format",
        '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
    ).stdout.strip()
    if not re.fullmatch("[0-9a-f]{40}", result):
        raise RuntimeError("lab MCP has no immutable source revision label")
    return result


def create_mcp(revision: str) -> None:
    run("docker", "rm", "-f", LAB_MCP, check=False)
    run(
        "docker", "run", "--detach", "--name", LAB_MCP, "--network", "none",
        "--label", "com.teamaot.jason.source_revision=" + revision,
        "python:3.12-alpine", "python", "-c", "import time;time.sleep(300)",
    )
    if docker_mcp_revision() != revision:
        raise AssertionError("lab MCP revision readback mismatch")


def host_script(mode: str) -> str:
    action = {
        "baseline": (
            'systemctl stop jason-pm-lab-root-candidate.service >/dev/null 2>&1 || true\n'
            'rm -f /etc/systemd/system/jason-pm-lab-root-candidate.service\n'
            'systemctl daemon-reload\n'
            'systemctl start jason-pm-lab-root-baseline.service\n'
        ),
        "candidate": (
            'cp "$JASON_PM_LAB_STATE/candidate.service" '
            '/etc/systemd/system/jason-pm-lab-root-candidate.service\n'
            'systemctl daemon-reload\n'
            'systemctl start jason-pm-lab-root-candidate.service\n'
        ),
        "fail": (
            'cp "$JASON_PM_LAB_STATE/candidate.service" '
            '/etc/systemd/system/jason-pm-lab-root-candidate.service\n'
            'systemctl daemon-reload\n'
            'systemctl start jason-pm-lab-root-candidate.service\n'
        ),
    }[mode]
    failure = "exit 42\n" if mode == "fail" else ""
    return (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'test "$JASON_PM_LAB" = 1\n'
        'test -n "$JASON_PM_LAB_STATE"\n'
        'test "$#" -eq 1\n'
        'REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"\n'
        'DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"\n'
        'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT\n'
        'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION="$1"\n'
        + action
        + 'ln -sfn "/opt/jason/releases/$1" /opt/jason/current\n'
        + failure
        + 'echo "HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=$1"\n'
        + 'echo "MANAGED_ENGINEERING_SOURCE=PASS"\n'
        + 'echo "MANAGED_DOCUMENTATION_SOURCE=PASS"\n'
        + 'echo "DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT"\n'
        + 'echo "JASON_HOST_SERVICE_RECONCILIATION=PASS"\n'
        + 'echo "JASON_PRODUCTION_DRIFT_GUARD=PASS"\n'
        + 'echo "JASON_ROLLBACK_CONTAINER_RETENTION=PASS"\n'
    )


def create_commits(lab: Path) -> tuple[Path, str, str, str]:
    repo = lab / "managed-repo"
    repo.mkdir()
    run("git", "init", "-q", "-b", "main", str(repo))
    git(repo, "config", "user.name", "Jason Disposable Lab")
    git(repo, "config", "user.email", "lab@example.invalid")
    policy = {
        "schema_version": "1.0",
        "required_system_units": [BASE_UNIT],
        "allowed_system_units": [CAND_UNIT],
        "required_user_units": [],
        "allowed_user_units": [],
    }
    def commit(mode: str) -> str:
        write_json(repo / "config/production-desired-state.json", policy, 0o644)
        write(repo / "tools/reconcile_production_host_services.sh", host_script(mode), 0o755)
        git(repo, "add", "config/production-desired-state.json",
            "tools/reconcile_production_host_services.sh")
        git(repo, "commit", "-qm", "lab " + mode)
        return git(repo, "rev-parse", "HEAD")
    baseline = commit("baseline")
    success = commit("candidate")
    failed = commit("fail")
    git(repo, "update-ref", "refs/remotes/origin/main", failed)
    # Dirty, unmerged work intentionally left in place for the whole exercise.
    write(repo / "unmerged-engineering-change.txt", "DO NOT OVERWRITE ACTIVE WORK\n")
    return repo, baseline, success, failed


def configure_root_worker(module, lab: Path, repo: Path) -> None:
    spool = lab / "spool"
    module.SPOOL = spool
    module.REQUESTS = spool / "requests"
    module.RESULTS = spool / "results"
    module.CANDIDATE_SCRIPTS = spool / "candidate-scripts"
    module.REPO = repo
    module.CURRENT = Path("/opt/jason/current")
    module.ROOT_RECOVERY_POLICY = lab / "protected-root-policy.json"
    module._trusted_root_policy_helper = lambda: SimpleNamespace(ACTIVE=lab / "no-policy-migration")
    module._mcp_revision = docker_mcp_revision


def worker(lab: Path) -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("JASON_PM_LAB") != "1"
            or os.geteuid() != 0
            or not lab.name.startswith("jason-pm-root-lab-")
            or not lab.is_dir()):
        raise RuntimeError("root worker simulation refused outside disposable lab")
    repo = lab / "managed-repo"
    worker_module = module_from(
        GITHUB / "tools/release_host_reconcile_worker.py", "pm_lab_host_worker"
    )
    configure_root_worker(worker_module, lab, repo)
    worker_module.main()


def write_unit_files(lab: Path) -> None:
    program = GITHUB / "tools/ci/production_manager_root_boundary_lab.py"
    write(
        SYSTEMD / BASE_UNIT,
        "[Unit]\nDescription=Disposable PM root baseline\n"
        "[Service]\nType=oneshot\nExecStart=/usr/bin/true\nRemainAfterExit=yes\n",
    )
    write(
        lab / "candidate.service",
        "[Unit]\nDescription=Disposable PM root candidate\n"
        "[Service]\nType=oneshot\nExecStart=/usr/bin/true\nRemainAfterExit=yes\n",
    )
    write(
        SYSTEMD / HOST_UNIT,
        "[Unit]\nDescription=Disposable PM root release worker\n"
        "[Service]\nType=oneshot\nUser=root\nGroup=root\n"
        "Environment=GITHUB_ACTIONS=true\nEnvironment=JASON_PM_LAB=1\n"
        "Environment=JASON_PM_LAB_STATE=" + str(lab) + "\n"
        "Environment=GITHUB_WORKSPACE=" + str(GITHUB) + "\n"
        "ExecStart=/usr/bin/python3 " + str(program) + " worker " + str(lab) + "\n"
        "TimeoutStartSec=45\n",
    )
    write(
        SYSTEMD / HOST_PATH,
        "[Unit]\nDescription=Disposable PM root request monitor\n"
        "[Path]\nDirectoryNotEmpty=" + str(lab / "spool/requests") + "\n"
        "Unit=" + HOST_UNIT + "\n[Install]\nWantedBy=multi-user.target\n",
    )


def submit_host(lab: Path, revision: str, al: pwd.struct_passwd,
                *, valid_owner: bool = True) -> dict:
    request_id = "release-" + revision[:12] + "-" + uuid4().hex[:12]
    request = lab / "spool/requests" / (request_id + ".json")
    payload = {
        "request_id": request_id, "source_revision": revision,
        "requested_by": "jason-release-manager", "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(
        request, payload, 0o600,
        al.pw_uid if valid_owner else 0,
        al.pw_gid if valid_owner else 0,
    )
    result = lab / "spool/results" / (request_id + ".json")
    deadline = time.monotonic() + 38
    while time.monotonic() < deadline:
        if result.is_file():
            item = json.loads(result.read_text())
            assert item["request_id"] == request_id
            assert item["source_revision"] == revision or not item["success"]
            assert not request.exists(), "request not retired by actual root worker"
            time.sleep(1.1)
            return item
        time.sleep(0.2)
    raise TimeoutError("root systemd.path request never produced a bounded result")


def root_health(manifest: dict, revision: str) -> dict:
    if (Path("/opt/jason/current").resolve().name != revision
            or docker_mcp_revision() != revision
            or not status(BASE_UNIT)):
        raise ValueError("independent lab host and MCP baseline not restored")
    return dict(manifest)


def transition(lab: Path, action: str, revision: str, al: pwd.struct_passwd,
               *, reason: str = "") -> dict:
    module = module_from(
        GITHUB / "tools/release_control_transition_worker.py", "pm_lab_control"
    )
    base = lab / "control"
    module.ROOT = base
    module.REQUESTS = base / "protected-transitions/requests"
    module.RESULTS = base / "protected-transitions/results"
    module.CONTROL = base / "production-control-state.json"
    module.DRIFT = base / "production-drift.json"
    module.LOCK = base / "protected-transitions/root-control.lock"
    old_state = json.loads(module.CONTROL.read_text())
    manifest = old_state["last_known_good"]["manifest"]
    module.verify_health = lambda sha: root_health(manifest, sha)
    reqid = uuid4().hex
    path = module.REQUESTS / (reqid + ".json")
    payload = {"request_id": reqid, "action": action,
               "revision": revision, "reason": reason}
    if action == "set_last_known_good":
        payload["release_id"] = "release-" + revision[:16]
    write_json(path, payload, 0o600, al.pw_uid, al.pw_gid)
    module.process()
    response = json.loads((module.RESULTS / (reqid + ".json")).read_text())
    breaker = json.loads(module.CONTROL.read_text())["circuit_breaker"]["state"]
    return {"response": response, "breaker": breaker}


def run_acceptance() -> None:
    assert_disposable()
    if any((SYSTEMD / unit).exists() for unit in UNITS):
        raise RuntimeError("disposable unit name collision")
    if Path("/opt/jason").exists():
        raise RuntimeError("existing /opt/jason directory detected")
    if run("docker", "inspect", LAB_MCP, check=False).returncode == 0:
        raise RuntimeError("disposable Docker container name collision")
    if run("id", "al", check=False).returncode == 0:
        raise RuntimeError("disposable runner unexpectedly has production user 'al'")
    run("groupadd", "--system", "jason")
    run("useradd", "--system", "--no-create-home", "--gid", "jason", "al")
    al = pwd.getpwnam("al")
    with tempfile.TemporaryDirectory(prefix="jason-pm-root-lab-") as dirname:
        lab = Path(dirname)
        try:
            repo, baseline, candidate, failed = create_commits(lab)
            dirty = repo / "unmerged-engineering-change.txt"
            preserved_hash = hashlib.sha256(dirty.read_bytes()).hexdigest()
            (lab / "spool/requests").mkdir(parents=True)
            (lab / "spool/results").mkdir(parents=True)
            policy = json.loads((repo / "config/production-desired-state.json").read_text())
            write_json(lab / "protected-root-policy.json", policy)
            # No operational filesystem should exist before creating dummy releases.
            Path("/opt/jason/releases").mkdir(parents=True)
            for sha in (baseline, candidate, failed):
                (Path("/opt/jason/releases") / sha).mkdir(mode=0o755)
            Path("/opt/jason/current").symlink_to(Path("/opt/jason/releases") / baseline)
            write_unit_files(lab)
            run("systemctl", "daemon-reload")
            run("systemctl", "start", BASE_UNIT, HOST_PATH)
            assert status(BASE_UNIT)
            create_mcp(candidate)
            ok = submit_host(lab, candidate, al)
            assert ok["success"] is True, ok
            assert "JASON_HOST_SERVICE_RECONCILIATION=PASS" in ok["detail"], ok
            assert status(CAND_UNIT)
            assert Path("/opt/jason/current").resolve().name == candidate
            print("ROOT_HOST_REQUEST_SYSTEMD_SUCCESS=PASS", flush=True)

            # Return from a successful staged test to the protected dummy baseline.
            create_mcp(baseline)
            rollback = submit_host(lab, baseline, al)
            assert rollback["success"] is True, rollback
            assert Path("/opt/jason/current").resolve().name == baseline
            assert not (SYSTEMD / CAND_UNIT).exists()
            print("ROOT_HOST_BASELINE_RECONCILE=PASS", flush=True)

            # Ownership must be checked before any change to the real dummy host.
            create_mcp(candidate)
            wrong = submit_host(lab, candidate, al, valid_owner=False)
            assert wrong["success"] is False, wrong
            assert "request owner" in wrong["detail"], wrong
            assert Path("/opt/jason/current").resolve().name == baseline
            print("ROOT_HOST_OWNER_GATE_FAIL_CLOSED=PASS", flush=True)

            # The candidate mutates test-only systemd and host SHA, then exits 42.
            create_mcp(failed)
            bad = submit_host(lab, failed, al)
            assert bad["success"] is False, bad
            assert "candidate host reconciliation script failed" in bad["detail"], bad
            assert status(CAND_UNIT)
            assert Path("/opt/jason/current").resolve().name == failed
            print("ROOT_HOST_PARTIAL_FAILURE_CAPTURED=PASS", flush=True)

            baseline_manifest = {
                "complete": True, "revision": baseline,
                "runtime_revision": baseline, "runtime_image_id": "sha256:" + ("c" * 64),
                "mcp_revision": baseline, "mcp_image_id": "sha256:" + ("d" * 64),
                "host_revision": baseline,
                "host_release": "/opt/jason/releases/" + baseline,
                "release_manager_source_revision": baseline,
                "desired_state_policy_digest": "sha256:" + ("e" * 64),
                "scheduled_control_units": [BASE_UNIT],
            }
            control = lab / "control"
            (control / "protected-transitions/requests").mkdir(parents=True)
            (control / "protected-transitions/results").mkdir(parents=True)
            state = {
                "schema_version": "1.0",
                "last_known_good": {"release_id": "lab-baseline", "manifest": baseline_manifest},
                "circuit_breaker": {"state": "closed"},
            }
            write_json(control / "production-control-state.json", state)
            write_json(control / "production-drift.json", {
                "schema_version": "1.0", "status": "pass", "problems": [],
                "observed_at": datetime.now(timezone.utc).isoformat(),
            })
            opened = transition(lab, "open", failed, al, reason="injected_root_host_failure")
            assert opened["response"]["success"] is True and opened["breaker"] == "open", opened
            # A healthy drift report alone must not reclose an un-restored host.
            denied = transition(lab, "revalidate", baseline, al)
            assert denied["response"]["success"] is False, denied
            assert denied["breaker"] == "open", denied
            # A forged approval-free change to last known good must also fail.
            unauthorized = transition(lab, "set_last_known_good", failed, al)
            assert unauthorized["response"]["success"] is False, unauthorized
            assert unauthorized["breaker"] == "open", unauthorized
            print("ROOT_BREAKER_RECOVERY_DENIAL=PASS", flush=True)

            # Simulate Release Manager's exact dependency-order rollback:
            # restore dummy MCP, then request exact LKG host revision.
            create_mcp(baseline)
            restored = submit_host(lab, baseline, al)
            assert restored["success"] is True, restored
            assert not (SYSTEMD / CAND_UNIT).exists()
            assert Path("/opt/jason/current").resolve().name == baseline
            recovered = transition(lab, "revalidate", baseline, al)
            assert recovered["response"]["success"] is True and recovered["breaker"] == "closed", recovered
            assert status(BASE_UNIT)
            assert hashlib.sha256(dirty.read_bytes()).hexdigest() == preserved_hash
            assert git(repo, "status", "--porcelain").find("unmerged-engineering-change.txt") >= 0
            print("ROOT_BREAKER_VERIFIED_RECOVERY=PASS", flush=True)
            print("DIRTY_PARALLEL_WORK_PRESERVED=PASS", flush=True)

            receipt = {
                "schema_version": "1.0",
                "environment": "ephemeral GitHub-hosted Ubuntu root systemd + Docker",
                "isolation": "test-only systemd names, fake isolated Git and root records, no client credentials",
                "production_changes": False,
                "actual_root_modules": [
                    "tools/release_host_reconcile_worker.py",
                    "tools/release_control_transition_worker.py",
                ],
                "baseline_sha": baseline, "candidate_sha": candidate,
                "injected_failure_sha": failed,
                "results": {
                    "root_systemd_path_one_request_success": "PASS",
                    "root_exact_baseline_restore": "PASS",
                    "root_request_owner_denial": "PASS",
                    "partial_host_change_failure_receipt": "PASS",
                    "root_circuit_open": "PASS",
                    "premature_revalidate_denied": "PASS",
                    "unauthorized_lkg_change_denied": "PASS",
                    "verified_lkg_restore_and_breaker_close": "PASS",
                    "unmerged_worktree_bytes_preserved": "PASS",
                },
                "limitations": [
                    "Uses lab-owned source/policy/host reconciliation script, not actual production reconciliation deployment shell.",
                    "Root worker dependency and health reads are redirected to test-only paths and Docker MCP.",
                    "Does not call the complete release_manager_host_runner.deploy_production transaction.",
                    "Successful isolated host and root control worker tests do not authorize production deployment.",
                ],
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            output = Path(os.environ["EVIDENCE_ROOT_OUTPUT"])
            write_json(output, receipt, 0o600)
            print("ROOT_WORKER_INTEGRATION=PASS_WITH_LIMITATIONS", flush=True)
        finally:
            run("systemctl", "stop", HOST_PATH, HOST_UNIT, CAND_UNIT, BASE_UNIT, check=False)
            for unit in UNITS:
                (SYSTEMD / unit).unlink(missing_ok=True)
            run("systemctl", "daemon-reload", check=False)
            run("docker", "rm", "-f", LAB_MCP, check=False)
            # The only created /opt/jason subtree is disposable lab fake releases.
            if Path("/opt/jason/releases").exists():
                shutil.rmtree("/opt/jason")
    run("userdel", "al", check=False)
    run("groupdel", "jason", check=False)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "worker":
        worker(Path(sys.argv[2]))
    elif len(sys.argv) == 1:
        run_acceptance()
    else:
        raise SystemExit("usage: production_manager_root_boundary_lab.py [worker LAB_ROOT]")
