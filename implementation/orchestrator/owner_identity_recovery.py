"""Offline, exact, fail-closed AOT Owner binding recovery.

This module does not expose an MCP write or create an Owner. The local CLI
requires independently authenticated host administration and human approval.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class RecoveryDenied(ValueError):
    """A recovery precondition or exact-state check failed."""


@dataclass(frozen=True)
class RecoveryReview:
    email: str
    tenant_id: str
    object_id: str
    source_subject: str
    owner_subject: str
    digest: str


@contextmanager
def _read_only(path: Path):
    if not path.is_file() or path.is_symlink():
        raise RecoveryDenied("RECOVERY_DATABASE_UNAVAILABLE")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def _identity(db: sqlite3.Connection, identity_id: str) -> dict:
    row = db.execute("SELECT payload FROM identities WHERE identity_id=?", (identity_id,)).fetchone()
    if row is None:
        raise RecoveryDenied("RECOVERY_IDENTITY_MISSING")
    try:
        value = json.loads(row["payload"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise RecoveryDenied("RECOVERY_IDENTITY_CORRUPT") from exc
    if (value.get("identity_id") != identity_id
        or value.get("identity_type") != "human"
        or value.get("organization_id") != "aot"
        or value.get("status") != "active"):
        raise RecoveryDenied("RECOVERY_IDENTITY_NOT_ACTIVE_AOT_HUMAN")
    return value


def _binding_rows(db: sqlite3.Connection, email: str) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT microsoft_tenant_id,microsoft_object_id,jason_identity_id,"
        "client_id,email_address,status FROM microsoft_identity_bindings "
        "WHERE lower(email_address)=? AND status='active'",
        (email,)
    ).fetchall()


def review_recovery(
    *, binding_db: Path, authority_db: Path, email: str,
    attested_tenant_id: str, attested_object_id: str,
    owner_subject: str, live_owner_allowlist: frozenset[str]
) -> RecoveryReview:
    email = email.strip().casefold()
    tenant = attested_tenant_id.strip().casefold()
    object_id = attested_object_id.strip().casefold()
    owner = owner_subject.strip()
    if not email.endswith("@teamaot.com") and not email.endswith("@teamaom.com"):
        raise RecoveryDenied("RECOVERY_AOT_EMAIL_REQUIRED")
    if not re.fullmatch(r"[a-f0-9-]{36}", tenant) or not re.fullmatch(r"[a-f0-9-]{36}", object_id):
        raise RecoveryDenied("RECOVERY_ATTESTED_ENTRA_UUID_REQUIRED")
    if owner not in live_owner_allowlist or not live_owner_allowlist:
        raise RecoveryDenied("RECOVERY_NOT_IN_LIVE_OWNER_ALLOWLIST")
    with _read_only(binding_db) as bindings, _read_only(authority_db) as authority:
        rows = _binding_rows(bindings, email)
        if len(rows) != 1:
            raise RecoveryDenied("RECOVERY_EXACT_ONE_ACTIVE_EMAIL_BINDING_REQUIRED")
        row = rows[0]
        if (row["microsoft_tenant_id"].casefold() != tenant
            or row["microsoft_object_id"].casefold() != object_id):
            raise RecoveryDenied("RECOVERY_INDEPENDENT_ENTRA_ATTESTATION_MISMATCH")
        if row["client_id"] is not None:
            raise RecoveryDenied("RECOVERY_CLIENT_SCOPED_BINDING_DENIED")
        normalized_oid = re.sub(r"[^a-f0-9]", "", object_id)
        source = f"person-entra-{normalized_oid}"
        if row["jason_identity_id"] != source or source == owner:
            raise RecoveryDenied("RECOVERY_ONLY_JIT_READ_ONLY_SOURCE")
        _identity(authority, source)
        _identity(authority, owner)
        owner_bindings = bindings.execute(
            "SELECT count(*) FROM microsoft_identity_bindings "
            "WHERE jason_identity_id=? AND status='active'", (owner,)
        ).fetchone()[0]
        if owner_bindings:
            raise RecoveryDenied("RECOVERY_OWNER_ALREADY_BOUND")
        grants = authority.execute(
            "SELECT payload FROM authority_grants WHERE subject_id=?", (source,)
        ).fetchall()
        for record in grants:
            try:
                grant = json.loads(record["payload"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise RecoveryDenied("RECOVERY_SOURCE_GRANT_CORRUPT") from exc
            if grant.get("status") == "active" and grant.get("permission") != "observe":
                raise RecoveryDenied("RECOVERY_SOURCE_HAS_EXECUTE_OR_ADMINISTER_GRANT")
        proof = {
            "version": 1,
            "email": email, "tenant_id": tenant, "object_id": object_id,
            "source_subject": source, "owner_subject": owner,
            "source_active": True, "owner_active": True,
            "owner_allowlist": sorted(live_owner_allowlist),
            "active_source_grants": sorted(
                (json.loads(x["payload"]).get("grant_id"), json.loads(x["payload"]).get("status"))
                for x in grants
            ),
        }
        digest = hashlib.sha256(
            json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return RecoveryReview(email, tenant, object_id, source, owner, digest)


_AUDIT_DDL = (
    """CREATE TABLE IF NOT EXISTS owner_identity_recovery_audit (
        event_id TEXT PRIMARY KEY,
        occurred_at TEXT NOT NULL,
        email TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        object_id TEXT NOT NULL,
        from_subject TEXT NOT NULL,
        to_subject TEXT NOT NULL,
        review_digest TEXT NOT NULL,
        approval_reference TEXT NOT NULL,
        operator_account TEXT NOT NULL,
        action TEXT NOT NULL DEFAULT 'recover'
    )""",
    """CREATE TRIGGER IF NOT EXISTS owner_recovery_audit_no_update
    BEFORE UPDATE ON owner_identity_recovery_audit
    BEGIN SELECT RAISE(ABORT, 'immutable_audit'); END""",
    """CREATE TRIGGER IF NOT EXISTS owner_recovery_audit_no_delete
    BEFORE DELETE ON owner_identity_recovery_audit
    BEGIN SELECT RAISE(ABORT, 'immutable_audit'); END""",
)
_AUDIT_SCHEMA = ";\n".join(_AUDIT_DDL) + ";"





def _take_verified_backup(binding_db: Path, backup_path: Path) -> None:
    if backup_path.exists() or backup_path.is_symlink():
        raise RecoveryDenied("RECOVERY_BACKUP_ALREADY_EXISTS")
    backup_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = backup_path.open("xb")
    fd.close()
    backup_path.chmod(0o600)
    try:
        with sqlite3.connect(str(binding_db)) as src:
            with sqlite3.connect(str(backup_path)) as dst:
                src.backup(dst)
        with _read_only(backup_path) as copy:
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RecoveryDenied("RECOVERY_BACKUP_INTEGRITY_FAILED")
    except BaseException:
        backup_path.unlink(missing_ok=True)
        raise


def apply_recovery(
    *, binding_db: Path, authority_db: Path, review: RecoveryReview,
    live_owner_allowlist: frozenset[str], approval_reference: str,
    operator_account: str, backup_path: Path
) -> str:
    """Apply after the CLI separately establishes ROOT + interactive human approval.

    The reviewer digest binds the exact pre-state. Audit and switch commit in the
    same SQLite transaction; an on-disk backup is taken first and never overwritten.
    """
    if not approval_reference.strip() or not operator_account.strip():
        raise RecoveryDenied("RECOVERY_HUMAN_APPROVAL_AND_OPERATOR_REQUIRED")
    # Never rely only on a previously printed plan: re-check all trusted
    # identity/authority evidence and compare the digest immediately prior.
    verified = review_recovery(
        binding_db=binding_db, authority_db=authority_db,
        email=review.email, attested_tenant_id=review.tenant_id,
        attested_object_id=review.object_id,
        owner_subject=review.owner_subject,
        live_owner_allowlist=live_owner_allowlist,
    )
    if verified != review:
        raise RecoveryDenied("RECOVERY_PRESTATE_REVIEW_DIGEST_CHANGED")
    _take_verified_backup(binding_db, backup_path)
    # Local OS authentication is enforced by the CLI. This operation must never
    # be exposed as an MCP method or as a direct provider mutation.
    db = sqlite3.connect(str(binding_db), isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        # Schema, binding mutation and immutable audit are atomic. A denied
        # recovery must not even leave an empty audit table behind.
        for ddl in _AUDIT_DDL:
            db.execute(ddl)
        rows = _binding_rows(db, review.email)
        if (len(rows) != 1 or
            rows[0]["microsoft_tenant_id"].casefold() != review.tenant_id or
            rows[0]["microsoft_object_id"].casefold() != review.object_id or
            rows[0]["jason_identity_id"] != review.source_subject or
            rows[0]["client_id"] is not None):
            raise RecoveryDenied("RECOVERY_CONCURRENT_BINDING_CHANGE")
        if db.execute(
            "SELECT count(*) FROM microsoft_identity_bindings "
            "WHERE jason_identity_id=? AND status='active'", (review.owner_subject,)
        ).fetchone()[0] != 0:
            raise RecoveryDenied("RECOVERY_CONCURRENT_OWNER_BINDING_CHANGE")
        result = db.execute(
            "UPDATE microsoft_identity_bindings SET jason_identity_id=? "
            "WHERE microsoft_tenant_id=? AND microsoft_object_id=? "
            "AND jason_identity_id=? AND status='active' AND client_id IS NULL",
            (review.owner_subject, rows[0]["microsoft_tenant_id"],
             rows[0]["microsoft_object_id"], review.source_subject),
        )
        if result.rowcount != 1:
            raise RecoveryDenied("RECOVERY_UPDATE_NOT_EXACTLY_ONE_ROW")
        event_id = f"owner-recovery-{uuid4().hex}"
        db.execute(
            "INSERT INTO owner_identity_recovery_audit"
            "(event_id,occurred_at,email,tenant_id,object_id,from_subject,"
            "to_subject,review_digest,approval_reference,operator_account,action)"
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, datetime.now(timezone.utc).isoformat(),
             review.email, review.tenant_id, review.object_id,
             review.source_subject, review.owner_subject, review.digest,
             approval_reference.strip(), operator_account.strip(), "recover"),
        )
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()
    with _read_only(binding_db) as verified_db:
        result = verified_db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings "
            "WHERE microsoft_tenant_id=? AND microsoft_object_id=?",
            (rows[0]["microsoft_tenant_id"], rows[0]["microsoft_object_id"]),
        ).fetchone()
        audit = verified_db.execute(
            "SELECT count(*) FROM owner_identity_recovery_audit WHERE event_id=?",
            (event_id,),
        ).fetchone()[0]
        if result is None or result[0] != review.owner_subject or audit != 1:
            raise RecoveryDenied("RECOVERY_POST_READBACK_FAILED")
    return event_id


@dataclass(frozen=True)
class RecoveryRollbackReview:
    original_event_id: str
    email: str
    tenant_id: str
    object_id: str
    from_owner: str
    to_source: str
    digest: str


def review_rollback(
    *, binding_db: Path, authority_db: Path, email: str,
    attested_tenant_id: str, attested_object_id: str,
    owner_subject: str, original_event_id: str,
    live_owner_allowlist: frozenset[str],
) -> RecoveryRollbackReview:
    email = email.strip().casefold()
    tenant = attested_tenant_id.strip().casefold()
    oid = attested_object_id.strip().casefold()
    owner = owner_subject.strip()
    if owner not in live_owner_allowlist:
        raise RecoveryDenied("ROLLBACK_OWNER_NO_LONGER_ALLOWLISTED")
    with _read_only(binding_db) as bindings, _read_only(authority_db) as authority:
        try:
            audit = bindings.execute(
                "SELECT * FROM owner_identity_recovery_audit "
                "WHERE event_id=? AND action='recover'", (original_event_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise RecoveryDenied("ROLLBACK_RECOVERY_AUDIT_MISSING") from exc
        if (audit is None or audit["email"] != email or
            audit["tenant_id"].casefold() != tenant or
            audit["object_id"].casefold() != oid or
            audit["to_subject"] != owner):
            raise RecoveryDenied("ROLLBACK_ORIGINAL_EVENT_ATTESTATION_MISMATCH")
        source = audit["from_subject"]
        if source != "person-entra-" + re.sub(r"[^a-f0-9]", "", oid):
            raise RecoveryDenied("ROLLBACK_ORIGINAL_SOURCE_NOT_JIT_PRINCIPAL")
        _identity(authority, owner)
        _identity(authority, source)
        rows = _binding_rows(bindings, email)
        if (len(rows) != 1 or rows[0]["microsoft_tenant_id"].casefold() != tenant
            or rows[0]["microsoft_object_id"].casefold() != oid
            or rows[0]["jason_identity_id"] != owner
            or rows[0]["client_id"] is not None):
            raise RecoveryDenied("ROLLBACK_CURRENT_BINDING_NOT_EXACT_OWNER")
        if bindings.execute(
            "SELECT count(*) FROM microsoft_identity_bindings "
            "WHERE jason_identity_id=? AND status='active'", (source,)
        ).fetchone()[0]:
            raise RecoveryDenied("ROLLBACK_SOURCE_ALREADY_BOUND")
        grants = authority.execute(
            "SELECT payload FROM authority_grants WHERE subject_id=?", (source,)
        ).fetchall()
        for record in grants:
            try:
                grant = json.loads(record["payload"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise RecoveryDenied("ROLLBACK_SOURCE_GRANT_CORRUPT") from exc
            if grant.get("status") == "active" and grant.get("permission") != "observe":
                raise RecoveryDenied("ROLLBACK_SOURCE_NOT_READ_ONLY")
        material = {
            "action": "rollback", "event_id": original_event_id,
            "original_review": audit["review_digest"],
            "email": email, "tenant": tenant, "oid": oid,
            "owner": owner, "source": source,
            "owner_allowlist": sorted(live_owner_allowlist),
        }
        digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return RecoveryRollbackReview(
            original_event_id, email, tenant, oid, owner, source, digest,
        )


def apply_rollback(
    *, binding_db: Path, authority_db: Path, review: RecoveryRollbackReview,
    live_owner_allowlist: frozenset[str],
    approval_reference: str, operator_account: str, backup_path: Path,
) -> str:
    """Revert exactly one previously audited recovery; never restore an entire DB."""
    if not approval_reference.strip() or not operator_account.strip():
        raise RecoveryDenied("ROLLBACK_HUMAN_APPROVAL_REQUIRED")
    current = review_rollback(
        binding_db=binding_db, authority_db=authority_db,
        email=review.email, attested_tenant_id=review.tenant_id,
        attested_object_id=review.object_id, owner_subject=review.from_owner,
        original_event_id=review.original_event_id,
        live_owner_allowlist=live_owner_allowlist,
    )
    if current != review:
        raise RecoveryDenied("ROLLBACK_PRESTATE_REVIEW_DIGEST_CHANGED")
    _take_verified_backup(binding_db, backup_path)
    db = sqlite3.connect(str(binding_db), isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        rows = _binding_rows(db, review.email)
        if (len(rows) != 1 or
            rows[0]["microsoft_tenant_id"].casefold() != review.tenant_id or
            rows[0]["microsoft_object_id"].casefold() != review.object_id or
            rows[0]["jason_identity_id"] != review.from_owner or
            rows[0]["client_id"] is not None):
            raise RecoveryDenied("ROLLBACK_CONCURRENT_BINDING_CHANGE")
        if db.execute(
            "SELECT count(*) FROM microsoft_identity_bindings "
            "WHERE jason_identity_id=? AND status='active'", (review.to_source,)
        ).fetchone()[0] != 0:
            raise RecoveryDenied("ROLLBACK_CONCURRENT_SOURCE_BINDING_CHANGE")
        event = db.execute(
            "SELECT event_id FROM owner_identity_recovery_audit "
            "WHERE event_id=? AND action='recover'", (review.original_event_id,)
        ).fetchone()
        if event is None:
            raise RecoveryDenied("ROLLBACK_ORIGINAL_AUDIT_DISAPPEARED")
        updated = db.execute(
            "UPDATE microsoft_identity_bindings SET jason_identity_id=? "
            "WHERE microsoft_tenant_id=? AND microsoft_object_id=? "
            "AND jason_identity_id=? AND status='active' AND client_id IS NULL",
            (review.to_source, rows[0]["microsoft_tenant_id"],
             rows[0]["microsoft_object_id"], review.from_owner),
        )
        if updated.rowcount != 1:
            raise RecoveryDenied("ROLLBACK_NOT_EXACTLY_ONE_ROW")
        event_id = f"owner-recovery-revert-{uuid4().hex}"
        db.execute(
            "INSERT INTO owner_identity_recovery_audit"
            "(event_id,occurred_at,email,tenant_id,object_id,from_subject,"
            "to_subject,review_digest,approval_reference,operator_account,action)"
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, datetime.now(timezone.utc).isoformat(),
             review.email, review.tenant_id, review.object_id,
             review.from_owner, review.to_source, review.digest,
             approval_reference.strip(), operator_account.strip(), "rollback"),
        )
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()
    with _read_only(binding_db) as verified_db:
        row = verified_db.execute(
            "SELECT jason_identity_id FROM microsoft_identity_bindings "
            "WHERE microsoft_tenant_id=? AND microsoft_object_id=?",
            (rows[0]["microsoft_tenant_id"], rows[0]["microsoft_object_id"]),
        ).fetchone()
        audit = verified_db.execute(
            "SELECT count(*) FROM owner_identity_recovery_audit WHERE event_id=? "
            "AND action='rollback'", (event_id,),
        ).fetchone()[0]
        if row is None or row[0] != review.to_source or audit != 1:
            raise RecoveryDenied("ROLLBACK_POST_READBACK_FAILED")
    return event_id
