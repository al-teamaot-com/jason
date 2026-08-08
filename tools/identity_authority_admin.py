#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from kernel.identity_authority import (  # noqa: E402
    ApprovalRecord,
    AuthorityGrant,
    DelegationRecord,
    IdentityRecord,
    PermissionMode,
    SQLiteApprovalRepository,
    SQLiteAuthorityGrantRepository,
    SQLiteDelegationRepository,
    SQLiteIdentityAuthorityStore,
    SQLiteIdentityRepository,
)

DEFAULT_DB = Path("/var/lib/jason/authority/authority.sqlite3")


def parse_time(value: str | None):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def emit(status: str, **details) -> None:
    print(json.dumps({"status": status, **details}, sort_keys=True))


def store_for(path: Path) -> SQLiteIdentityAuthorityStore:
    return SQLiteIdentityAuthorityStore(path)


def cmd_health(args) -> int:
    store = store_for(args.database)
    try:
        mode = oct(os.stat(args.database).st_mode & 0o777)
        emit(
            "pass",
            database=str(args.database),
            file_mode=mode,
            identities=store.connection.execute("SELECT COUNT(*) FROM identities").fetchone()[0],
            grants=store.connection.execute("SELECT COUNT(*) FROM authority_grants").fetchone()[0],
            approvals=store.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0],
            delegations=store.connection.execute("SELECT COUNT(*) FROM delegations").fetchone()[0],
            contexts=store.connection.execute("SELECT COUNT(*) FROM execution_contexts").fetchone()[0],
        )
        return 0
    finally:
        store.close()


def cmd_identity_put(args) -> int:
    store = store_for(args.database)
    try:
        SQLiteIdentityRepository(store).put(
            IdentityRecord(args.identity_id, args.identity_type, args.organization_id, args.record_status)
        )
        emit("pass", action="identity_put", identity_id=args.identity_id)
        return 0
    finally:
        store.close()


def cmd_grant_put(args) -> int:
    store = store_for(args.database)
    try:
        SQLiteAuthorityGrantRepository(store).put(
            AuthorityGrant(
                grant_id=args.grant_id,
                subject_id=args.subject_id,
                capability=args.capability,
                organization_id=args.organization_id,
                client_id=args.client_id,
                permission=PermissionMode(args.permission),
                approval_required=args.approval_required,
                effective_from=parse_time(args.effective_from),
                effective_until=parse_time(args.effective_until),
                status=args.record_status,
            )
        )
        emit("pass", action="grant_put", grant_id=args.grant_id)
        return 0
    finally:
        store.close()


def cmd_approval_put(args) -> int:
    store = store_for(args.database)
    try:
        SQLiteApprovalRepository(store).put(
            ApprovalRecord(
                approval_id=args.approval_id,
                request_id=args.request_id,
                capability=args.capability,
                organization_id=args.organization_id,
                client_id=args.client_id,
                requested_by=args.requested_by,
                status=args.record_status,
                decided_by=args.decided_by,
                decided_at=parse_time(args.decided_at),
                expires_at=parse_time(args.expires_at),
            )
        )
        emit("pass", action="approval_put", approval_id=args.approval_id)
        return 0
    finally:
        store.close()


def cmd_delegation_put(args) -> int:
    effective_from = parse_time(args.effective_from)
    effective_until = parse_time(args.effective_until)
    if effective_from is None or effective_until is None:
        raise ValueError("delegation effective-from and effective-until are required")
    store = store_for(args.database)
    try:
        SQLiteDelegationRepository(store).put(
            DelegationRecord(
                delegation_id=args.delegation_id,
                delegator_id=args.delegator_id,
                delegate_id=args.delegate_id,
                organization_id=args.organization_id,
                client_id=args.client_id,
                capability=args.capability,
                maximum_mode=PermissionMode(args.maximum_mode),
                effective_from=effective_from,
                effective_until=effective_until,
                status=args.record_status,
            )
        )
        store.append_authority_audit(
            event_type="authority.delegation.recorded",
            correlation_id=args.correlation_id,
            principal_id=args.recorded_by,
            organization_id=args.organization_id,
            capability=args.capability,
            outcome="recorded",
            reason_codes=(args.delegation_id,),
        )
        emit("pass", action="delegation_put", delegation_id=args.delegation_id)
        return 0
    finally:
        store.close()


