#!/usr/bin/env python3
"""Reproducible *offline* Ticket Core container ownership/continuity acceptance.

Creates only throwaway containers without network, providers, production mounts,
AI credentials or runtime restarts. The synthetic ledger is NEVER production.
Run from the versioned checkout on the Jason host with installed Docker.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS autonomy_ticket_worker_heartbeat (
 singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
 last_started_at TEXT, last_completed_at TEXT, state TEXT
);
CREATE TABLE IF NOT EXISTS autonomy_ticket_scan_cycle(
 scanned_at TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS synthetic_ticket_claims(
 ticket_id TEXT PRIMARY KEY, claimant TEXT NOT NULL, claim_generation INTEGER NOT NULL
);
"""
PREFIX = "jason-pmv4-ticket-core-acceptance-"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _heartbeat(db: Path, *, scan: int, claimant: str) -> None:
    with sqlite3.connect(str(db), timeout=3.0) as con:
        con.executescript(TEST_SCHEMA)
        now = _now()
        con.execute(
            "INSERT OR IGNORE INTO synthetic_ticket_claims VALUES(?,?,?)",
            ("synthetic-ticket-01", claimant, 1),
        )
        con.execute(
            "INSERT OR IGNORE INTO autonomy_ticket_scan_cycle VALUES(?)", (now,)
        )
        con.execute(
            "INSERT INTO autonomy_ticket_worker_heartbeat VALUES(1,?,?,?) "
            "ON CONFLICT(singleton_id) DO UPDATE SET "
            "last_started_at=excluded.last_started_at, "
            "last_completed_at=excluded.last_completed_at, state=excluded.state",
            (now, now, "completed"),
        )
    (db.parent / ("scan-" + str(scan))).write_text(now)


def _child(mode: str) -> int:
    from jason_runtime.ticket_worker_ownership import (
        TicketWorkerOwnershipError, exclusive_ticket_worker_owner
    )
    db = Path("/lab/synthetic-ticket-work.sqlite3")
    try:
        with exclusive_ticket_worker_owner(db):
            if mode == "contender":
                # A genuine conflict should stop before entering this block.
                return 18
            if mode == "recover":
                _heartbeat(db, scan=3, claimant="recovery")
                return 0
            if mode != "primary":
                return 19
            _heartbeat(db, scan=1, claimant="primary")
            deadline = time.monotonic() + 35
            while not Path("/lab/advance").exists():
                if time.monotonic() > deadline:
                    return 20
                time.sleep(0.1)
            _heartbeat(db, scan=2, claimant="primary")
            while not Path("/lab/stop").exists():
                if time.monotonic() > deadline:
                    return 21
                time.sleep(0.1)
            return 0
    except TicketWorkerOwnershipError as exc:
        return 11 if "ALREADY_OWNED" in str(exc) else 12


