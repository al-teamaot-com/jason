"""Durable server-only J-Assist session authority (preproduction).

The key is injected by Jason's governed secret source, never passed by a
Chrome client. SQLite holds only encrypted internal session credentials and
bounded metadata; access is rechecked against the *current* Entra group and
Datto device source on every operation. No browser credential is ever issued.

A production deployment additionally needs the governed secret resolver,
reviewed configuration publisher and accepted encrypted evidence store.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .session_gate import Denied, SessionReceipt, VerifiedTechnician

_UID = re.compile(r"^[0-9]{1,24}$")
_SID = re.compile(r"^[a-zA-Z0-9_-]{12,128}$")
_MAX_SECONDS = 300

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jassist_sessions (
 session_id TEXT PRIMARY KEY, subject TEXT NOT NULL, tenant TEXT NOT NULL,
 device_uid TEXT NOT NULL, credential_digest BLOB NOT NULL,
 sealed_credential BLOB NOT NULL, nonce BLOB NOT NULL,
 expires_at REAL NOT NULL, status TEXT NOT NULL
 CHECK(status IN ('active','closed','revoked'))
);
CREATE TABLE IF NOT EXISTS jassist_session_events (
 event_id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
 event_type TEXT NOT NULL, occurred_at REAL NOT NULL,
 subject TEXT NOT NULL, device_uid TEXT NOT NULL
);
"""


