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
            db.execute("""
                CREATE TABLE IF NOT EXISTS admin_release_decision_outbox(
                    approval_id TEXT PRIMARY KEY,
                    release_fingerprint TEXT NOT NULL,
                    signed_envelope TEXT NOT NULL,
                    signed_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending','delivered')),
                    recorded_at TEXT NOT NULL
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

    def preview_explicit_decision(
        self, *, cookie_value: str, csrf_token: str, decision: str,
        approval: ExactRelease, route: ReleaseIdentityRoute, now: datetime,
    ) -> Mapping[str, Any]:
        """Read-only verified proof: signer can prepare before atomic consume."""
        if decision not in ("approve", "deny") or type(csrf_token) is not str:
            raise EntraStepUpDenied("DECISION_SESSION_EXPLICIT_CHOICE_REQUIRED")
        route.validate()
        _, row = self._read(cookie_value, approval, now)
        if not hmac.compare_digest(row[2], csrf_token):
            raise EntraStepUpDenied("DECISION_SESSION_CSRF_MISMATCH")
        try:
            proof = json.loads(row[3])
        except (TypeError, ValueError) as exc:
            raise EntraStepUpDenied("DECISION_SESSION_PROOF_INVALID") from exc
        _validate_proof(proof, approval=approval, route=route, now=now)
        return proof

    def record_signed_decision(
        self, *, cookie_value: str, csrf_token: str, decision: str,
        approval: ExactRelease, route: ReleaseIdentityRoute,
        signed_envelope: Mapping[str, Any], now: datetime,
    ) -> str:
        """Atomically consume consent and durably store signed decision.

        A crash before commit leaves consent pending. A crash afterwards leaves
        an immutable signed outbox record for idempotent delivery to the
        existing approval consumer, rather than losing the user's decision.
        """
        self.preview_explicit_decision(
            cookie_value=cookie_value, csrf_token=csrf_token,
            decision=decision, approval=approval, route=route, now=now,
        )
        if not isinstance(signed_envelope, Mapping) or set(signed_envelope) != {
            "payload", "key_id", "signature",
        }:
            raise EntraStepUpDenied("DECISION_OUTBOX_SIGNED_EVIDENCE_REQUIRED")
        payload = signed_envelope.get("payload")
        if (not isinstance(payload, dict)
                or payload.get("schema_version") != "5.0"
                or payload.get("channel") != "entra_browser_admin"
                or payload.get("decision") != decision
                or payload.get("approval_id") != approval.approval_id
                or payload.get("release_fingerprint") != approval.fingerprint()
                or payload.get("authenticated_admin_oid") != route.admin_approver_oid
                or payload.get("tenant_id") != route.tenant_id):
            raise EntraStepUpDenied("DECISION_OUTBOX_SIGNED_SCOPE_MISMATCH")
        from .entra_release_browser_decision import _canonical
        serialized = _canonical(dict(signed_envelope))
        if len(serialized) > 16384:
            raise EntraStepUpDenied("DECISION_OUTBOX_EVIDENCE_TOO_LARGE")
        fingerprint = sha256(serialized).hexdigest()
        key = sha256(cookie_value.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT approval_id,release_fingerprint,csrf_token,login_proof,issued_at "
                "FROM admin_release_decision_sessions WHERE cookie_sha256=?",
                (key,),
            ).fetchone()
            if row is None or row[0] != approval.approval_id or (
                not hmac.compare_digest(row[1], approval.fingerprint())
            ) or not hmac.compare_digest(row[2], csrf_token):
                raise EntraStepUpDenied("DECISION_SESSION_REPLAYED_OR_MISSING")
            # A second browser session can never replace a recorded decision.
            if db.execute(
                "SELECT 1 FROM admin_release_decision_outbox WHERE approval_id=?",
                (approval.approval_id,),
            ).fetchone() is not None:
                raise EntraStepUpDenied("DECISION_OUTBOX_ALREADY_RECORDED")
            deleted = db.execute(
                "DELETE FROM admin_release_decision_sessions WHERE cookie_sha256=? "
                "AND release_fingerprint=? AND csrf_token=?",
                (key, approval.fingerprint(), csrf_token),
            )
            if deleted.rowcount != 1:
                raise EntraStepUpDenied("DECISION_SESSION_REPLAYED_OR_MISSING")
            db.execute(
                "INSERT INTO admin_release_decision_outbox VALUES(?,?,?,?,?,?)",
                (approval.approval_id, approval.fingerprint(),
                 serialized.decode("utf-8"), fingerprint, "pending",
                 now.isoformat()),
            )
        return fingerprint

    def pending_signed_decisions(self, *, limit: int = 20) -> tuple[Mapping[str, Any], ...]:
        """Read-only bounded pending delivery. Does not authorize release."""
        if type(limit) is not int or not 1 <= limit <= 20:
            raise EntraStepUpDenied("DECISION_OUTBOX_LIMIT_INVALID")
        with self._connect() as db:
            rows = db.execute(
                "SELECT signed_envelope,signed_sha256 FROM admin_release_decision_outbox "
                "WHERE state='pending' ORDER BY recorded_at LIMIT ?",
                (limit,),
            ).fetchall()
        documents = []
        for source, expected in rows:
            if sha256(source.encode("utf-8")).hexdigest() != expected:
                raise EntraStepUpDenied("DECISION_OUTBOX_EVIDENCE_TAMPERED")
            documents.append(json.loads(source))
        return tuple(documents)

    def mark_signed_delivered(self, *, approval_id: str, signed_sha256: str) -> None:
        """Idempotent acknowledgement after protected consumer accepts evidence."""
        if not isinstance(signed_sha256, str) or len(signed_sha256) != 64:
            raise EntraStepUpDenied("DECISION_OUTBOX_ACK_INVALID")
        with self._connect() as db:
            row = db.execute(
                "SELECT signed_sha256,state FROM admin_release_decision_outbox WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if row is None or not hmac.compare_digest(row[0], signed_sha256):
                raise EntraStepUpDenied("DECISION_OUTBOX_ACK_CONFLICT")
            if row[1] == "pending":
                db.execute(
                    "UPDATE admin_release_decision_outbox SET state='delivered' "
                    "WHERE approval_id=? AND signed_sha256=?",
                    (approval_id,signed_sha256),
                )
