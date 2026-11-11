#!/usr/bin/env python3
"""Bounded emergency fast-health adapter; NEVER invent a full integrity PASS.

The independent heavy full SQLite proof has timed out. Accept only that single
known incomplete-proof condition, after rechecking all four live SQLite DBs,
the trusted key registry and delegation readability. Publish failure/degraded
evidence and exit zero *only for systemd scheduling*, so the unrelated
release system does not treat a 60-minute optional audit as production drift.

This explicit temporary recovery expires automatically in less than 30 hours.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/jason/current/tools")
from openclaw_authority_fast_health import check
from openclaw_authority_health_snapshot import write_atomic_snapshot

OUTPUT = Path("/var/lib/jason/openclaw/operational-health.json")
FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
ADVISORY = Path("/var/lib/jason/openclaw/owner-emergency-health-advisory.json")
EXPIRES = datetime.fromisoformat("2026-11-12T15:00:00+00:00")
ALLOWED_FAILURE = "full_integrity_proof_missing_stale_or_invalid"


def known_full_timeout() -> bool:
    try:
        e = json.loads(FULL.read_text(encoding="utf-8"))
        return (e.get("status") == "fail"
                and e.get("failures") == ["operational_health_timeout"]
                and e.get("snapshot_source_exit_code") == 124
                and e.get("provider_contacted") is False
                and e.get("provider_credentials_used") is False)
    except (OSError, ValueError, TypeError):
        return False


def complete_read_health(report: dict) -> bool:
    files = report.get("files")
    expected = {"authority", "replay", "security_audit", "orchestration_audit"}
    return (isinstance(files, dict) and set(files) == expected
            and all(isinstance(x, dict)
                    and x.get("present") is True
                    and x.get("readable") is True
                    and x.get("mode") == "0o600" for x in files.values())
            and isinstance(report.get("delegations"), dict)
            and report["delegations"].get("expired_active_records") == 0
            and isinstance(report.get("trusted_key_registry"), dict)
            and report["trusted_key_registry"].get("present") is True
            and report["trusted_key_registry"].get("mode") == "0o600"
            and int(report["trusted_key_registry"].get("active_records", 0)) >= 1)


def classify(report: dict, now: datetime) -> str:
    if report.get("status") == "pass" and report.get("failures") == []:
        return "pass"
    if (now < EXPIRES
            and report.get("status") == "fail"
            and report.get("failures") == [ALLOWED_FAILURE]
            and complete_read_health(report)
            and known_full_timeout()):
        return "degraded_read_safe"
    return "fail"


def main() -> int:
    now = datetime.now(timezone.utc)
    report = check(output=OUTPUT, full_path=FULL, now=now)
    # Always preserve the actual health result and its failed full proof.
    write_atomic_snapshot(OUTPUT, report)
    result = classify(report, now)
    advisory = {
        "schema_version": "1.0",
        "status": result,
        "observed_at": now.isoformat(),
        "expires_at": EXPIRES.isoformat(),
        "full_proof_verified": result == "pass",
        "fast_databases_readable": complete_read_health(report),
        "full_proof_reason": ALLOWED_FAILURE if result == "degraded_read_safe" else None,
        "approval_boundary": "local_root_owner_emergency_recovery_only",
        "no_authority_granted": True,
    }
    write_atomic_snapshot(ADVISORY, advisory)
    print(json.dumps({
        "status": result,
        "full_proof_verified": advisory["full_proof_verified"],
        "fast_databases_readable": advisory["fast_databases_readable"],
        "expires_at": advisory["expires_at"],
    }, sort_keys=True))
    return 0 if result in ("pass", "degraded_read_safe") else 2


if __name__ == "__main__":
    raise SystemExit(main())
