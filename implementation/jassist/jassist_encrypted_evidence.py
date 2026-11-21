"""Fail-closed encrypted J-Assist screenshot evidence storage (preproduction).

A server-owned 256-bit key (e.g., from Jason's governed OpenBao resolver)
encrypts each accepted image with AES-GCM and receipt/identity-bound AAD.
No plaintext screenshots or credentials persist. The reviewer must be a
trusted approved external DLP/content policy; this module has no accept-all
fallback. Redaction requiring image modification is rejected by this
v1 exact-hash receipt protocol; a future schema must bind both digests.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time
from threading import RLock
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .screen_evidence_intake import (
    AcceptedScreen, ScreenReceipt, ScreenEvidenceIntake, MAX_IMAGE_BYTES,
)
from .session_gate import Denied, VerifiedTechnician

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jassist_images (
 receipt_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
 device_uid TEXT NOT NULL, subject TEXT NOT NULL, tenant TEXT NOT NULL,
 image_sha256 TEXT NOT NULL, image_size INTEGER NOT NULL,
 accepted_at REAL NOT NULL, expires_at REAL NOT NULL,
 reviewer_id TEXT NOT NULL, policy_version TEXT NOT NULL,
 iv BLOB NOT NULL, ciphertext BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS jassist_nonces (
 session_id TEXT NOT NULL, nonce TEXT NOT NULL,
 expires_at REAL NOT NULL, state TEXT NOT NULL,
 PRIMARY KEY (session_id,nonce)
);
CREATE TABLE IF NOT EXISTS jassist_image_audit (
 event_id INTEGER PRIMARY KEY, receipt_id TEXT NOT NULL,
 session_id TEXT NOT NULL, action TEXT NOT NULL,
 timestamp REAL NOT NULL
);
"""


