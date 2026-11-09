"""Private one-use signed decision session after independent Entra admin login.

The browser's authentication and the administrator's decision are separate
operations. The login callback never approves. This store has no authority to
apply a decision, and does not contact Microsoft or the Release Manager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
from typing import Any, Mapping

from .entra_release_browser_decision import _validate_proof
from .entra_release_stepup import EntraStepUpDenied, ExactRelease, ReleaseIdentityRoute


@dataclass(frozen=True)
class IssuedDecisionSession:
    cookie_value: str
    csrf_token: str


class OneTimeAdminDecisionStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        parent = self.path.parent
        if (parent.is_symlink() or not parent.is_dir()
                or stat.S_IMODE(parent.stat().st_mode) & 0o077):
            raise EntraStepUpDenied("DECISION_SESSION_DIRECTORY_NOT_PRIVATE")
        if self.path.is_symlink():
            raise EntraStepUpDenied("DECISION_SESSION_PATH_UNSAFE")
        if not self.path.exists():
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        if (not self.path.is_file() or stat.S_IMODE(self.path.stat().st_mode) & 0o077):
            raise EntraStepUpDenied("DECISION_SESSION_FILE_NOT_PRIVATE")
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS admin_release_decision_sessions(
                    cookie_sha256 TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    release_fingerprint TEXT NOT NULL,
                    csrf_token TEXT NOT NULL,
                    login_proof TEXT NOT NULL,
                    issued_at TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def issue(
        self, *, approval: ExactRelease, route: ReleaseIdentityRoute,
        verified_login_proof: Mapping[str, Any], now: datetime,
    ) -> IssuedDecisionSession:
        approval.validate()
        route.validate()
        if now.tzinfo is None or now >= approval.expires_at:
            raise EntraStepUpDenied("DECISION_SESSION_RELEASE_EXPIRED")
        _validate_proof(verified_login_proof, approval=approval, route=route, now=now)
        raw_cookie = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        cookie_hash = sha256(raw_cookie.encode("ascii")).hexdigest()
        sanitized = {
            k: verified_login_proof[k] for k in (
                "authenticated_admin_oid", "tenant_id", "owner_subject_id",
                "approval_id", "channel", "candidate_sha", "scope_sha256",
                "rollback_sha", "manifest_sha256", "auth_time", "evidence_sha256",
                "release_authorized",
            )
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO admin_release_decision_sessions VALUES(?,?,?,?,?,?)",
                (cookie_hash, approval.approval_id, approval.fingerprint(), csrf,
                 json.dumps(sanitized, sort_keys=True), now.isoformat()),
            )
        return IssuedDecisionSession(raw_cookie, csrf)

    def _read(self, cookie_value: str, approval: ExactRelease, now: datetime):
        if (not isinstance(cookie_value, str) or not 40 <= len(cookie_value) <= 128
                or now.tzinfo is None):
            raise EntraStepUpDenied("DECISION_SESSION_REQUEST_INVALID")
        key = sha256(cookie_value.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT approval_id,release_fingerprint,csrf_token,login_proof,issued_at "
                "FROM admin_release_decision_sessions WHERE cookie_sha256=?",
                (key,),
            ).fetchone()
        if row is None:
            raise EntraStepUpDenied("DECISION_SESSION_REPLAYED_OR_MISSING")
        try:
            issued = datetime.fromisoformat(row[4])
        except (ValueError, TypeError) as exc:
            raise EntraStepUpDenied("DECISION_SESSION_TIMESTAMP_INVALID") from exc
        if (issued.tzinfo is None or issued > now or now >= approval.expires_at
                or (now-issued).total_seconds() > 300
                or row[0] != approval.approval_id
                or not hmac.compare_digest(row[1], approval.fingerprint())):
            raise EntraStepUpDenied("DECISION_SESSION_EXPIRED_OR_SCOPE_CHANGED")
        return key,row

    def lookup_release_id(self, *, cookie_value: str) -> str:
        """Return exact server-stored approval ID without exposing login proof."""
        if not isinstance(cookie_value, str) or not 40 <= len(cookie_value) <= 128:
            raise EntraStepUpDenied("DECISION_SESSION_COOKIE_INVALID")
        key = sha256(cookie_value.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT approval_id FROM admin_release_decision_sessions "
                "WHERE cookie_sha256=?", (key,),
            ).fetchone()
        if row is None:
            raise EntraStepUpDenied("DECISION_SESSION_REPLAYED_OR_MISSING")
        return str(row[0])

    def load_consent(self, *, cookie_value: str, approval: ExactRelease,
                     now: datetime) -> str:
        """Return an HTML form CSRF value; never expose stored login proof."""
        _,row = self._read(cookie_value,approval,now)
        return row[2]

    def consume_explicit_decision(
        self, *, cookie_value: str, csrf_token: str, decision: str,
        approval: ExactRelease, route: ReleaseIdentityRoute, now: datetime,
    ) -> Mapping[str, Any]:
        if (decision not in ("approve","deny") or
                not isinstance(csrf_token,str) or not 40 <= len(csrf_token) <= 128):
            raise EntraStepUpDenied("DECISION_SESSION_EXPLICIT_CHOICE_REQUIRED")
        route.validate()
        key,row=self._read(cookie_value,approval,now)
        if not hmac.compare_digest(row[2],csrf_token):
            raise EntraStepUpDenied("DECISION_SESSION_CSRF_MISMATCH")
        try:
            proof=json.loads(row[3])
        except (TypeError,ValueError) as exc:
            raise EntraStepUpDenied("DECISION_SESSION_PROOF_INVALID") from exc
        _validate_proof(proof,approval=approval,route=route,now=now)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            deleted=db.execute(
                "DELETE FROM admin_release_decision_sessions "
                "WHERE cookie_sha256=? AND release_fingerprint=? AND csrf_token=?",
                (key,approval.fingerprint(),csrf_token),
            )
            if deleted.rowcount != 1:
                raise EntraStepUpDenied("DECISION_SESSION_REPLAYED_OR_MISSING")
        return proof