def cmd_delegation_revoke(args) -> int:
    store = store_for(args.database)
    try:
        changed = SQLiteDelegationRepository(store).revoke(
            args.delegation_id,
            revoked_at=datetime.now(timezone.utc),
            reason=args.reason,
        )
        if not changed:
            emit("fail", action="delegation_revoke", reason="delegation_not_found_or_already_revoked")
            return 2
        store.append_authority_audit(
            event_type="authority.delegation.revoked",
            correlation_id=args.correlation_id,
            principal_id=args.revoked_by,
            organization_id=args.organization_id,
            capability=args.capability,
            outcome="revoked",
            reason_codes=(args.reason,),
        )
        emit("pass", action="delegation_revoke", delegation_id=args.delegation_id)
        return 0
    finally:
        store.close()


def cmd_context_revoke(args) -> int:
    store = store_for(args.database)
    try:
        changed = store.revoke_context(
            args.context_id,
            revoked_at=datetime.now(timezone.utc),
            reason=args.reason,
        )
        if not changed:
            emit("fail", action="context_revoke", reason="context_not_found_or_already_revoked")
            return 2
        store.append_authority_audit(
            event_type="authority.context.revoked",
            correlation_id=args.correlation_id,
            principal_id=args.revoked_by,
            organization_id=args.organization_id,
            capability=args.capability,
            outcome="revoked",
            reason_codes=(args.reason,),
        )
        emit("pass", action="context_revoke", context_id=args.context_id)
        return 0
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Governed JKD-001 local pilot administration")
    p.add_argument("--database", type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health")
    health.set_defaults(func=cmd_health)

    identity = sub.add_parser("identity-put")
    identity.add_argument("--identity-id", required=True)
    identity.add_argument("--identity-type", required=True)
    identity.add_argument("--organization-id", required=True)
    identity.add_argument("--record-status", default="active")
    identity.set_defaults(func=cmd_identity_put)

    grant = sub.add_parser("grant-put")
    grant.add_argument("--grant-id", required=True)
    grant.add_argument("--subject-id", required=True)
    grant.add_argument("--capability", required=True)
    grant.add_argument("--organization-id", required=True)
    grant.add_argument("--client-id")
    grant.add_argument("--permission", choices=[m.value for m in PermissionMode], required=True)
    grant.add_argument("--approval-required", action="store_true")
    grant.add_argument("--effective-from")
    grant.add_argument("--effective-until")
    grant.add_argument("--record-status", default="active")
    grant.set_defaults(func=cmd_grant_put)

    approval = sub.add_parser("approval-put")
    approval.add_argument("--approval-id", required=True)
    approval.add_argument("--request-id", required=True)
    approval.add_argument("--capability", required=True)
    approval.add_argument("--organization-id", required=True)
    approval.add_argument("--client-id")
    approval.add_argument("--requested-by", required=True)
    approval.add_argument("--record-status", required=True)
    approval.add_argument("--decided-by")
    approval.add_argument("--decided-at")
    approval.add_argument("--expires-at")
    approval.set_defaults(func=cmd_approval_put)

    delegation = sub.add_parser("delegation-put")
    delegation.add_argument("--delegation-id", required=True)
    delegation.add_argument("--delegator-id", required=True)
    delegation.add_argument("--delegate-id", required=True)
    delegation.add_argument("--organization-id", required=True)
    delegation.add_argument("--client-id")
    delegation.add_argument("--capability", required=True)
    delegation.add_argument("--maximum-mode", choices=[m.value for m in PermissionMode], required=True)
    delegation.add_argument("--effective-from", required=True)
    delegation.add_argument("--effective-until", required=True)
    delegation.add_argument("--record-status", default="active")
    delegation.add_argument("--correlation-id", required=True)
    delegation.add_argument("--recorded-by", required=True)
    delegation.set_defaults(func=cmd_delegation_put)

    delegation_revoke = sub.add_parser("delegation-revoke")
    delegation_revoke.add_argument("--delegation-id", required=True)
    delegation_revoke.add_argument("--reason", required=True)
    delegation_revoke.add_argument("--correlation-id", required=True)
    delegation_revoke.add_argument("--revoked-by", required=True)
    delegation_revoke.add_argument("--organization-id", required=True)
    delegation_revoke.add_argument("--capability", required=True)
    delegation_revoke.set_defaults(func=cmd_delegation_revoke)

    revoke = sub.add_parser("context-revoke")
    revoke.add_argument("--context-id", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--correlation-id", required=True)
    revoke.add_argument("--revoked-by", required=True)
    revoke.add_argument("--organization-id", required=True)
    revoke.add_argument("--capability", required=True)
    revoke.set_defaults(func=cmd_context_revoke)

    return p


def main() -> int:
    args = parser().parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        emit("fail", error_type=type(exc).__name__, message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
