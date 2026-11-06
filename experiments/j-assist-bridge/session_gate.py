"""Preproduction J-Assist session authority boundary.

This is intentionally *not* an HTTP endpoint, bearer-auth service or deployed
integration. Trusted identity and Datto authorization must be supplied by a
future independently verified adapter. No browser-provided identity is trusted.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable

_DEVICE = re.compile(r"^[0-9]{1,24}$")
_MAX_SECONDS = 300


class Denied(PermissionError):
    """An untrusted, expired, or out-of-scope J-Assist request."""


@dataclass(frozen=True)
class VerifiedTechnician:
    """Only constructed by a trusted, server-side identity adapter."""

    subject: str
    tenant_id: str


@dataclass(frozen=True)
class SessionReceipt:
    session_id: str
    device_uid: str
    expires_at: float


@dataclass
class _Session:
    token_digest: bytes
    subject: str
    tenant_id: str
    device_uid: str
    expires_at: float
    sequence: int = 0


class SessionGate:
    """In-memory, explicit-consent, metadata-only intake.

    A verified identity and a provider-backed permission check are mandatory
    and must originate outside browser-controlled payloads. Raw screen images,
    PowerShell text, diagnostic transcripts, cookies, and secrets are prohibited
    until redaction and DLP review are separately implemented.
    """

    def __init__(
        self,
        *,
        identity: Callable[[object], VerifiedTechnician],
        can_read_datto_device: Callable[[VerifiedTechnician, str], bool],
        clock: Callable[[], float] = time.time,
    ):
        self._identity = identity
        self._authorize = can_read_datto_device
        self._clock = clock
        self._sessions: dict[str, _Session] = {}

    def _principal(self, trusted_context: object) -> VerifiedTechnician:
        principal = self._identity(trusted_context)
        if not isinstance(principal, VerifiedTechnician):
            raise Denied("trusted identity unavailable")
        if not principal.subject.strip() or not principal.tenant_id.strip():
            raise Denied("incomplete verified identity")
        return principal

    def start(
        self, *, trusted_context: object, device_uid: str, consent: bool,
        lifetime_seconds: int = 120,
    ) -> tuple[SessionReceipt, str]:
        if consent is not True:
            raise Denied("explicit consent required")
        if not isinstance(device_uid, str) or not _DEVICE.fullmatch(device_uid):
            raise Denied("invalid Datto device identity")
        if type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= _MAX_SECONDS:
            raise Denied("invalid session lifetime")
        principal = self._principal(trusted_context)
        if not self._authorize(principal, device_uid):
            raise Denied("native Datto device permission denied")
        session_id = secrets.token_urlsafe(24)
        token = secrets.token_urlsafe(32)
        expires = self._clock() + lifetime_seconds
        self._sessions[session_id] = _Session(
            token_digest=hashlib.sha256(token.encode()).digest(),
            subject=principal.subject, tenant_id=principal.tenant_id,
            device_uid=device_uid, expires_at=expires,
        )
        return SessionReceipt(session_id, device_uid, expires), token

    def _get(
        self, *, trusted_context: object, session_id: str, token: str,
        device_uid: str,
    ) -> _Session:
        principal = self._principal(trusted_context)
        entry = self._sessions.get(session_id)
        if entry is None or not isinstance(token, str):
            raise Denied("session not found")
        if not secrets.compare_digest(
            entry.token_digest, hashlib.sha256(token.encode()).digest()
        ):
            raise Denied("invalid session credential")
        if self._clock() >= entry.expires_at:
            self._sessions.pop(session_id, None)
            raise Denied("session expired")
        if (entry.subject != principal.subject or
                entry.tenant_id != principal.tenant_id or
                entry.device_uid != device_uid):
            raise Denied("session binding mismatch")
        if not self._authorize(principal, device_uid):
            self._sessions.pop(session_id, None)
            raise Denied("Datto permission revoked")
        return entry

    def acknowledge_metadata(
        self, *, trusted_context: object, session_id: str,
        token: str, device_uid: str, event: str, bytes_sent: int = 0,
    ) -> int:
        """Receipt for safe lifecycle metadata only; content is not accepted."""
        if event not in {"tab_paused", "tab_resumed", "heartbeat"}:
            raise Denied("unsupported session event")
        if bytes_sent != 0:
            raise Denied("content intake is disabled")
        entry = self._get(
            trusted_context=trusted_context, session_id=session_id,
            token=token, device_uid=device_uid,
        )
        entry.sequence += 1
        return entry.sequence

    def stop(
        self, *, trusted_context: object, session_id: str,
        token: str, device_uid: str,
    ) -> None:
        self._get(
            trusted_context=trusted_context, session_id=session_id,
            token=token, device_uid=device_uid,
        )
        self._sessions.pop(session_id, None)

    def expire(self) -> int:
        now = self._clock()
        expired = [sid for sid, s in self._sessions.items() if now >= s.expires_at]
        for sid in expired:
            self._sessions.pop(sid, None)
        return len(expired)
