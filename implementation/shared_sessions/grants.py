"""Isolated non-executing, single-use grant verifier prototype.

NOT production authority: caller-supplied secret, local memory only, no issuer
authentication, no durable replay store, no Microsoft Teams integration.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import binascii
import hashlib
import hmac
import json
import secrets
from threading import RLock
from typing import Callable

@dataclass(frozen=True)
class GrantScope:
    tenant_id: str
    client_id: str
    target_id: str
    technician_id: str
    ticket_id: str
    transport_id: str
    command_digest: str

    def as_dict(self) -> dict[str, str]:
        values = vars(self)
        if any(type(value) is not str or not value.strip() for value in values.values()):
            raise ValueError('invalid grant scope')
        if len(self.command_digest) != 64 or any(c not in '0123456789abcdef' for c in self.command_digest):
            raise ValueError('command digest must be sha256 hex')
        return dict(values)

class SingleUseGrantPrototype:
    """Server-side demonstration; NOT integrated into Jason runtime or capable of execution."""
    def __init__(self, key: bytes, *, now: Callable[[], datetime] | None = None):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError('grant signing key must be at least 32 bytes')
        self._key = key
        self._clock = now or (lambda: datetime.now(timezone.utc))
        self._used: set[str] = set()
        self._revoked: set[str] = set()
        self._lock = RLock()

    def _time(self) -> int:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError('clock must be timezone-aware')
        return int(now.timestamp())

    def issue_for_test(self, scope: GrantScope, lifetime_seconds: int = 60) -> str:
        """Test fixture only. Production grant issuance requires verified approval provider."""
        if type(lifetime_seconds) is not int or not 0 < lifetime_seconds <= 300:
            raise ValueError('invalid expiry')
        body = {'v': 1, 'scope': scope.as_dict(), 'exp': self._time() + lifetime_seconds,
                'nonce': secrets.token_hex(16)}
        payload = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
        signature = hmac.new(self._key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload).decode().rstrip('=') + '.' + base64.urlsafe_b64encode(signature).decode().rstrip('=')

    def _decode(self, token: str) -> tuple[dict, bytes]:
        if type(token) is not str or len(token) > 4096 or token.count('.') != 1:
            raise ValueError('invalid grant token')
        raw, mac = token.split('.')
        def decode(value: str) -> bytes:
            return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        payload, signature = decode(raw), decode(mac)
        if not hmac.compare_digest(hmac.new(self._key, payload, hashlib.sha256).digest(), signature):
            raise ValueError('invalid grant signature')
        body = json.loads(payload)
        if not isinstance(body, dict) or body.get('v') != 1 or not isinstance(body.get('scope'), dict):
            raise ValueError('invalid grant schema')
        return body, payload

    def consume(self, token: str, expected_scope: GrantScope) -> bool:
        """Fail closed. Atomic, single-use consumption for this process only."""
        try:
            body, payload = self._decode(token)
            nonce = body['nonce']
            exp = body['exp']
            if type(nonce) is not str or len(nonce) != 32 or type(exp) is not int:
                return False
            if body['scope'] != expected_scope.as_dict() or self._time() >= exp:
                return False
            digest = hashlib.sha256(payload).hexdigest()
            with self._lock:
                if digest in self._used or digest in self._revoked:
                    return False
                self._used.add(digest)
                return True
        except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
            return False

    def revoke(self, token: str) -> bool:
        """Revoke an issued unconsumed token within this ephemeral test process."""
        try:
            _, payload = self._decode(token)
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
            return False
        digest = hashlib.sha256(payload).hexdigest()
        with self._lock:
            self._revoked.add(digest)
            return True
