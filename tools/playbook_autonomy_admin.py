#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from autonomous_remediation.playbook_autonomy_approval import (  # noqa: E402
    SQLitePlaybookAutonomyApprovalStore,
)

DEFAULT_DB = Path("/var/lib/jason/openclaw/playbook-autonomy.sqlite3")


def _time(value: str | None):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def _emit(status: str, **details) -> None:
    print(json.dumps({"status": status, **details}, sort_keys=True))


def cmd_approve(args) -> int:
    store = SQLitePlaybookAutonomyApprovalStore(args.database)
    try:
        record = store.new(
            playbook_id=args.playbook_id,
            playbook_version=args.playbook_version,
            policy_id=args.policy_id,
            allowed_capabilities=args.capability,
            approved_by=args.approved_by,
            expires_at=_time(args.expires_at),
        )
        store.put(record)
        _emit(
            "pass",
            action="approve",
            approval_id=record.approval_id,
            playbook_id=record.playbook_id,
            playbook_version=record.playbook_version,
            policy_id=record.policy_id,
            allowed_capabilities=list(record.allowed_capabilities),
            approved_by=record.approved_by,
            approved_at=record.approved_at.isoformat(),
            expires_at=record.expires_at.isoformat() if record.expires_at else None,
        )
        return 0
    finally:
        store.close()


def cmd_list(args) -> int:
    store = SQLitePlaybookAutonomyApprovalStore(args.database)
    try:
        rows = store._connection.execute(
            "SELECT payload FROM playbook_autonomy_approvals ORDER BY approval_id"
        ).fetchall()
        records = [store._decode(str(row["payload"])) for row in rows]
        _emit(
            "pass",
            action="list",
            approvals=[
                {
                    "approval_id": r.approval_id,
                    "playbook_id": r.playbook_id,
                    "playbook_version": r.playbook_version,
                    "policy_id": r.policy_id,
                    "allowed_capabilities": list(r.allowed_capabilities),
                    "approved_by": r.approved_by,
                    "approved_at": r.approved_at.isoformat(),
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "status": r.status,
                    "revoked_by": r.revoked_by,
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                    "revoke_reason": r.revoke_reason,
                }
                for r in records
            ],
        )
        return 0
    finally:
        store.close()


def cmd_revoke(args) -> int:
    store = SQLitePlaybookAutonomyApprovalStore(args.database)
    try:
        record = store.revoke(
            args.approval_id,
            revoked_by=args.revoked_by,
            reason=args.reason,
        )
        if record is None:
            _emit("fail", action="revoke", reason="approval_not_found")
            return 2
        _emit(
            "pass",
            action="revoke",
            approval_id=record.approval_id,
            status=record.status,
            revoked_by=record.revoked_by,
            revoked_at=record.revoked_at.isoformat() if record.revoked_at else None,
            reason=record.revoke_reason,
        )
        return 0
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Administer durable Project Jason playbook-autonomy promotions"
    )
    p.add_argument("--database", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="command", required=True)

    approve = sub.add_parser("approve")
    approve.add_argument("--playbook-id", required=True)
    approve.add_argument("--playbook-version", required=True)
    approve.add_argument("--policy-id", required=True)
    approve.add_argument("--capability", action="append", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--expires-at")
    approve.set_defaults(func=cmd_approve)

    listing = sub.add_parser("list")
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke")
    revoke.add_argument("--approval-id", required=True)
    revoke.add_argument("--revoked-by", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.set_defaults(func=cmd_revoke)

    return p


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        _emit("fail", error_type=type(exc).__name__, message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
