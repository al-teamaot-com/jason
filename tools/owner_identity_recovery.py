#!/usr/bin/env python3
"""Read-only review or supervised local break-glass recovery of AOT Owner identity.

Never expose this command as an MCP tool, scheduled automation, or remote model
action. The apply path requires an independently authenticated local sudo shell
and a human typing the exact one-use digest challenge.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "implementation"))

from orchestrator.owner_identity_recovery import (  # noqa: E402
    RecoveryDenied, apply_recovery, review_recovery,
    apply_rollback, review_rollback,
    recovery_audit_evidence_sha256,
)

DEFAULT_BINDINGS = Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")
DEFAULT_AUTHORITY = Path("/var/lib/jason/authority/authority.sqlite3")
DEFAULT_BACKUP = Path("/var/lib/jason/authority/owner-identity-recovery-backups")


def live_owner_allowlist() -> frozenset[str]:
    try:
        result = subprocess.run(
            ["docker", "inspect", "jason-mcp-pilot"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        containers = json.loads(result.stdout)
        if len(containers) != 1 or containers[0]["State"]["Running"] is not True:
            raise RecoveryDenied("RECOVERY_LIVE_MCP_CONTAINER_REQUIRED")
        values = [
            x.split("=", 1)[1]
            for x in containers[0]["Config"].get("Env", [])
            if x.startswith("JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=")
        ]
        if len(values) != 1:
            raise RecoveryDenied("RECOVERY_OWNER_ALLOWLIST_UNAVAILABLE")
        return frozenset(x.strip() for x in values[0].split(",") if x.strip())
    except RecoveryDenied:
        raise
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError, KeyError, IndexError) as exc:
        raise RecoveryDenied("RECOVERY_LIVE_OWNER_VERIFICATION_FAILED") from exc


def assert_production_targets(bindings_db: Path, authority_db: Path) -> None:
    """Production apply must never accept caller-selected alternate databases."""
    for candidate, canonical in (
        (bindings_db, DEFAULT_BINDINGS),
        (authority_db, DEFAULT_AUTHORITY),
    ):
        if (candidate != canonical or not candidate.is_file()
            or candidate.is_symlink() or candidate.resolve() != canonical):
            raise RecoveryDenied("RECOVERY_PRODUCTION_DATABASE_PATH_REQUIRED")
        if (candidate.stat().st_mode & 0o077) != 0:
            raise RecoveryDenied("RECOVERY_PRODUCTION_DATABASE_PERMISSIONS_INVALID")


def assert_human_local_approval(digest: str, owner: str, action: str = "RECOVER") -> str:
    """Break-glass is never inferred from a ChatGPT conversation or API caller."""
    if (os.geteuid() != 0 or not os.isatty(0) or not os.isatty(1)):
        raise RecoveryDenied("RECOVERY_LOCAL_ROOT_TTY_REQUIRED")
    operator = os.environ.get("SUDO_USER", "").strip()
    if not operator or operator == "root":
        raise RecoveryDenied("RECOVERY_INDIVIDUAL_SUDO_OPERATOR_REQUIRED")
    if action not in ("RECOVER", "ROLLBACK"):
        raise RecoveryDenied("RECOVERY_INVALID_LOCAL_APPROVAL_ACTION")
    phrase = f"{action} {owner} {digest[:16]}"
    print("Owner identity recovery is a production security/authority mutation.")
    print("Only a separately authorized AOT Owner/security administrator may proceed.")
    print(f"Type exactly: {phrase}")
    if input("> ").strip() != phrase:
        raise RecoveryDenied("RECOVERY_HUMAN_LOCAL_APPROVAL_MISMATCH")
    return operator


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Requires local sudo and interactive approval")
    p.add_argument("--rollback-event-id", default="", help="Review/undo one previously audited recovery")
    p.add_argument("--email", required=True)
    p.add_argument("--attested-tenant-id", required=True, help="Independently verified in Microsoft Entra")
    p.add_argument("--attested-object-id", required=True, help="Independently verified in Microsoft Entra")
    p.add_argument("--owner-subject", default="person-al")
    p.add_argument("--bindings-db", type=Path, default=DEFAULT_BINDINGS)
    p.add_argument("--authority-db", type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument("--expected-review-sha256", default="")
    p.add_argument("--approval-reference", default="")
    p.add_argument("--directory-evidence-reference", default="")
    args = p.parse_args()
    try:
        owners = live_owner_allowlist()
        if args.rollback_event_id:
            plan = review_rollback(
                binding_db=args.bindings_db,
                authority_db=args.authority_db,
                email=args.email,
                attested_tenant_id=args.attested_tenant_id,
                attested_object_id=args.attested_object_id,
                owner_subject=args.owner_subject,
                original_event_id=args.rollback_event_id,
                live_owner_allowlist=owners,
            )
            source = plan.to_source
            target = plan.from_owner
            action = "ROLLBACK"
        else:
            plan = review_recovery(
                binding_db=args.bindings_db,
                authority_db=args.authority_db,
                email=args.email,
                attested_tenant_id=args.attested_tenant_id,
                attested_object_id=args.attested_object_id,
                owner_subject=args.owner_subject,
                live_owner_allowlist=owners,
            )
            source = plan.source_subject
            target = plan.owner_subject
            action = "RECOVER"
        if not args.apply:
            print(json.dumps({
                "status": "review_only",
                "email": plan.email,
                "source_subject": source,
                "target_owner_subject": target,
                "action": action,
                "review_sha256": plan.digest,
                "no_mutations": True,
                "requires_separate_verified_owner_and_production_authorization": True,
            }, sort_keys=True))
            return 0
        assert_production_targets(args.bindings_db, args.authority_db)
        if not args.expected_review_sha256 or args.expected_review_sha256 != plan.digest:
            raise RecoveryDenied("RECOVERY_EXPECTED_REVIEW_SHA_REQUIRED_AND_MUST_MATCH")
        if len(args.approval_reference.strip()) < 8 or len(args.directory_evidence_reference.strip()) < 8:
            raise RecoveryDenied("RECOVERY_APPROVAL_AND_INDEPENDENT_DIRECTORY_EVIDENCE_REQUIRED")
        # Bind each operation to separate evidence references, not email or title alone.
        operator = assert_human_local_approval(plan.digest, args.owner_subject, action)
        # Re-read running production policy after the human approval, too.
        owners = live_owner_allowlist()
        backup = DEFAULT_BACKUP / f"binding-backup-{uuid4().hex}.sqlite3"
        evidence = (
            f"{args.approval_reference.strip()} | "
            f"independent_directory:{args.directory_evidence_reference.strip()}"
        )
        if action == "ROLLBACK":
            event = apply_rollback(
                binding_db=args.bindings_db, authority_db=args.authority_db,
                review=plan, live_owner_allowlist=owners,
                approval_reference=evidence,
                operator_account=operator, backup_path=backup,
            )
        else:
            event = apply_recovery(
                binding_db=args.bindings_db, authority_db=args.authority_db,
                review=plan, live_owner_allowlist=owners,
                approval_reference=evidence,
                operator_account=operator, backup_path=backup,
            )
        print(json.dumps({
            "status": "verified_applied", "event_id": event,
            "owner_subject": args.owner_subject,
            "action": action,
            "backup_path": str(backup),
            "audit_in_binding_db": True,
            "audit_evidence_sha256": recovery_audit_evidence_sha256(
                binding_db=args.bindings_db, event_id=event,
            ),
            "requires_external_immutable_audit_archive": True,
        }, sort_keys=True))
        return 0
    except RecoveryDenied as exc:
        print(json.dumps({"status": "rejected", "error_code": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
