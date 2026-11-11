"""Configurable Datto RMM assigned-security-level gate for J-Assist (preproduction).

An authorized Datto security-level assignment can make an enabled technician
eligible for screen assistance on an AOT-owned device; it never authorizes
PowerShell, remote control, ticket writes or other device operations.

IMPORTANT: the documented Datto account-users API does not itself expose
assigned security levels. Only a vetted server-side provider can supply proof.
The browser cannot select policy, level, account, or identity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
import time
from typing import Callable

from jassist_access_policy import JAssistDattoAccessPolicy
from session_gate import VerifiedTechnician

_DEVICE_UID = re.compile(r"^[0-9]{1,24}$")
MAX_PROOF_AGE = 30


@dataclass(frozen=True)
class DattoSecurityLevelEvidence:
    """Produced only by a trusted Datto-side assignment/identity resolver."""
    technician_subject: str
    technician_tenant: str
    account_uid: str
    datto_username: str
    # Assigned Datto security levels, NOT just the active Datto UI level.
    assigned_security_levels: tuple[str, ...]
    assignment_verified: bool
    user_enabled: bool
    provider_verified: bool
    verified_at: float


class DattoSecurityLevelScreenAuthorizer:
    """Per-request server-managed eligibility; no standing endpoint permission."""

    def __init__(
        self, *,
        aot_account_uid: str,
        access_policy_for: Callable[[], JAssistDattoAccessPolicy],
        evidence_for: Callable[[VerifiedTechnician], DattoSecurityLevelEvidence | None],
        device_in_account: Callable[[str, str], bool],
        clock: Callable[[], float] = time.time,
    ):
        if (not isinstance(aot_account_uid, str) or not aot_account_uid.strip()
                or not callable(access_policy_for) or not callable(evidence_for)
                or not callable(device_in_account) or not callable(clock)):
            raise ValueError("pinned account and trusted policy/Datto readers required")
        self._aot_account_uid = aot_account_uid
        self._access_policy_for = access_policy_for
        self._evidence_for = evidence_for
        self._device_in_account = device_in_account
        self._clock = clock

    def __call__(self, technician: VerifiedTechnician, device_uid: str) -> bool:
        return self.can_access(technician, device_uid, surface="screen_assistance")

    def can_access(self, technician: VerifiedTechnician, device_uid: str, *, surface: str) -> bool:
        if surface != "screen_assistance":
            return False
        if not isinstance(technician, VerifiedTechnician):
            return False
        if not isinstance(device_uid, str) or not _DEVICE_UID.fullmatch(device_uid):
            return False
        try:
            policy = self._access_policy_for()
            if not isinstance(policy, JAssistDattoAccessPolicy):
                return False
            # A dataclass obtained by bypassing the parser must not grant
            # authority: validate the whole snapshot again on EVERY call.
            policy = JAssistDattoAccessPolicy.from_mapping(asdict(policy))
            if not policy.enabled or policy.aot_account_uid != self._aot_account_uid:
                return False
            proof = self._evidence_for(technician)
            now = self._clock()
            if not isinstance(proof, DattoSecurityLevelEvidence):
                return False
            if (proof.technician_subject != technician.subject
                    or proof.technician_tenant != technician.tenant_id
                    or proof.account_uid != self._aot_account_uid
                    or not isinstance(proof.datto_username, str)
                    or not proof.datto_username.strip()
                    or type(proof.assigned_security_levels) is not tuple
                    or not proof.assigned_security_levels
                    or any(not isinstance(level, str) for level in proof.assigned_security_levels)
                    or policy.required_security_level not in proof.assigned_security_levels
                    or proof.assignment_verified is not True
                    or proof.user_enabled is not True
                    or proof.provider_verified is not True
                    or type(proof.verified_at) not in (float, int)
                    or not math.isfinite(proof.verified_at)
                    or not math.isfinite(now)
                    or not 0 <= now - proof.verified_at <= MAX_PROOF_AGE):
                return False
            return self._device_in_account(self._aot_account_uid, device_uid) is True
        except Exception:
            # Missing, tampered or unapproved configuration, stale membership,
            # provider outage and ambiguous account/device always deny.
            return False


# Compatibility import name only; no hard-coded Administrator policy remains.
DattoAdministratorEvidence = DattoSecurityLevelEvidence
DattoAdministratorScreenAuthorizer = DattoSecurityLevelScreenAuthorizer
