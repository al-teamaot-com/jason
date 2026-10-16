"""Non-executing companion handshake and targeting contract.

No endpoint control, shell execution, agent installation or network calls.
The real companion must enforce signed and durable owner-approved authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class CompanionIdentity:
    tenant_id: str
    client_id: str
    datto_device_uid: str
    hostname: str
    installation_id: str
    public_key_fingerprint: str
    platform: str

    def __post_init__(self):
        if any(type(v) is not str or not v.strip() for v in vars(self).values()):
            raise ValueError('incomplete companion identity')
        if self.platform not in ('windows', 'linux'):
            raise ValueError('unsupported companion platform')

@dataclass(frozen=True)
class CompanionHandshake:
    identity: CompanionIdentity
    issued_at: datetime
    expires_at: datetime
    nonce: str
    authenticated: bool
    tenant_binding_verified: bool
    device_binding_verified: bool
    key_proof_verified: bool
    engineering_only: bool = True

    def check(self, *, expected: CompanionIdentity, now: datetime | None = None) -> bool:
        stamp = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None or self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            return False
        if self.identity != expected or type(self.nonce) is not str or len(self.nonce) < 16:
            return False
        if any(type(v) is not bool for v in (self.authenticated,self.tenant_binding_verified,
                  self.device_binding_verified,self.key_proof_verified,self.engineering_only)):
            return False
        if not all((self.authenticated,self.tenant_binding_verified,
                    self.device_binding_verified,self.key_proof_verified,self.engineering_only)):
            return False
        if not self.issued_at <= stamp < self.expires_at:
            return False
        if (self.expires_at-self.issued_at).total_seconds() > 300:
            return False
        return True
