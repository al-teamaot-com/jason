"""Source-only one-time browser login sessions for admin Entra step-up.

A browser adapter must:
- bind the opaque cookie with HttpOnly, Secure, SameSite=Lax,
- use the exact registered confidential-client HTTPS redirect,
- redeem auth codes with PKCE server-side, and
- call independent OIDC proof validation before sending any signed decision.

NO approval is accepted by this store and it makes no provider calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import stat

from .entra_release_stepup import (
    EntraStepUpDenied, ExactRelease, PendingEntraLogin, new_login,
)

_COOKIE_BYTES = 32
_MAX_LOGIN_SECONDS = 300


@dataclass(frozen=True)
class NewBrowserLoginSession:
    cookie_value: str
    login: PendingEntraLogin
    # Cookie is an HTTP-only server-bound secret, never a Teams URL.
    cookie_secure: bool = True
    cookie_http_only: bool = True
    cookie_same_site: str = "Lax"


class OneTimeBrowserLoginStore:
    """One-use CSRF/PKCE session ledger in a protected SQLite state file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        parent = self.path.parent
        if (parent.is_symlink() or not parent.is_dir()
                or stat.S_IMODE(parent.stat().st_mode) & 0o077):
            raise EntraStepUpDenied("BROWSER_SESSION_DIRECTORY_NOT_PRIVATE")
        if self.path.is_symlink():
            raise EntraStepUpDenied("BROWSER_SESSION_PATH_SYMLINK")
        if self.path.exists():
            file_stat = self.path.stat()
            if (not stat.S_ISREG(file_stat.st_mode)
                    or stat.S_IMODE(file_stat.st_mode) & 0o077):
                raise EntraStepUpDenied("BROWSER_SESSION_FILE_NOT_PRIVATE")
        else:
            fd = os.open(
                str(self.path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
            )
            os.close(fd)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS browser_login_sessions(
                    cookie_sha256 TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    release_fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    started_at TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def issue(self, *, approval: ExactRelease, now: datetime) -> NewBrowserLoginSession:
        login = new_login(approval, now=now)
        raw_cookie = secrets.token_urlsafe(_COOKIE_BYTES)
        cookie_hash = sha256(raw_cookie.encode("ascii")).hexdigest()
        with self._connect() as db:
            db.execute(
                "INSERT INTO browser_login_sessions VALUES (?,?,?,?,?,?,?)",
                (cookie_hash, login.approval_id,
                 login.exact_release_fingerprint, login.state, login.nonce,
                 login.code_verifier, login.started_at.isoformat()),
            )
        return NewBrowserLoginSession(cookie_value=raw_cookie, login=login)

    def lookup_release_id(self, *, cookie_value: str) -> str:
        """Read one opaque-cookie-bound approval ID, NOT an authority grant."""
        if type(cookie_value) is not str or not 40 <= len(cookie_value) <= 128:
            raise EntraStepUpDenied("BROWSER_SESSION_COOKIE_INVALID")
        key = sha256(cookie_value.encode("utf-8")).hexdigest()
        with self._connect() as db:
            row = db.execute(
                "SELECT approval_id FROM browser_login_sessions WHERE cookie_sha256=?",
                (key,),
            ).fetchone()
        if row is None:
            raise EntraStepUpDenied("BROWSER_SESSION_MISSING_OR_REPLAYED")
        return str(row[0])

    def consume(
        self, *, cookie_value: str, returned_state: str,
        approval: ExactRelease, now: datetime,
    ) -> PendingEntraLogin:
        """Atomically consume a matching session before OAuth code redemption.

        A bogus state/cookie cannot consume another person's login. A valid
        session is one-use even if Microsoft denies a token exchange.
        """
        approval.validate()
        if (type(cookie_value) is not str or not 40 <= len(cookie_value) <= 128
                or type(returned_state) is not str
                or now.tzinfo is None):
            raise EntraStepUpDenied("BROWSER_SESSION_REQUEST_INVALID")
        cookie_hash = sha256(cookie_value.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT approval_id,release_fingerprint,state,nonce,"
                "code_verifier,started_at FROM browser_login_sessions "
                "WHERE cookie_sha256=?",
                (cookie_hash,),
            ).fetchone()
            if row is None:
                raise EntraStepUpDenied("BROWSER_SESSION_MISSING_OR_REPLAYED")
            try:
                started = datetime.fromisoformat(row[5])
            except (TypeError, ValueError) as exc:
                raise EntraStepUpDenied("BROWSER_SESSION_CORRUPTED") from exc
            if (started.tzinfo is None or started > now
                    or now >= approval.expires_at
                    or (now - started).total_seconds() > _MAX_LOGIN_SECONDS
                    or row[0] != approval.approval_id
                    or not hmac.compare_digest(
                        str(row[1]), approval.fingerprint(),
                    )
                    or not hmac.compare_digest(str(row[2]), returned_state)):
                raise EntraStepUpDenied("BROWSER_SESSION_STATE_OR_SCOPE_MISMATCH")
            db.execute(
                "DELETE FROM browser_login_sessions WHERE cookie_sha256=?",
                (cookie_hash,),
            )
        return PendingEntraLogin(
            approval_id=row[0], exact_release_fingerprint=row[1],
            state=row[2], nonce=row[3],
            code_verifier=row[4], started_at=started,
        )
