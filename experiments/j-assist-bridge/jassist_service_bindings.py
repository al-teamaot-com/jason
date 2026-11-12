"""Governed J-Assist runtime binding, intentionally inert without live services.

Connect the configuration read contract and independently verified Datto
security-level evidence to the existing Jason SessionGate. Neither the
browser nor the shared API key chooses the required security level.

The deployment integrator must provide existing, governed Jason services
rather than constructing a second credential or policy authority here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from datto_administrator_authority import (
    DattoSecurityLevelEvidence, DattoSecurityLevelScreenAuthorizer,
)
from jassist_access_policy import FileBackedJAssistPolicyReader
from session_gate import SessionGate, VerifiedTechnician


@dataclass(frozen=True)
class JAssistServiceBindings:
    # Server-owned path published by Jason's governed configuration manager.
    access_policy_path: Path
    # Pinned, independently verified AOT Datto account identifier.
    datto_account_uid: str
    # Production Entra/Jason identity resolver; no client-supplied claims.
    identity: Callable[[object], VerifiedTechnician]
    # Trusted provider-backed Datto assigned-security-level lookup.
    datto_level_evidence: Callable[[VerifiedTechnician], DattoSecurityLevelEvidence | None]
    # Trusted Datto native device-account lookup.
    datto_device_in_account: Callable[[str, str], bool]

    def build_session_gate(self) -> SessionGate:
        if (not isinstance(self.access_policy_path, Path)
                or not self.access_policy_path.is_absolute()
                or not isinstance(self.datto_account_uid, str)
                or not self.datto_account_uid.strip()
                or not all(callable(x) for x in (
                    self.identity, self.datto_level_evidence,
                    self.datto_device_in_account,
                ))):
            raise ValueError("live governed J-Assist service bindings are unavailable")
        access = FileBackedJAssistPolicyReader(self.access_policy_path)
        # Validate the current trusted snapshot, not only construction.
        policy = access()
        if policy.aot_account_uid != self.datto_account_uid:
            raise ValueError("J-Assist settings and Datto account differ")
        authorization = DattoSecurityLevelScreenAuthorizer(
            aot_account_uid=self.datto_account_uid,
            access_policy_for=access,
            evidence_for=self.datto_level_evidence,
            device_in_account=self.datto_device_in_account,
        )
        return SessionGate(identity=self.identity, can_read_datto_device=authorization)


def prepare_live_bindings(*, settings_path: Path | None,
                          datto_account_uid: str | None,
                          identity: Callable | None,
                          datto_level_evidence: Callable | None,
                          datto_device_in_account: Callable | None) -> SessionGate:
    """Fail closed until the real Jason services have been supplied."""
    return JAssistServiceBindings(settings_path, datto_account_uid,
                                  identity, datto_level_evidence,
                                  datto_device_in_account).build_session_gate()
