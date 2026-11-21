"""Two dedicated AES-256-GCM keys from Jason's governed secret boundary.

The integration parent supplies a callable that invokes the existing
OpenBaoSecretResolver under a J-Assist-only AppRole and ConnectorContext.
No environment, in-repository key, plaintext disk or fallback generator
is accepted. A missing permission/key prevents the pilot from starting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping
import base64
import binascii
import hmac


@dataclass(frozen=True, repr=False)
class JAssistAesKeys:
    session: bytes
    evidence: bytes

    def __post_init__(self):
        if (type(self.session) is not bytes or len(self.session) != 32
                or type(self.evidence) is not bytes or len(self.evidence) != 32
                or hmac.compare_digest(self.session, self.evidence)):
            raise ValueError("two independent J-Assist 256-bit keys required")


class GovernedJAssistKeyBroker:
    def __init__(self, *, resolve: Callable[[str], Mapping[str, str]]):
        if not callable(resolve):
            raise ValueError("existing governed OpenBao resolver is required")
        self._resolve = resolve

    @staticmethod
    def _key(result, field):
        if not isinstance(result, Mapping) or set(result) != {field}:
            raise PermissionError("unexpected OpenBao key contract")
        value = result.get(field)
        if not isinstance(value, str) or len(value) != 44:
            raise PermissionError("invalid encrypted-evidence key")
        try:
            raw = base64.b64decode(value, validate=True)
            if base64.b64encode(raw).decode("ascii") != value or len(raw) != 32:
                raise ValueError("invalid key length")
            return raw
        except (binascii.Error, ValueError) as exc:
            raise PermissionError("invalid OpenBao key encoding") from exc

    def load(self):
        try:
            session = self._key(self._resolve("jassist.session_encryption"),
                                "key_b64")
            evidence = self._key(self._resolve("jassist.evidence_encryption"),
                                 "key_b64")
            return JAssistAesKeys(session=session, evidence=evidence)
        except (PermissionError, ValueError):
            raise
        except Exception as exc:
            raise PermissionError("J-Assist scoped OpenBao key unavailable") from exc
