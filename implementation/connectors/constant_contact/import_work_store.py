"""Private encrypted work records for bounded Constant Contact import proposals.

This store is NOT an approval ledger and does not authorize provider actions.
It retains the exact contact payload as AES-GCM ciphertext, a short expiration,
and the original server-issued approval reference. All authorization lives in
Jason's canonical governing ledgers and must be revalidated at dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .import_activity import ImportSpecification
from .import_authorization import ImportAuthorizationError

AAD = b"project-jason:constant-contact:import-work:v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WORK_ID = re.compile(r"^[A-Za-z0-9_-]{25,64}$")
MAX_WORK_SECONDS = 3600
# Preserve enough encrypted evidence to reconcile asynchronous imports after
# approval expiry; this does NOT extend execution or approval authority.
MAX_RECONCILIATION_SECONDS = 172800


@dataclass(frozen=True)
class StoredImportWork:
    work_id: str
    requester_id: str
    account_binding_sha256: str
    suppression_receipt_sha256: str
    specification: ImportSpecification
    approval_id: str | None = None


class EncryptedImportWorkStore:
    def __init__(self, path: Path, key: bytes, *, clock=time.time):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ImportAuthorizationError("Protected AES-256 work encryption key required")
        self.path, self.key, self.clock = Path(path), bytes(key), clock

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.path.is_symlink():
            raise ImportAuthorizationError("Import work database cannot be a symlink")
        if self.path.exists() and (
            not self.path.is_file() or stat.S_IMODE(self.path.stat().st_mode) & 0o077
        ):
            raise ImportAuthorizationError("Import work database permissions unsafe")
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        os.chmod(self.path, 0o600)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS import_work("
            "work_id TEXT PRIMARY KEY, expires_at INTEGER NOT NULL,"
            "reconcile_until INTEGER NOT NULL, ciphertext BLOB NOT NULL)"
        )
        return connection

    def _encrypt(self, work: StoredImportWork) -> bytes:
        spec = work.specification
        if (
            not work.requester_id or not WORK_ID.fullmatch(work.work_id)
            or not HEX64.fullmatch(work.account_binding_sha256)
            or not HEX64.fullmatch(work.suppression_receipt_sha256)
            or not HEX64.fullmatch(spec.sha256)
            or not HEX64.fullmatch(spec.preview_digest)
            or not 1 <= spec.contact_count <= 25
            or len(spec.list_ids) == 0
            or not isinstance(spec.payload, dict)
            or len(spec.payload.get("import_data", [])) != spec.contact_count
        ):
            raise ImportAuthorizationError("Import work manifest invalid")
        # Imported raw contact records are encrypted; only immutable digests
        # and the approved provider activity ID appear in other stores.
        record = {
            "requester_id": work.requester_id,
            "account_binding_sha256": work.account_binding_sha256,
            "suppression_receipt_sha256": work.suppression_receipt_sha256,
            "specification": {
                "payload": spec.payload, "sha256": spec.sha256,
                "contact_count": spec.contact_count,
                "list_ids": list(spec.list_ids),
                "preview_digest": spec.preview_digest,
            },
            "approval_id": work.approval_id,
        }
        raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > 3_900_000:
            raise ImportAuthorizationError("Import work record exceeds safe limit")
        nonce = os.urandom(12)
        return nonce + AESGCM(self.key).encrypt(nonce, raw, AAD + work.work_id.encode())

    def _decrypt(self, work_id: str, blob: bytes) -> StoredImportWork:
        try:
            raw = AESGCM(self.key).decrypt(
                blob[:12], blob[12:], AAD + work_id.encode(),
            )
            values = json.loads(raw)
            spec_data = values["specification"]
            spec = ImportSpecification(
                payload=spec_data["payload"], sha256=spec_data["sha256"],
                contact_count=spec_data["contact_count"],
                list_ids=tuple(spec_data["list_ids"]),
                preview_digest=spec_data["preview_digest"],
            )
            work = StoredImportWork(
                work_id=work_id, requester_id=values["requester_id"],
                account_binding_sha256=values["account_binding_sha256"],
                suppression_receipt_sha256=values["suppression_receipt_sha256"],
                specification=spec, approval_id=values["approval_id"],
            )
            # Also verify stored payload has not drifted from the original
            # canonical digest, even after an implementation upgrade.
            from hashlib import sha256
            payload_digest = sha256(json.dumps(
                spec.payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
            if payload_digest != spec.sha256:
                raise ValueError("Import payload digest mismatch")
            return work
        except Exception:
            raise ImportAuthorizationError("Encrypted import work unavailable or invalid") from None

    def create(
        self, *, requester_id: str, specification: ImportSpecification,
        account_binding_sha256: str, suppression_receipt_sha256: str,
    ) -> StoredImportWork:
        work = StoredImportWork(
            work_id=secrets.token_urlsafe(24), requester_id=requester_id,
            account_binding_sha256=account_binding_sha256,
            suppression_receipt_sha256=suppression_receipt_sha256,
            specification=specification,
        )
        blob = self._encrypt(work)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO import_work VALUES (?,?,?,?)",
                (work.work_id, int(self.clock()) + MAX_WORK_SECONDS,
                 int(self.clock()) + MAX_RECONCILIATION_SECONDS, blob),
            )
            db.execute("COMMIT")
        return work

    def _load(self, *, work_id: str, requester_id: str,
              reconciliation_only: bool) -> StoredImportWork:
        if not WORK_ID.fullmatch(work_id) or not requester_id:
            raise ImportAuthorizationError("Exact authorized work identifier required")
        with self._connect() as db:
            row = db.execute(
                "SELECT expires_at, reconcile_until, ciphertext FROM import_work WHERE work_id=?",
                (work_id,),
            ).fetchone()
        if not row or (row[1] if reconciliation_only else row[0]) <= int(self.clock()):
            raise ImportAuthorizationError("Import work expired or unavailable")
        work = self._decrypt(work_id, row[2])
        if work.requester_id != requester_id:
            raise ImportAuthorizationError("Requester is not the import work owner")
        return work

    def load_for_requester(self, *, work_id: str, requester_id: str) -> StoredImportWork:
        return self._load(work_id=work_id, requester_id=requester_id,
                          reconciliation_only=False)

    def load_for_reconciliation(self, *, work_id: str, requester_id: str) -> StoredImportWork:
        return self._load(work_id=work_id, requester_id=requester_id,
                          reconciliation_only=True)

    def attach_approval(self, *, work_id: str, requester_id: str,
                        approval_id: str) -> StoredImportWork:
        if not approval_id.startswith("planapproval-"):
            raise ImportAuthorizationError("Canonical plan issuer reference required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT expires_at, reconcile_until, ciphertext FROM import_work WHERE work_id=?",
                (work_id,),
            ).fetchone()
            if not row or row[0] <= int(self.clock()):
                raise ImportAuthorizationError("Import work expired or unavailable")
            original = self._decrypt(work_id, row[2])
            if original.requester_id != requester_id or original.approval_id:
                raise ImportAuthorizationError("Import approval already bound or requester invalid")
            from dataclasses import replace
            bound = replace(original, approval_id=approval_id)
            db.execute("UPDATE import_work SET ciphertext=? WHERE work_id=?",
                       (self._encrypt(bound), work_id))
            db.execute("COMMIT")
            return bound


    def list_reconcilable(self, *, limit: int = 25) -> tuple[StoredImportWork, ...]:
        """Internal read-only supervisor view; never grants approval or writes."""
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ImportAuthorizationError("Bounded import reconciliation limit required")
        with self._connect() as db:
            rows = db.execute(
                "SELECT work_id,ciphertext FROM import_work "
                "WHERE reconcile_until>? ORDER BY rowid LIMIT ?",
                (int(self.clock()), limit),
            ).fetchall()
        results = []
        for work_id, ciphertext in rows:
            work = self._decrypt(work_id, ciphertext)
            if work.approval_id:
                results.append(work)
        return tuple(results)
