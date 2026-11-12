#!/usr/bin/env python3
"""PMv4 independent runbook lifecycle acceptance, synthetic data only.

Local mode uses isolated child processes, never production JSON registry.
Docker mode is designed for isolated GitHub CI runners, NOT Jason production:
undeclared test containers can trigger its protected drift watchdog.
No OAuth/Owner authority is minted here; the production MCP boundary remains
the only authorized control plane for real registry changes.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

PHASES = ("stage", "activate", "upgrade", "deny_mutation", "retire", "verify")


def sample(version: str = "1.0.0") -> dict:
    return {
        "schema_version": 1,
        "playbook": {"id": "pmv4_acceptance_repair", "name": "PMv4 Synthetic",
                     "version": version, "lifecycle": "pilot",
                     "target_type": "endpoint"},
        "trigger": {"provider": "synthetic", "match": {"title_contains": ["Synthetic"]}},
        "scope": {"direct_provider_access": False},
        "expected_state": {"service": "running"},
        "state_model": {"entry_step": "check"},
        "steps": [
            {"id": "check", "type": "diagnostic",
             "capability": "endpoint.service.read",
             "arguments": {"service": "Synthetic"},
             "next": "complete"},
            {"id": "complete", "type": "complete"},
        ],
        "verification": {"authoritative_source": "endpoint.service.read",
                         "success_condition": "service_running=true"},
        "completion": {"terminal_disposition": "Complete"},
        "autonomy": {"activation": "disabled",
                     "allowed_capabilities": ["endpoint.service.read"]},
    }


def phase_action(phase: str, db: Path) -> dict:
    from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
    db.parent.mkdir(parents=True, exist_ok=True)
    store = SQLitePlaybookRegistry(db)
    try:
        pid = "pmv4_acceptance_repair"
        if phase == "stage":
            stored = store.stage(sample(), actor="synthetic-technician")
            assert stored.state == "draft" and store.generation() == 1
        elif phase == "activate":
            staged = store.get(pid, "1.0.0")
            active = store.activate(pid, "1.0.0", actor="synthetic-owner",
                                    expected_fingerprint=staged.document.fingerprint)
            assert active.state == "active" and store.generation() == 2
        elif phase == "upgrade":
            draft = store.stage(sample("1.1.0"), actor="synthetic-technician")
            store.activate(pid, "1.1.0", actor="synthetic-owner",
                           expected_fingerprint=draft.document.fingerprint)
            assert store.get(pid, "1.0.0").state == "retired"
            assert store.active(pid).document.version == "1.1.0"
            assert store.generation() == 4
        elif phase == "deny_mutation":
            changed = sample("1.1.0")
            changed["expected_state"]["service"] = "wrong"
            try:
                store.stage(changed, actor="synthetic-technician")
            except ValueError as exc:
                assert "PLAYBOOK_VERSION_IMMUTABLE" in str(exc)
            else:
                raise AssertionError("immutable version overwritten")
            assert store.generation() == 4
            assert store.active(pid).document.version == "1.1.0"
            assert len(store.lifecycle_events()) == 4
        elif phase == "retire":
            assert store.retire(pid, actor="synthetic-owner")
            assert store.active(pid) is None and store.generation() == 5
        elif phase == "verify":
            assert store.generation() == 5 and store.active(pid) is None
            assert [event["event_type"] for event in store.lifecycle_events()] == [
                "staged", "activated", "staged", "activated", "retired"]
            assert [e["generation_after"] for e in store.lifecycle_events()] == list(range(1, 6))
            assert [p.document.version for p in store.list_all()] == ["1.0.0", "1.1.0"]
            with sqlite3.connect(str(db)) as con:
                assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        else:
            raise ValueError("unexpected phase")
        return {"phase": phase, "generation": store.generation(), "status": "passed"}
    finally:
        store.close()


def command_for_phase(phase: str, root: Path, engine: str) -> list[str]:
    script = Path(__file__).resolve()
    if engine == "local":
        return [sys.executable, str(script), "--child", phase, "--db",
                str(root / "json-playbooks.sqlite3")]
    if engine != "docker":
        raise ValueError("invalid engine")
    if os.geteuid() == 0:
        raise ValueError("docker acceptance must run as a non-root user")
    repo = script.parents[1]
    # Fixed offline container profile; the ONLY writable mount is a new
    # private temporary synthetic registry. No network, host config,
    # production ledger, user credential, or AI service is passed through.
    return [
        "docker", "run", "--rm",
        "--name", f"pmv4-runbook-acceptance-{os.getpid()}-{phase}",
        "--network", "none", "--read-only",
        "--user", f"{os.geteuid()}:{os.getegid()}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "256m", "--cpus", "0.5",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=8m",
        "--mount", f"type=bind,src={root},dst=/lab",
        "--mount", f"type=bind,src={repo / 'implementation'},dst=/src,readonly",
        "--mount", f"type=bind,src={script},dst=/opt/accept.py,readonly",
        "--env", "PYTHONPATH=/src",
        "python:3.12-slim", "python", "/opt/accept.py",
        "--child", phase, "--db", "/lab/json-playbooks.sqlite3",
    ]


def acceptance(engine: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pmv4-runbook-isolation-") as tmp:
        root = Path(tmp)
        results = []
        for phase in PHASES:
            cmd = command_for_phase(phase, root, engine)
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "implementation")}
            result = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=90)
            if result.returncode:
                raise RuntimeError("RUNBOOK_ACCEPTANCE_" + phase.upper() + "_FAILED: " +
                                   result.stderr[-1000:])
            decoded = json.loads(result.stdout.strip())
            if decoded != {"phase": phase,
                           "generation": {"stage": 1, "activate": 2,
                                          "upgrade": 4, "deny_mutation": 4,
                                          "retire": 5, "verify": 5}[phase],
                           "status": "passed"}:
                raise RuntimeError("RUNBOOK_ACCEPTANCE_READBACK_MISMATCH")
            results.append(decoded)
        db = root / "json-playbooks.sqlite3"
        return {
            "status": "accepted", "evidence_type": "synthetic_only",
            "engine": engine, "phases": [r["phase"] for r in results],
            "final_generation": 5,
            "sqlite_sha256": sha256(db.read_bytes()).hexdigest(),
            "distinct_lifecycle_processes": len(results),
            "provider_access": False, "production_mounts": False,
            "owner_authorization_issued": False, "production_deployed": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=PHASES)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--acceptance", choices=("local", "docker"))
    args = parser.parse_args()
    if args.child:
        if args.db is None:
            parser.error("--child requires --db")
        print(json.dumps(phase_action(args.child, args.db), sort_keys=True))
    elif args.acceptance:
        print(json.dumps(acceptance(args.acceptance), sort_keys=True))
    else:
        parser.error("specify --acceptance local|docker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
