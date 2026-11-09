"""One-time post-OIDC browser decision session, NOT an approval service.

Stores the already *verified* Entra admin identity proof in the existing
private browser-session SQLite file. An unrelated Teams viewer cannot create
or consume this record. Only an explicit CSRF-bound POST may consume it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
import json
from pathlib import Path
import secrets
import sqlite3

from .entra_release_browser_sessions import OneTimeBrowserLoginStore
from .entra_release_stepup import (
    EntraStepUpDenied, ExactRelease, ReleaseIdentityRoute,
)


@dataclass(frozen=True)
class NewDecisionSession:
    cookie_value: str
    csrf_value: str
    approval_id: str


class OneTimeAdminDecisionStore:
    """Same private session DB, distinct short-lived login->decision handoff."""

    def __init__(self, db_path: Path, *, route: ReleaseIdentityRoute):
        route.validate()
        self.route = route
        self.login_store = OneTimeBrowserLoginStore(db_path)
        with self.login_store._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS browser_admin_decisions (
                    cookie_sha256 TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    release_fingerprint TEXT NOT NULL,
                    csrf_value TEXT NOT NULL,
                    verified_admin_proof_json TEXT NOT NULL,
                    authenticated_at TEXT NOT NULL
                )
            """)

    def issue(
        self, *, approval: ExactRelease,
        verified_admin_proof: dict, now: datetime,
    ) -> NewDecisionSession:
        approval.validate()
        self.route.validate()
        if (
            now.tzinfo is None or not now < approval.expires_at
            or not isinstance(verified_admin_proof, dict)
            or verified_admin_proof.get("release_authorized") is not False
            or verified_admin_proof.get("authenticated_admin_oid")
                != self.route.admin_approver_oid
            or verified_admin_proof.get("tenant_id") != self.route.tenant_id
            or verified_admin_proof.get("approval_id") != approval.approval_id
            or verified_admin_proof.get("candidate_sha") != approval.candidate_sha
            or verified_admin_proof.get("rollback_sha") != approval.rollback_sha
            or verified_admin_proof.get("scope_sha256") != approval.scope_sha256
            or verified_admin_proof.get("manifest_sha256") != approval.manifest_sha256
            or not isinstance(verified_admin_proof.get("evidence_sha256"), str)
            or len(verified_admin_proof["evidence_sha256"]) != 64
        ):
            raise EntraStepUpDenied("V5_VERIFIED_ADMIN_DECISION_SESSION_INVALID")
        raw_cookie=secrets.token_urlsafe(32)
        csrf=secrets.token_urlsafe(32)
        digest=sha256(raw_cookie.encode("ascii")).hexdigest()
        with self.login_store._connect() as db:
            db.execute("""
                INSERT INTO browser_admin_decisions VALUES (?,?,?,?,?,?)
            """, (
                digest, approval.approval_id, approval.fingerprint(), csrf,
                json.dumps(verified_admin_proof,sort_keys=True,separators=(",",":")),
                now.isoformat(),
            ))
        return NewDecisionSession(raw_cookie,csrf,approval.approval_id)

    def peek_approval_id(self, *, cookie_value: str) -> str:
        """Find pending review only by opaque cookie, never requester data."""
        if type(cookie_value) is not str or not 40 <= len(cookie_value) <= 128:
            raise EntraStepUpDenied("V5_DECISION_COOKIE_INVALID")
        digest=sha256(cookie_value.encode("utf-8")).hexdigest()
        with self.login_store._connect() as db:
            row=db.execute(
                "SELECT approval_id FROM browser_admin_decisions "
                "WHERE cookie_sha256=?", (digest,),
            ).fetchone()
        if row is None:
            raise EntraStepUpDenied("V5_DECISION_SESSION_MISSING_OR_REPLAYED")
        return str(row[0])

    def consume(
        self, *, cookie_value: str, csrf_value: str,
        approval: ExactRelease, now: datetime,
    ) -> dict:
        approval.validate()
        if (
            type(cookie_value) is not str or not 40<=len(cookie_value)<=128
            or type(csrf_value) is not str or not 40<=len(csrf_value)<=128
            or now.tzinfo is None
        ):
            raise EntraStepUpDenied("V5_DECISION_SESSION_INVALID")
        digest=sha256(cookie_value.encode("utf-8")).hexdigest()
        with self.login_store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""
                SELECT approval_id,release_fingerprint,csrf_value,
                       verified_admin_proof_json,authenticated_at
                  FROM browser_admin_decisions
                 WHERE cookie_sha256=?
            """,(digest,)).fetchone()
            if row is None:
                raise EntraStepUpDenied("V5_DECISION_SESSION_MISSING_OR_REPLAYED")
            instant=datetime.fromisoformat(row[4])
            if (
                row[0]!=approval.approval_id
                or not hmac.compare_digest(row[1],approval.fingerprint())
                or not hmac.compare_digest(row[2],csrf_value)
                or instant.tzinfo is None
                or instant>now
                or (now-instant)>timedelta(minutes=5)
                or now>=approval.expires_at
            ):
                raise EntraStepUpDenied("V5_DECISION_SESSION_SCOPE_OR_CSRF_MISMATCH")
            db.execute(
                "DELETE FROM browser_admin_decisions WHERE cookie_sha256=?",
                (digest,),
            )
        return json.loads(row[3])
