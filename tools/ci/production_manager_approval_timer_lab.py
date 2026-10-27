#!/usr/bin/env python3
"""Real isolated systemd timer versus native Release Manager transaction lock.

Only disposable GitHub-hosted Ubuntu. No production provider, endpoint, secret,
host worktree, network action or mutable release state is used.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


GITHUB = Path(os.environ.get("GITHUB_WORKSPACE", "/invalid"))
UNIT = "jason-pm-lab-approval-only.service"
TIMER = "jason-pm-lab-approval-only.timer"
UNITDIR = Path("/etc/systemd/system")


def run(*args, check=True):
    return subprocess.run([str(x) for x in args], text=True, capture_output=True,
                          check=check)


def verify_runner():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("JASON_PM_LAB") != "1" or
            os.geteuid() != 0 or
            not Path("/run/systemd/system").is_dir() or
            not (GITHUB / "tools/release_manager_host_runner.py").is_file()):
        raise RuntimeError("requires a disposable root/systemd GitHub Actions runner")
    for forbidden in ("/opt/jason/current", "/var/lib/jason/openclaw",
                      "/home/al/projects/jason"):
        if Path(forbidden).exists():
            raise RuntimeError("operational Jason path found: refused")
    for unit in (UNIT, TIMER):
        if (UNITDIR / unit).exists():
            raise RuntimeError("refused collision with an installed systemd unit")


def write_json(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def fake_worker(lab: Path):
    # This launches the exact reviewed production module. Only its external
    # read functions are redirected to harmless in-memory lab-only fixtures.
    sys.path.insert(0, str(GITHUB / "tools"))
    import release_manager_host_runner as runner
    runner.DEFAULT_STATE = lab
    mode = (lab / "mode").read_text().strip()
    read_calls = []
    sha = "a" * 40

    def root_snapshot(root, name):
        read_calls.append(name)
        return (
            {"schema_version": "1.0",
             "circuit_breaker": {"state": "closed"},
             "last_known_good": {"manifest":
                 {"revision": "b" * 40 if mode == "mismatch" else sha}}}
            if name == "production-control-state.json"
            else {"schema_version": "1.0", "status": "pass", "problems": []}
        )
    runner._read_protected_snapshot = root_snapshot
    runner.live_runtime = lambda: {"revision": sha}
    runner.live_production_alignment = lambda revision: {}
    runner.MOBILE_APPROVAL_POLICY = lab / "absent-owner-policy.json"

    output = io.StringIO()
    error = None
    try:
        with redirect_stdout(output):
            published = runner.approval_only_while_promotion_held(GITHUB, lab)
    except Exception as exc:
        error = type(exc).__name__
        published = False
    write_json(lab / "result.json", {
        "mode": mode, "published": published, "root_reads": len(read_calls),
        "output": output.getvalue().strip(), "error_type": error,
    })
    if error is not None:
        raise RuntimeError("guarded approval-only execution failed")


def systemd_result():
    raw = run("systemctl", "show", UNIT, "-p", "Result",
              "-p", "ExecMainStatus", "--no-pager").stdout.strip()
    return dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)


def await_result(lab: Path):
    path = lab / "result.json"
    until = time.monotonic() + 24
    while time.monotonic() < until:
        if path.is_file():
            return json.loads(path.read_text())
        time.sleep(0.15)
    raise TimeoutError("isolated systemd approval timer did not dispatch")


def main():
    verify_runner()
    with tempfile.TemporaryDirectory(prefix="jason-pm-approval-lab-") as raw:
        lab = Path(raw)
        try:
            (lab / "auto-promotion-incident-hold").touch()
            (lab / "mode").write_text("busy")
            unfinished = lab / "unmerged-engineering-change.txt"
            unfinished.write_text("UNMERGED WORK MUST BE PRESERVED\n")
            preserved = hashlib.sha256(unfinished.read_bytes()).hexdigest()
            source = GITHUB / "tools/ci/production_manager_approval_timer_lab.py"
            service = (
                "[Unit]\nDescription=Disposable Jason PM approval-only service\n"
                "ConditionPathExists=" + str(lab / "auto-promotion-incident-hold") +
                "\n[Service]\nType=oneshot\nUser=root\nGroup=root\n"
                "Environment=GITHUB_ACTIONS=true\nEnvironment=JASON_PM_LAB=1\n"
                "Environment=GITHUB_WORKSPACE=" + str(GITHUB) + "\n"
                "ExecStart=/usr/bin/python3 " + str(source) + " worker " + str(lab) + "\n"
            )
            timer = (
                "[Unit]\nDescription=Disposable Jason PM race timer\n"
                "[Timer]\nOnActiveSec=2s\nAccuracySec=1s\n"
                "Unit=" + UNIT + "\n"
            )
            (UNITDIR / UNIT).write_text(service)
            (UNITDIR / TIMER).write_text(timer)
            run("systemctl", "daemon-reload")

            # The real exclusive lock is held throughout the timer fire,
            # including the new runtime/old-LKG critical transition window.
            fd = os.open(lab / "production-transaction.lock",
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o660)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run("systemctl", "start", TIMER)
                first = await_result(lab)
                assert first["published"] is False and first["error_type"] is None, first
                assert "PRODUCTION_TRANSITION_IN_PROGRESS" in first["output"], first
                assert first["root_reads"] == 0, first
                assert systemd_result().get("Result") == "success"
                print("TIMER_DURING_RELEASE=PASS_DEFERRED_NO_FAILED_SYSTEMD", flush=True)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

            # Once the same lock is released, normal stable production checks
            # resume. No original approval/card may be emitted by the lab.
            (lab / "mode").write_text("stable")
            (lab / "result.json").unlink()
            run("systemctl", "start", UNIT)
            stable = await_result(lab)
            assert stable["error_type"] is None and stable["published"] is False, stable
            assert "OWNER_POLICY_UNAVAILABLE" in stable["output"], stable
            assert stable["root_reads"] == 2 and systemd_result()["Result"] == "success"
            print("POST_RELEASE_APPROVAL_ONLY=PASS_IDLE", flush=True)

            # A *persistent* version mismatch outside an active transaction
            # must still fail closed rather than be quietly ignored.
            (lab / "mode").write_text("mismatch")
            (lab / "result.json").unlink()
            failure = run("systemctl", "start", UNIT, check=False)
            assert failure.returncode != 0, failure
            mismatch = await_result(lab)
            assert mismatch["error_type"] == "ReleaseManagerError", mismatch
            assert systemd_result()["Result"] == "exit-code", systemd_result()
            print("PERSISTENT_LKG_MISMATCH=PASS_FAIL_CLOSED", flush=True)

            # Restore normal clean schedule state; never leave a failed unit
            # on the disposable test runner.
            (lab / "mode").write_text("stable")
            (lab / "result.json").unlink()
            run("systemctl", "start", UNIT)
            assert await_result(lab)["error_type"] is None
            assert systemd_result()["Result"] == "success"
            assert hashlib.sha256(unfinished.read_bytes()).hexdigest() == preserved
            print("DEV_WORKTREE_PRESERVATION=PASS", flush=True)

            receipt = {
                "schema_version": "1.0",
                "environment": "disposable GitHub-hosted Ubuntu systemd",
                "production_resources_touched": False,
                "actual_source": "tools/release_manager_host_runner.py",
                "scenarios": {
                    "timer_fired_with_active_native_mutex": "PASS",
                    "no_approval_or_provider_reads_in_midflight": "PASS",
                    "systemd_exit_zero_with_busy_mutex": "PASS",
                    "normal_idle_after_release": "PASS",
                    "persistent_lkg_mismatch_still_fails": "PASS",
                    "failed_unit_recovers_after_valid_baseline": "PASS",
                    "unmerged_file_unchanged": "PASS",
                },
                "limitations": [
                    "Protected snapshots and live runtime are synthetic; it verifies the real lock and systemd timer behavior.",
                    "No production promotion performed; future deployment still needs a fresh exact-SHA Owner approval.",
                ],
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            out = Path(os.environ["EVIDENCE_APPROVAL_OUTPUT"])
            out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            out.chmod(0o644)
            print("APPROVAL_TIMER_LAB=PASS_WITH_LIMITATIONS", flush=True)
        finally:
            run("systemctl", "stop", TIMER, UNIT, check=False)
            for name in (UNIT, TIMER):
                (UNITDIR / name).unlink(missing_ok=True)
            run("systemctl", "daemon-reload", check=False)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "worker":
        fake_worker(Path(sys.argv[2]))
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit("usage: lab.py [worker LAB_ROOT]")
