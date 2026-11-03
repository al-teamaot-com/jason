#!/usr/bin/env python3
"""Real systemd ExecCondition/transaction-lock race test on disposable GitHub CI.

This deliberately cannot run on Jason production. It uses only a unique
test service and temporary lock on a credential-free GitHub-hosted runner.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", "/unavailable")).resolve()
UNIT = "jason-pmv3-worker-gate-lab.service"
UNIT_PATH = Path("/run/systemd/system") / UNIT


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(x) for x in args], text=True, capture_output=True, timeout=25
    )
    if check and result.returncode:
        raise RuntimeError(
            "isolated command failed: " + str(args[:3])
            + " rc=" + str(result.returncode)
            + " stderr=" + result.stderr[-300:]
        )
    return result


def assert_disposable() -> None:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("JASON_PM_LAB") != "1"
        or os.geteuid() != 0
        or not Path("/run/systemd/system").is_dir()
        or not (ROOT / "tools/pmv3_worker_release_gate.py").is_file()
        or not os.environ.get("EVIDENCE_PMV3_GATE_OUTPUT")
    ):
        raise RuntimeError("disposable GitHub Actions root/systemd host required")
    if any(Path(p).exists() for p in (
        "/opt/jason/current", "/var/lib/jason/openclaw",
        "/home/al/projects/jason",
    )):
        raise RuntimeError("refused: operational Jason host evidence detected")
    if UNIT_PATH.exists() or UNIT_PATH.is_symlink():
        raise RuntimeError("refused: test service name already exists")


def source_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def unit_state() -> tuple[str, str]:
    state = run("systemctl", "show", UNIT, "-p", "ActiveState", "--value").stdout.strip()
    result = run("systemctl", "show", UNIT, "-p", "Result", "--value").stdout.strip()
    return state, result


def acceptance() -> None:
    assert_disposable()
    with tempfile.TemporaryDirectory(prefix="jason-pmv3-systemd-lab-") as raw:
        lab = Path(raw)
        if not re.fullmatch(r"[/A-Za-z0-9_.-]+", str(lab)):
            raise RuntimeError("invalid disposable lab pathname")
        lock = lab / "production-transaction.lock"
        lock.touch(mode=0o600)
        lock.chmod(0o600)
        starts = lab / "worker-starts.txt"
        gate = lab / "gate.py"
        marker = lab / "marker.py"
        gate.write_text(
            "import importlib.util,sys\n"
            "from pathlib import Path\n"
            "p=Path(" + repr(str(ROOT / "tools/pmv3_worker_release_gate.py")) + ")\n"
            "spec=importlib.util.spec_from_file_location('pmv3_exact_gate',p)\n"
            "m=importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "sys.exit(0 if m.admission_allowed(Path(sys.argv[1])) else 1)\n",
            encoding="utf-8",
        )
        marker.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "p=Path(sys.argv[1])\n"
            "with p.open('a',encoding='utf-8') as f:f.write('start\\n')\n",
            encoding="utf-8",
        )
        unit = (
            "[Unit]\nDescription=Disposable PMV3 worker admission race lab\n"
            "[Service]\nType=oneshot\n"
            "ExecCondition=/usr/bin/python3 " + str(gate) + " " + str(lock) + "\n"
            "ExecStart=/usr/bin/python3 " + str(marker) + " " + str(starts) + "\n"
            "TimeoutStartSec=12\n"
        )
        # All units exist only on a disposable CI runner and are removed below.
        UNIT_PATH.write_text(unit, encoding="utf-8")
        try:
            run("systemctl", "daemon-reload")

            def count() -> int:
                return starts.read_text().count("start\n") if starts.exists() else 0

            run("systemctl", "start", UNIT)
            assert count() == 1, "idle worker gate did not permit start"
            assert unit_state()[0] == "inactive"

            # The actual kernel mutex remains held across systemd's separate
            # ExecCondition process; systemd must SKIP without failing the unit.
            with lock.open("rb") as owner:
                fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    for _ in range(2):
                        run("systemctl", "start", UNIT, check=False)
                        assert count() == 1, "worker started during release lock"
                        state, _ = unit_state()
                        assert state != "failed", (state, unit_state())
                    # Self-heal uses the exact same lock and must not dispatch.
                    sys.path.insert(0, str(ROOT / "tools"))
                    watchdog = source_module(
                        ROOT / "tools/jason_self_heal_watchdog.py",
                        "pmv3_lab_selfheal",
                    )
                    watchdog.PRODUCTION_TRANSACTION_LOCK = lock
                    watchdog.run = lambda *a, **k: (_ for _ in ()).throw(
                        AssertionError("unexpected systemctl or Docker mutation")
                    )
                    assert watchdog.request_engineering_worker().startswith("deferred_")
                    assert watchdog.bounded_recovery(["container_down:jason-runtime"]) == []
                finally:
                    fcntl.flock(owner.fileno(), fcntl.LOCK_UN)

            # Untrusted lock material must fail closed, not hang on an open FIFO.
            lock.chmod(0o666)
            run("systemctl", "start", UNIT, check=False)
            assert count() == 1
            lock.unlink()
            os.mkfifo(lock, mode=0o600)
            run("systemctl", "start", UNIT, check=False)
            assert count() == 1
            lock.unlink()
            target = lab / "target.lock"
            target.touch(mode=0o600)
            lock.symlink_to(target)
            run("systemctl", "start", UNIT, check=False)
            assert count() == 1
            lock.unlink()
            lock.touch(mode=0o600)
            lock.chmod(0o600)

            run("systemctl", "start", UNIT)
            assert count() == 2, "worker did not resume after release"
            state, _ = unit_state()
            assert state == "inactive", (state, unit_state())

            receipt = {
                "schema_version": "1.0",
                "environment": "disposable GitHub-hosted Ubuntu real systemd",
                "source_sha": os.environ.get("GITHUB_SHA", ""),
                "production_changes": False,
                "scenarios": {
                    "systemd_worker_starts_with_idle_mutex": "PASS",
                    "systemd_exec_condition_denies_held_mutex_without_failed_unit": "PASS",
                    "selfheal_defers_worker_and_docker_under_mutex": "PASS",
                    "world_writable_fifo_and_symlink_lock_denied": "PASS",
                    "systemd_worker_resumes_after_lock_release": "PASS",
                },
                "limitations": [
                    "Test-only root systemd unit and lock, not production user unit.",
                    "No production promotion, deployment or rollback authorization.",
                ],
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
            out = Path(os.environ["EVIDENCE_PMV3_GATE_OUTPUT"])
            out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print("PMV3_DISPOSABLE_WORKER_ADMISSION=PASS", flush=True)
        finally:
            run("systemctl", "stop", UNIT, check=False)
            UNIT_PATH.unlink(missing_ok=True)
            run("systemctl", "daemon-reload", check=False)


if __name__ == "__main__":
    acceptance()
