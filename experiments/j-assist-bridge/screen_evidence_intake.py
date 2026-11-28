"""Fail-closed image evidence receipt contract for preproduction J-Assist.

Not a live transport. A trusted ingress must authenticate the caller, perform
provider-native authorization and invoke a genuine DLP/review policy before
this class may accept an image. There is deliberately NO default accept-all.
Evidence remains in process memory and cannot be used in production.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from threading import RLock
from typing import Callable

from session_gate import Denied, SessionGate, VerifiedTechnician

MAX_IMAGE_BYTES = 1024 * 1024
MAX_IN_MEMORY_IMAGES = 32  # bounded preproduction storage; NOT production persistence
NONCE_RETENTION_SECONDS = 300  # at least the maximum governed session lifetime
PNG_MAGIC = bytes.fromhex("89504e470d0a1a0a")
JPEG_MAGIC = bytes.fromhex("ffd8ff")


@dataclass(frozen=True)
class AcceptedScreen:
    """A policy-approved image, returned by the trusted content reviewer."""
    image: bytes
    reviewer_id: str
    policy_version: str


@dataclass(frozen=True)
class ScreenReceipt:
    receipt_id: str
    session_id: str
    device_uid: str
    subject: str
    image_sha256: str
    bytes_accepted: int
    accepted_at: float
    expires_at: float
    content_kind: str = "screenshot"
    analyzed_by_model: bool = False


class ScreenEvidenceIntake:
    """Preproduction-only bounded in-memory image intake with strict scopes."""

    def __init__(
        self, *,
        gate: SessionGate,
        review_content: Callable[[bytes], AcceptedScreen],
        clock: Callable[[], float] = time.time,
    ):
        if not callable(review_content):
            raise ValueError("review callback required")
        self._gate = gate
        self._review = review_content
        self._clock = clock
        self._images: dict[str, tuple[ScreenReceipt, bytes, str]] = {}
        self._nonces: dict[tuple[str, str], float] = {}
        self._pending_nonces: set[tuple[str, str]] = set()
        self._lock = RLock()

    def _prune_locked(self, now: float) -> int:
        old = [rid for rid, (receipt, _, _) in self._images.items()
               if now >= receipt.expires_at]
        for rid in old:
            self._images.pop(rid, None)
        expired_nonces = [key for key, expires in self._nonces.items()
                          if now >= expires]
        for key in expired_nonces:
            self._nonces.pop(key, None)
        return len(old)

    @staticmethod
    def _format(data: bytes) -> str:
        if data.startswith(PNG_MAGIC):
            return "image/png"
        if data.startswith(JPEG_MAGIC) and data.endswith(bytes.fromhex("ffd9")):
            return "image/jpeg"
        raise Denied("unsupported or incomplete image")

    def receive(
        self, *,
        trusted_technician: VerifiedTechnician,
        session_id: str, session_token: str, device_uid: str,
        request_nonce: str, image: bytes, declared_sha256: str,
    ) -> ScreenReceipt:
        if not isinstance(trusted_technician, VerifiedTechnician):
            raise Denied("authenticated technician required")
        if not isinstance(request_nonce, str) or not (
            16 <= len(request_nonce) <= 96 and request_nonce.isascii()
            and request_nonce.isalnum()
        ):
            raise Denied("invalid unique request nonce")
        if type(image) is not bytes or not 0 < len(image) <= MAX_IMAGE_BYTES:
            raise Denied("image size denied")
        if not isinstance(declared_sha256, str) or len(declared_sha256) != 64:
            raise Denied("missing sha256 evidence declaration")
        actual_sha256 = hashlib.sha256(image).hexdigest()
        if not hmac.compare_digest(actual_sha256, declared_sha256):
            raise Denied("image integrity mismatch")
        self._format(image)
        self._gate.authorize_read(
            trusted_context=trusted_technician, session_id=session_id,
            token=session_token, device_uid=device_uid,
        )
        key = (session_id, request_nonce)
        # The HTTP proof uses ThreadingHTTPServer. Reserve the nonce BEFORE
        # invoking a potentially slow DLP reviewer to prevent concurrent replay.
        with self._lock:
            self._prune_locked(self._clock())
            if key in self._nonces or key in self._pending_nonces:
                raise Denied("replayed image request")
            if (len(self._images) + len(self._pending_nonces)
                    >= MAX_IN_MEMORY_IMAGES):
                raise Denied("preproduction evidence capacity exhausted")
            self._pending_nonces.add(key)
        try:
            try:
                reviewed = self._review(image)
            except Exception as exc:
                raise Denied("content review unavailable or rejected") from exc
            if (not isinstance(reviewed, AcceptedScreen)
                    or not isinstance(reviewed.image, bytes)
                    or not reviewed.reviewer_id.strip()
                    or not reviewed.policy_version.strip()
                    or not 0 < len(reviewed.image) <= MAX_IMAGE_BYTES):
                raise Denied("content review denied")
            self._format(reviewed.image)
            # Revalidate AFTER potentially slow DLP review. A revoked Datto
            # permission must not leave a reviewed image accepted.
            self._gate.authorize_read(
                trusted_context=trusted_technician, session_id=session_id,
                token=session_token, device_uid=device_uid,
            )
            now = self._clock()
            receipt = ScreenReceipt(
                receipt_id=secrets.token_urlsafe(24),
                session_id=session_id, device_uid=device_uid,
                subject=trusted_technician.subject,
                image_sha256=hashlib.sha256(reviewed.image).hexdigest(),
                bytes_accepted=len(reviewed.image),
                accepted_at=now, expires_at=now + 120,
            )
            with self._lock:
                self._prune_locked(now)
                if key in self._nonces:
                    raise Denied("replayed image request")
                if len(self._images) >= MAX_IN_MEMORY_IMAGES:
                    raise Denied("preproduction evidence capacity exhausted")
                self._images[receipt.receipt_id] = (
                    receipt, reviewed.image, trusted_technician.tenant_id,
                )
                self._nonces[key] = now + NONCE_RETENTION_SECONDS
            return receipt
        finally:
            # Errors, DLP rejection and revocation release only the
            # reservation; successfully committed nonces remain replay-proof.
            with self._lock:
                self._pending_nonces.discard(key)

    def retrieve(
        self, *,
        trusted_technician: VerifiedTechnician,
        session_id: str, session_token: str, device_uid: str,
        receipt_id: str,
    ) -> tuple[ScreenReceipt, bytes]:
        self._gate.authorize_read(
            trusted_context=trusted_technician, session_id=session_id,
            token=session_token, device_uid=device_uid,
        )
        with self._lock:
            entry = self._images.get(receipt_id)
            if entry is None:
                raise Denied("unknown evidence receipt")
            receipt, image, tenant = entry
            if self._clock() >= receipt.expires_at:
                self._images.pop(receipt_id, None)
                raise Denied("evidence expired")
            if (receipt.session_id != session_id
                    or receipt.device_uid != device_uid
                    or receipt.subject != trusted_technician.subject
                    or tenant != trusted_technician.tenant_id):
                raise Denied("evidence identity or device mismatch")
            return receipt, image

    def purge_expired(self) -> int:
        with self._lock:
            return self._prune_locked(self._clock())