class DurableJAssistSessionGate:
    def __init__(self, *, db_path: Path, encryption_key: bytes,
                 identity: Callable[[object], VerifiedTechnician],
                 can_read_datto_device: Callable[[VerifiedTechnician, str], bool],
                 clock: Callable[[], float] = time.time):
        if (not isinstance(db_path, Path) or not db_path.is_absolute()
                or db_path.name in {"", ".", ".."}
                or type(encryption_key) is not bytes or len(encryption_key) != 32
                or not callable(identity) or not callable(can_read_datto_device)
                or not callable(clock)):
            raise ValueError("approved durable path, 256-bit key and trusted readers required")
        parent = db_path.parent
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_mode & 0o022):
            raise ValueError("J-Assist session database parent must not be writable by others")
        if db_path.is_symlink():
            raise ValueError("J-Assist session database cannot be a symlink")
        if not db_path.exists():
            fd = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        file_info = db_path.stat()
        if (not stat.S_ISREG(file_info.st_mode)
                or file_info.st_mode & 0o077):
            raise ValueError("J-Assist session database must have mode 0600")
        self._path = str(db_path)
        self._cipher = AESGCM(encryption_key)
        self._identity = identity
        self._authorize = can_read_datto_device
        self._clock = clock
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self):
        db = sqlite3.connect(self._path,timeout=5)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    @staticmethod
    def _aad(session_id, technician, device_uid):
        return ("jassist-session:v1|"+session_id+"|"+
                technician.subject+"|"+technician.tenant_id+"|"+
                device_uid).encode()

    def _principal(self, ctx):
        principal=self._identity(ctx)
        if (not isinstance(principal, VerifiedTechnician)
                or not principal.subject.strip()
                or principal.tenant_id!="aot"):
            raise Denied("trusted AOT technician identity required")
        return principal

    def _has_access(self, principal, device_uid):
        try:
            return self._authorize(principal,device_uid) is True
        except Exception:
            return False

    def can_start(self, *, trusted_context, device_uid):
        """Read-only current authorization check; no session is opened."""
        if not isinstance(device_uid,str) or not _UID.fullmatch(device_uid):
            return False
        try:
            principal=self._principal(trusted_context)
            return self._has_access(principal,device_uid)
        except Exception:
            return False

    def start(self, *, trusted_context, device_uid, consent,
              lifetime_seconds=120):
        if (consent is not True or not isinstance(device_uid,str)
                or not _UID.fullmatch(device_uid)
                or type(lifetime_seconds) is not int
                or not 1<=lifetime_seconds<=_MAX_SECONDS):
            raise Denied("invalid consent, device or lifetime")
        principal=self._principal(trusted_context)
        if not self._has_access(principal,device_uid):
            raise Denied("current J-Assist group or Datto device authorization denied")
        session_id=secrets.token_urlsafe(24)
        token=secrets.token_urlsafe(32)
        nonce=os.urandom(12)
        sealed=self._cipher.encrypt(nonce,token.encode(),
            self._aad(session_id,principal,device_uid))
        expires=self._clock()+lifetime_seconds
        with self._connect() as db:
            db.execute("INSERT INTO jassist_sessions VALUES (?,?,?,?,?,?,?,?,?)",(
                session_id,principal.subject,principal.tenant_id,device_uid,
                hashlib.sha256(token.encode()).digest(),sealed,nonce,expires,"active"))
            db.execute("INSERT INTO jassist_session_events (session_id,event_type,occurred_at,subject,device_uid) VALUES (?,?,?,?,?)",(
                session_id,"opened",self._clock(),principal.subject,device_uid))
        return SessionReceipt(session_id,device_uid,expires),token

    def _session(self, *, trusted_context, session_id, token, device_uid):
        principal=self._principal(trusted_context)
        if (not isinstance(session_id,str) or not _SID.fullmatch(session_id)
                or not isinstance(token,str)
                or not isinstance(device_uid,str) or not _UID.fullmatch(device_uid)):
            raise Denied("invalid session selector")
        with self._connect() as db:
            row=db.execute("SELECT subject,tenant,device_uid,credential_digest,expires_at,status FROM jassist_sessions WHERE session_id=?",(session_id,)).fetchone()
        if row is None:raise Denied("session unavailable")
        subject,tenant,device,digest,expires,state=row
        if (state!="active" or self._clock()>=expires
                or subject!=principal.subject or tenant!=principal.tenant_id
                or device!=device_uid
                or not hmac.compare_digest(digest,hashlib.sha256(token.encode()).digest())):
            raise Denied("session expired, revoked or mismatch")
        if not self._has_access(principal,device_uid):
            with self._connect() as db:
                db.execute("UPDATE jassist_sessions SET status='revoked' WHERE session_id=? AND status='active'",(session_id,))
                db.execute("INSERT INTO jassist_session_events (session_id,event_type,occurred_at,subject,device_uid) VALUES (?,?,?,?,?)",(
                    session_id,"revoked",self._clock(),principal.subject,device_uid))
            raise Denied("current technician group or Datto permission revoked")
        return principal

    def authorize_read(self, *, trusted_context, session_id, token, device_uid):
        self._session(trusted_context=trusted_context,
            session_id=session_id,token=token,device_uid=device_uid)

    def credential_for(self, session_id):
        """Internal service only: the client never sends or receives this token."""
        if not isinstance(session_id,str) or not _SID.fullmatch(session_id):
            return None
        with self._connect() as db:
            row=db.execute("SELECT subject,tenant,device_uid,sealed_credential,nonce,expires_at,status FROM jassist_sessions WHERE session_id=?",(session_id,)).fetchone()
        if row is None:return None
        subject,tenant,device,sealed,nonce,expires,state=row
        if state!="active" or self._clock()>=expires:return None
        principal=VerifiedTechnician(subject,tenant)
        try:
            plain=self._cipher.decrypt(nonce,sealed,
                self._aad(session_id,principal,device))
            return plain.decode()
        except Exception as exc:
            raise Denied("session secret cannot be decrypted") from exc

    def stop(self, *, trusted_context, session_id, token, device_uid):
        principal=self._session(trusted_context=trusted_context,
            session_id=session_id,token=token,device_uid=device_uid)
        with self._connect() as db:
            db.execute("UPDATE jassist_sessions SET status='closed' WHERE session_id=? AND status='active'",(session_id,))
            db.execute("INSERT INTO jassist_session_events (session_id,event_type,occurred_at,subject,device_uid) VALUES (?,?,?,?,?)",(
                session_id,"closed",self._clock(),principal.subject,device_uid))

    def purge_expired(self):
        now=self._clock()
        with self._connect() as db:
            count=db.execute("DELETE FROM jassist_sessions WHERE expires_at<=?",(now,)).rowcount
        return count
