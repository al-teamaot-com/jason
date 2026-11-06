"""Native Datto technician Web Remote access contract.

A positive decision MUST be backed by fresh Datto-origin evidence for the
actual individual signed-in technician. This module never calls Datto or
infers user permission from a shared MSP API identity, Chrome URL, or JWT.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import time
from typing import Callable

from session_gate import VerifiedTechnician

_DEVICE = re.compile(r"^[0-9]{1,24}$")
MAX_EVIDENCE_AGE_SECONDS = 30

@dataclass(frozen=True)
class DattoWebRemoteEvidence:
    user_subject: str
    tenant_id: str
    device_uid: str
    issued_at: float
    active_security_level: str
    device_visible: bool
    sites_view: bool
    devices_view: bool
    web_remote_enabled: bool
    provider_verified: bool


class DattoWebRemoteAuthorizer:
    """Require all active Datto user grants, explicitly fail closed.

    The provider evidence adapter MUST supply a real current signed-in Datto
    technician identity mapped to the trusted Entra principal. Synthetic
    evidence is acceptable only in isolated automated tests.
    """
    def __init__(
        self,
        *,
        evidence_for: Callable[[VerifiedTechnician, str], DattoWebRemoteEvidence | None],
        clock: Callable[[], float] = time.time,
    ):
        self._evidence_for = evidence_for
        self._clock = clock

    def __call__(self, technician: VerifiedTechnician, device_uid: str) -> bool:
        if not isinstance(technician, VerifiedTechnician):
            return False
        if not isinstance(device_uid, str) or not _DEVICE.fullmatch(device_uid):
            return False
        try:
            proof = self._evidence_for(technician, device_uid)
        except Exception:
            return False
        if not isinstance(proof, DattoWebRemoteEvidence):
            return False
        if (proof.user_subject != technician.subject
                or proof.tenant_id != technician.tenant_id
                or proof.device_uid != device_uid
                or not proof.active_security_level.strip()
                or type(proof.issued_at) not in (int, float)
                or not 0 <= self._clock() - proof.issued_at <= MAX_EVIDENCE_AGE_SECONDS):
            return False
        return all((
            proof.provider_verified is True,
            proof.device_visible is True,
            proof.sites_view is True,
            proof.devices_view is True,
            proof.web_remote_enabled is True,
        ))
