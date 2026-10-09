#!/usr/bin/env python3
"""Continuously enforce Jason production desired-state drift policy."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import production_drift_guard as drift_guard

DEFAULT_CONFIG = Path("/opt/jason/current/config/production-desired-state.json")
DEFAULT_EVIDENCE = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
DEFAULT_CONTROL_STATE = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DEFAULT_WATCHDOG_STATE = Path("/var/lib/jason/openclaw/release-manager/production-drift-watchdog.json")
DEFAULT_TRANSACTION_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload: dict, *, inherit_parent_owner: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        if inherit_parent_owner:
            parent = path.parent.stat()
            os.chown(temp, parent.st_uid, parent.st_gid)
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return dict(default or {})
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def production_transaction_active(lock_path: Path = DEFAULT_TRANSACTION_LOCK) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


def apply_result(result: dict, *, control_state: Path, evidence: Path, watchdog_state: Path) -> int:
    atomic_json(evidence, result)
    status = str(result.get("status") or "unknown")
    problems = list(result.get("problems") or [])
    watchdog = {
        "schema_version": "1.0",
        "status": status,
        "problem_count": len(problems),
        "evidence_path": str(evidence),
        "observed_at": str(result.get("observed_at") or now()),
        "updated_at": now(),
    }
    if status == "pass":
        # Never auto-close a circuit breaker. Production Manager must perform
        # authoritative revalidation against the last-known-good manifest.
        watchdog["circuit_breaker_action"] = "none"
        atomic_json(watchdog_state, watchdog)
        return 0

    control = load_json(
        control_state,
        {
            "schema_version": "1.0",
            "last_known_good": None,
            "circuit_breaker": {"state": "closed"},
        },
    )
    control["schema_version"] = "1.0"
    control["circuit_breaker"] = {
        "state": "open",
        "reason": "continuous_production_drift_detected",
        "source": "production_drift_watchdog",
        "problem_count": len(problems),
        "problem_kinds": sorted({str(item.get("kind") or "unknown") for item in problems if isinstance(item, dict)}),
        "evidence_path": str(evidence),
        "opened_at": now(),
        "updated_at": now(),
    }
    control["updated_at"] = now()
    atomic_json(control_state, control, inherit_parent_owner=True)
    watchdog["circuit_breaker_action"] = "opened"
    atomic_json(watchdog_state, watchdog)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--control-state", type=Path, default=DEFAULT_CONTROL_STATE)
    parser.add_argument("--watchdog-state", type=Path, default=DEFAULT_WATCHDOG_STATE)
    args = parser.parse_args()

    if production_transaction_active():
        atomic_json(
            args.watchdog_state,
            {
                "schema_version": "1.0",
                "status": "deferred",
                "reason": "production_transaction_active",
                "circuit_breaker_action": "none",
                "updated_at": now(),
            },
        )
        return 0

    config = load_json(args.config)
    result = drift_guard.evaluate(config)
    return apply_result(
        result,
        control_state=args.control_state,
        evidence=args.evidence,
        watchdog_state=args.watchdog_state,
    )


if __name__ == "__main__":
    raise SystemExit(main())