def _docker(*args: str, timeout: float = 25, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["/usr/bin/docker", *args],
        capture_output=True, text=True, check=False, timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError("CONTAINER_LAB_DOCKER_COMMAND_FAILED")
    return proc


def _wait(path: Path, seconds: float = 20) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not path.exists():
        raise RuntimeError("CONTAINER_LAB_SYNTHETIC_SCAN_MISSING")


def _check_container(name: str) -> None:
    raw = _docker("inspect", name).stdout
    obj = json.loads(raw)[0]
    host = obj["HostConfig"]
    config = obj["Config"]
    if not (
        host["NetworkMode"] == "none"
        and host["ReadonlyRootfs"] is True
        and host["Privileged"] is False
        and "ALL" in host["CapDrop"]
        and "no-new-privileges:true" in host["SecurityOpt"]
        and host["PortBindings"] in (None, {})
        and config["User"] == "1000:1000"
        and {item["Destination"] for item in obj["Mounts"]}
            == {"/lab", "/src", "/opt/lab-worker.py"}
        and isinstance(host.get("Tmpfs"), dict)
        and "/tmp" in host["Tmpfs"]
        and all(item.get("Type") == "bind" for item in obj["Mounts"])
        and all(item.get("RW") is False for item in obj["Mounts"]
                if item["Destination"] in ("/src", "/opt/lab-worker.py"))
        and all(item.get("RW") is True for item in obj["Mounts"]
                if item["Destination"] == "/lab")
    ):
        raise RuntimeError("CONTAINER_LAB_ISOLATION_READBACK_FAILED")
    forbidden = (
        "OPENAI_API_KEY=", "ANTHROPIC_API_KEY=", "AZURE_OPENAI_API_KEY=",
        "DATTO_API_KEY=", "AUTOTASK_API_KEY=", "AWS_SECRET_ACCESS_KEY=",
    )
    if any(entry.startswith(forbidden) for entry in config["Env"]):
        raise RuntimeError("CONTAINER_LAB_UNEXPECTED_PROVIDER_KEY")


def _acceptance() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    source = root / "implementation" / "runtime_service" / "src"
    if not (source / "jason_runtime" / "ticket_worker_ownership.py").is_file():
        raise RuntimeError("CONTAINER_LAB_SOURCE_UNAVAILABLE")
    image_info = json.loads(_docker("image", "inspect", "jason-runtime:production").stdout)[0]
    image = image_info["Id"]
    if not image.startswith("sha256:") or len(image) != 71:
        raise RuntimeError("CONTAINER_LAB_IMAGE_UNPINNED")
    source_bytes = (
        (source / "jason_runtime" / "ticket_worker_ownership.py").read_bytes()
        + (source / "jason_runtime" / "ticket_worker_service.py").read_bytes()
    )
    source_hash = sha256(source_bytes).hexdigest()
    revision = subprocess.run(
        ["/usr/bin/git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    name = PREFIX + str(os.getpid())
    with tempfile.TemporaryDirectory(prefix=PREFIX) as temp:
        folder = Path(temp)
        os.chmod(folder, 0o700)
        def args(container_name: str, mode: str, *, detached: bool = False) -> tuple[str, ...]:
            return (
                "run", "--rm", "--pull", "never",
                *(("-d",) if detached else ()),
                "--name", container_name, "--network", "none",
                "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--user", "1000:1000", "--pids-limit", "32",
                "--memory", "256m", "--cpus", "0.5",
                "--tmpfs", "/tmp:rw,nosuid,noexec,size=8m",
                "--mount", "type=bind,src=" + str(folder) + ",dst=/lab",
                "--mount", "type=bind,src=" + str(source) + ",dst=/src,readonly",
                "--mount", "type=bind,src=" + str(Path(__file__).resolve()) +
                    ",dst=/opt/lab-worker.py,readonly",
                "--env", "PYTHONPATH=/src", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--label", "com.aot.jason.component=pmv4-ticket-core-acceptance",
                image, "python3", "/opt/lab-worker.py", "--child-mode", mode,
            )
        try:
            _docker(*args(name, "primary", detached=True))
            _check_container(name)
            _wait(folder / "scan-1")
            challenger = _docker(
                *args(name + "-challenger", "contender"), check=False
            )
            if challenger.returncode != 11:
                raise RuntimeError("CONTAINER_LAB_DUPLICATE_DISPATCH_NOT_BLOCKED")
            (folder / "advance").write_text("two independent scans")
            _wait(folder / "scan-2")
            with sqlite3.connect(str(folder / "synthetic-ticket-work.sqlite3")) as con:
                cycles = con.execute(
                    "SELECT COUNT(*) FROM autonomy_ticket_scan_cycle"
                ).fetchone()[0]
                claims = con.execute(
                    "SELECT COUNT(*) FROM synthetic_ticket_claims"
                ).fetchone()[0]
            if cycles != 2 or claims != 1:
                raise RuntimeError("CONTAINER_LAB_TWO_CYCLE_LEDGER_MISMATCH")
            (folder / "stop").write_text("stop")
            deadline = time.monotonic() + 10
            while _docker("inspect", name, check=False).returncode == 0:
                if time.monotonic() > deadline:
                    raise RuntimeError("CONTAINER_LAB_PRIMARY_NOT_STOPPED")
                time.sleep(0.1)
            recovery = _docker(*args(name + "-recovered", "recover"), check=False)
            if recovery.returncode != 0:
                raise RuntimeError("CONTAINER_LAB_RECOVERY_DID_NOT_CLAIM_LOCK")
            with sqlite3.connect(str(folder / "synthetic-ticket-work.sqlite3")) as con:
                cycles = con.execute(
                    "SELECT COUNT(*) FROM autonomy_ticket_scan_cycle"
                ).fetchone()[0]
                claims = con.execute(
                    "SELECT COUNT(*) FROM synthetic_ticket_claims"
                ).fetchone()[0]
            if cycles != 3 or claims != 1:
                raise RuntimeError("CONTAINER_LAB_RECOVERY_LEDGER_MISMATCH")
            return {
                "status": "accepted", "evidence_type": "offline_synthetic_only",
                "base_runtime_image_source_sha": image_info["Config"]["Labels"].get(
                    "com.teamaot.jason.source_revision"
                ),
                "tested_ticket_source_revision": revision,
                "tested_ticket_code_sha256": source_hash,
                "image_sha256": image,
                "network": "none", "provider_credentials": False,
                "production_mounts": False, "live_ticket_mutations": False,
                "successful_synthetic_scans": cycles,
                "unique_synthetic_claims": claims,
                "competing_container_denied": True,
                "owner_reacquired_after_process_exit": True,
                "production_deployed": False,
            }
        finally:
            # Only our fixed throwaway name(s); no host process/services touched.
            for instance in (name, name + "-challenger", name + "-recovered"):
                _docker("rm", "-f", instance, check=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--child-mode", choices=("primary", "contender", "recover"))
    p.add_argument("--acceptance", action="store_true")
    args = p.parse_args()
    if args.child_mode:
        return _child(args.child_mode)
    if not args.acceptance:
        raise SystemExit("Use --acceptance for isolated container test.")
    print(json.dumps(_acceptance(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