class EncryptedJAssistEvidenceIntake:
    def __init__(self, *, db_path: Path, encryption_key: bytes,
                 gate, review_content: Callable[[bytes], AcceptedScreen],
                 clock: Callable[[], float] = time.time,
                 maximum_images: int = 256):
        if (not isinstance(db_path,Path) or not db_path.is_absolute()
                or type(encryption_key) is not bytes or len(encryption_key)!=32
                or not callable(review_content)
                or not callable(getattr(gate,"authorize_read",None))
                or not callable(clock)
                or type(maximum_images) is not int
                or not 1<=maximum_images<=1024):
            raise ValueError("governed encrypted evidence storage and DLP reader required")
        if (db_path.parent.stat().st_mode & 0o022
                or db_path.is_symlink()):
            raise ValueError("J-Assist evidence directory cannot be writable by others")
        if not db_path.exists():
            fd=os.open(db_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        if (not stat.S_ISREG(db_path.stat().st_mode)
                or db_path.stat().st_mode & 0o077):
            raise ValueError("evidence database must have mode 0600")
        self._db=str(db_path)
        self._cipher=AESGCM(encryption_key)
        self._gate=gate
        self._review=review_content
        self._clock=clock
        self._cap=maximum_images
        self._lock=RLock()
        with self._connect() as db:db.executescript(_SCHEMA)

    def _connect(self):
        db=sqlite3.connect(self._db,timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _aad(receipt: ScreenReceipt, tenant: str):
        return ("jassist-image:v1|"+receipt.receipt_id+"|"+receipt.session_id+
                "|"+receipt.device_uid+"|"+receipt.subject+"|"+tenant+
                "|"+receipt.image_sha256+"|"+str(receipt.expires_at)).encode()

    def _authorize(self, *, trusted_technician, session_id, session_token,
                   device_uid):
        if not isinstance(trusted_technician,VerifiedTechnician):
            raise Denied("trusted technician identity required")
        self._gate.authorize_read(trusted_context=trusted_technician,
            session_id=session_id,token=session_token,device_uid=device_uid)

    def receive(self, *, trusted_technician, session_id, session_token,
                device_uid, request_nonce, image, declared_sha256):
        if (type(image) is not bytes or not 0<len(image)<=MAX_IMAGE_BYTES
                or not isinstance(request_nonce,str)
                or not 16<=len(request_nonce)<=96
                or not request_nonce.isascii() or not request_nonce.isalnum()
                or not isinstance(declared_sha256,str)
                or len(declared_sha256)!=64):
            raise Denied("invalid screenshot envelope")
        digest=hashlib.sha256(image).hexdigest()
        if not hmac.compare_digest(digest,declared_sha256):
            raise Denied("screenshot hash mismatch")
        ScreenEvidenceIntake._format(image)
        self._authorize(trusted_technician=trusted_technician,
                        session_id=session_id,session_token=session_token,
                        device_uid=device_uid)
        stamp=self._clock()
        # Reserve nonce in SQLite BEFORE DLP. Reject concurrent and
        # process-restart replay, including abandoned pending reservations.
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM jassist_nonces WHERE expires_at<=?",(stamp,))
            if (db.execute("SELECT COUNT(*) FROM jassist_images WHERE expires_at>?",
                           (stamp,)).fetchone()[0]>=self._cap):
                raise Denied("encrypted evidence capacity exhausted")
            try:
                db.execute("INSERT INTO jassist_nonces VALUES (?,?,?,?)",
                    (session_id,request_nonce,stamp+300,"pending"))
            except sqlite3.IntegrityError as exc:
                raise Denied("replayed screenshot request") from exc
        committed=False
        try:
            try:
                reviewed=self._review(image)
            except Exception as exc:
                raise Denied("screenshot content review rejected") from exc
            if (not isinstance(reviewed,AcceptedScreen)
                    or reviewed.image!=image
                    or not isinstance(reviewed.reviewer_id,str)
                    or not reviewed.reviewer_id.strip()
                    or not isinstance(reviewed.policy_version,str)
                    or not reviewed.policy_version.strip()):
                raise Denied("unapproved or modified screenshot content")
            self._authorize(trusted_technician=trusted_technician,
                            session_id=session_id,session_token=session_token,
                            device_uid=device_uid)
            accepted_at=self._clock()
            receipt=ScreenReceipt(
                receipt_id=secrets.token_urlsafe(24),
                session_id=session_id,device_uid=device_uid,
                subject=trusted_technician.subject,image_sha256=digest,
                bytes_accepted=len(image),accepted_at=accepted_at,
                expires_at=accepted_at+120)
            iv=os.urandom(12)
            sealed=self._cipher.encrypt(iv,image,self._aad(receipt, trusted_technician.tenant_id))
            with self._lock, self._connect() as db:
                if db.execute("SELECT COUNT(*) FROM jassist_images WHERE expires_at>?",
                              (accepted_at,)).fetchone()[0]>=self._cap:
                    raise Denied("encrypted evidence capacity exhausted")
                db.execute("INSERT INTO jassist_images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                    receipt.receipt_id,session_id,device_uid,receipt.subject,
                    trusted_technician.tenant_id,receipt.image_sha256,len(image),
                    receipt.accepted_at,receipt.expires_at,
                    reviewed.reviewer_id,reviewed.policy_version,iv,sealed))
                db.execute("UPDATE jassist_nonces SET state='committed' WHERE session_id=? AND nonce=?",
                    (session_id,request_nonce))
                db.execute("INSERT INTO jassist_image_audit (receipt_id,session_id,action,timestamp) VALUES (?,?,?,?)",
                    (receipt.receipt_id,session_id,"accepted",accepted_at))
            committed=True
            return receipt
        finally:
            if not committed:
                with self._lock,self._connect() as db:
                    db.execute("DELETE FROM jassist_nonces WHERE session_id=? AND nonce=? AND state='pending'",
                               (session_id,request_nonce))

    def retrieve(self, *, trusted_technician, session_id, session_token,
                 device_uid, receipt_id):
        self._authorize(trusted_technician=trusted_technician,
                        session_id=session_id,session_token=session_token,
                        device_uid=device_uid)
        with self._connect() as db:
            row=db.execute("""SELECT session_id,device_uid,subject,tenant,
                        image_sha256,image_size,accepted_at,expires_at,
                        iv,ciphertext FROM jassist_images WHERE receipt_id=?""",
                        (receipt_id,)).fetchone()
        if row is None:raise Denied("evidence receipt unavailable")
        sid,device,subject,tenant,digest,size,at,expiry,iv,sealed=row
        if (self._clock()>=expiry or sid!=session_id or device!=device_uid
                or subject!=trusted_technician.subject
                or tenant!=trusted_technician.tenant_id):
            raise Denied("evidence expired or not bound to technician/device")
        receipt=ScreenReceipt(receipt_id,sid,device,subject,digest,size,at,expiry)
        try:
            image=self._cipher.decrypt(iv,sealed,self._aad(receipt,tenant))
        except Exception as exc:
            raise Denied("evidence failed authenticated decryption") from exc
        if len(image)!=size or not hmac.compare_digest(hashlib.sha256(image).hexdigest(),digest):
            raise Denied("screenshot integrity mismatch")
        return receipt,image

    def purge_expired(self):
        now=self._clock()
        with self._lock,self._connect() as db:
            count=db.execute("DELETE FROM jassist_images WHERE expires_at<=?",(now,)).rowcount
            db.execute("DELETE FROM jassist_nonces WHERE expires_at<=?",(now,))
        return count
