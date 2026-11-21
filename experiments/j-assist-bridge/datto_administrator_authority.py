"""Optional J-Assist Administrator-only SCREEN authority (preproduction).

This separate, narrow owner-requested policy allows a verified, enabled
Datto Administrator security-level member to review/send a screenshot of an
AOT Datto-owned device. It does not override the Datto UI's active security
level for native remote-control execution, nor grant any endpoint action.

NOTE: GET /v2/account/users documents user identity/status, but NOT
security-level membership. A live trusted backend adapter that obtains
authoritative Administrator assignment from Datto is still REQUIRED.
No group/role claims from Chrome, Entra alone, or shared API-key rights.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time
from typing import Callable

from session_gate import VerifiedTechnician

_DEVICE_UID = re.compile(r"^[0-9]{1,24}$")
MAX_PROOF_AGE = 30


@dataclass(frozen=True)
class DattoAdministratorEvidence:
    """Produced only by a trusted Datto-side membership/identity resolver."""
    technician_subject: str
    technician_tenant: str
    account_uid: str
    datto_username: str
    # ASSIGNED level, not the currently active Datto UI security level.
    assigned_security_level: str
    administrator_assigned: bool
    user_enabled: bool
    provider_verified: bool
    verified_at: float


class DattoAdministratorScreenAuthorizer:
    """Admin membership policy; READ-ONLY screen evidence, never RMM action."""

    def __init__(
        self, *,
        aot_account_uid: str,
        evidence_for: Callable[[VerifiedTechnician], DattoAdministratorEvidence | None],
        device_in_account: Callable[[str, str], bool],
        clock: Callable[[], float] = time.time,
    ):
        if (not isinstance(aot_account_uid, str) or not aot_account_uid.strip()
                or not callable(evidence_for) or not callable(device_in_account)):
            raise ValueError("pinned account and trusted Datto resolvers required")
        self._aot_account_uid = aot_account_uid
        self._evidence_for = evidence_for
        self._device_in_account = device_in_account
        self._clock = clock

    def __call__(self, technician: VerifiedTechnician, device_uid: str) -> bool:
        return self.can_access(technician, device_uid, surface="screen_assistance")

    def can_access(
        self, technician: VerifiedTechnician, device_uid: str, *, surface: str
    ) -> bool:
        if surface != "screen_assistance":
            return False
        if not isinstance(technician, VerifiedTechnician):
            return False
        if not isinstance(device_uid, str) or not _DEVICE_UID.fullmatch(device_uid):
            return False
        try:
            proof = self._evidence_for(technician)
            now = self._clock()
            if not isinstance(proof, DattoAdministratorEvidence):
                return False
            if (proof.technician_subject != technician.subject
                    or proof.technician_tenant != technician.tenant_id
                    or proof.account_uid != self._aot_account_uid
                    or not isinstance(proof.datto_username, str)
                    or not proof.datto_username.strip()
                    or proof.assigned_security_level != "Administrator"
                    or proof.administrator_assigned is not True
                    or proof.user_enabled is not True
                    or proof.provider_verified is not True
                    or type(proof.verified_at) not in (float, int)
                    or not math.isfinite(proof.verified_at)
                    or not math.isfinite(now)
                    or not 0 <= now - proof.verified_at <= MAX_PROOF_AGE):
                return False
            # Mandatory second native check: device must actually belong to
            # the pinned AOT DRMM account, never a caller-chosen account.
            return self._device_in_account(self._aot_account_uid, device_uid) is True
        except Exception:
            # Offline, untrusted/missing membership, provider error or
            # ambiguous account/device association always denies.
            return False
