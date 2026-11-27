"""Isolated regression tests for the post-power-loss recovery controls."""
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

boot = load("boot_postboot_recovery", ROOT / "tools/jason_boot_recovery.py")
wal = load("runbook_wal_prepare", ROOT / "tools/runbook_wal_prepare.py")


@pytest.fixture
def topology(tmp_path):
    mount = tmp_path / "role_id"
    mount.write_text("synthetic")
    transaction = tmp_path / "production.lock"
    transaction.touch()
    owner = tmp_path / "worker.lock"
    owner.touch()
    runtime = {"Config": {"Env": ["JASON_TICKET_WORKER_HOSTING=external"]}}
    worker = {
        "Id": "a" * 64, "Name": "/jason-pmv4-ticket-core", "Path": "python",
        "Args": ["-m", "jason_runtime.ticket_worker_service"],
        "Config": {"Env": ["JASON_TICKET_WORKER_HOSTING=external"],
                   "Healthcheck": {"Test": ["CMD", "synthetic"]}},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
        "State": {"Status": "exited", "ExitCode": 127,
                  "Error": "failed to fulfil mount request: " + str(mount)
                           + ": no such file or directory"},
        "Mounts": [{"Source": str(mount)}],
    }
    return mount, transaction, owner, runtime, worker


def invoke(topology, *, lock_rc=0, ready=True):
    mount, transaction, owner, runtime, worker = topology
    with (
        patch.object(boot, "STAGED_FILES", (mount,)),
        patch.object(boot, "inspect_container", side_effect=lambda n: runtime if n == boot.RUNTIME_CONTAINER else worker),
        patch.object(boot, "staged_credentials_ready", return_value=ready),
        patch.object(boot, "staged_credentials_current", return_value=ready),
        patch.object(boot, "wait_container_health") as health,
        patch.object(boot, "run", side_effect=lambda args, quiet=False:
                     SimpleNamespace(returncode=lock_rc if args[0] == "runuser" else 0)) as run,
    ):
        boot.recover_ticket_core(transaction_lock=transaction, owner_lock=owner)
        return [call.args[0] for call in run.call_args_list], health.call_args_list


def test_exact_credential_mount_failure_recovers_existing_id(topology):
    calls, health = invoke(topology)
    assert calls[-1] == ["docker", "start", "a" * 64]
    assert len(health) == 1
    assert not any(call[:2] in (["docker", "rm"], ["docker", "run"]) for call in calls)


def test_running_worker_never_restarted(topology):
    topology[-1]["State"] = {"Status": "running"}
    calls, health = invoke(topology)
    assert calls == [] and len(health) == 1


def test_embedded_runtime_skips_external_worker(topology):
    topology[-2]["Config"]["Env"] = ["JASON_TICKET_WORKER_HOSTING=embedded"]
    assert invoke(topology) == ([], [])


@pytest.mark.parametrize("condition", ["intentional_stop", "wrong_mount", "missing_mount", "lock_held", "not_ready", "no_healthcheck"])
def test_unapproved_or_unsafe_recovery_fails_closed(topology, condition):
    if condition == "intentional_stop":
        topology[-1]["State"] = {"Status": "exited", "ExitCode": 0, "Error": ""}
    elif condition == "wrong_mount":
        topology[-1]["State"]["Error"] = "failed to fulfil mount request: /wrong: no such file or directory"
    elif condition == "missing_mount":
        topology[0].unlink()
    elif condition == "no_healthcheck":
        topology[-1]["Config"]["Healthcheck"] = {"Test": ["NONE"]}
    with pytest.raises(boot.RecoveryError):
        invoke(topology, lock_rc=1 if condition == "lock_held" else 0,
               ready=condition != "not_ready")


def test_active_production_transaction_defers(topology):
    with topology[1].open("rb") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert invoke(topology) == ([], [])


def make_wal_db(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE proof(value)")
    db.commit()
    db.close()
    path.chmod(0o600)


def test_readonly_preparation_preserves_db_and_live_wal(tmp_path):
    db = tmp_path / "registry.sqlite3"
    make_wal_db(db)
    baseline = hashlib.sha256(db.read_bytes()).hexdigest()
    assert not Path(str(db) + "-wal").exists()
    old = os.umask(0o077)
    try:
        wal.prepare(db)
    finally:
        os.umask(old)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == baseline
    assert Path(str(db) + "-wal").exists()
    assert Path(str(db) + "-shm").exists()
    anchor = sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True)
    try:
        assert anchor.execute("SELECT count(*) FROM proof").fetchone() == (0,)
        subprocess.run([sys.executable, "-c",
            "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('INSERT INTO proof VALUES (1)'); c.commit(); c.close()", str(db)],
            check=True)
        assert Path(str(db) + "-wal").exists()
        assert Path(str(db) + "-shm").exists()
        assert anchor.execute("SELECT count(*) FROM proof").fetchone() == (1,)
    finally:
        anchor.close()


def test_untrusted_sidecar_rejected(tmp_path):
    db = tmp_path / "registry.sqlite3"
    make_wal_db(db)
    external = tmp_path / "external"
    external.write_bytes(b"unrelated")
    Path(str(db) + "-wal").symlink_to(external)
    with pytest.raises(RuntimeError, match="UNTRUSTED_FILE"):
        wal.prepare(db)
    assert external.read_bytes() == b"unrelated"
