"""Preproduction-only AOT Entra group authorization for J-Assist images.

Supports one explicitly approved capability-group ID, not broad admin roles
or implicit rights in QuickBooks/other applications. Membership and account
enabled state must be verified through Graph by a SERVER-OWNED adapter,
not from browser-authored claims or an access-token group list. No live
provider connector is registered and image uploads remain disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from entra_send_authority import AOT_ENTRA_TENANT_ID
from session_gate import VerifiedTechnician

# Exact AOT Entra pilot security group created and verified by Owner 2026-11-06.
# Never change this to a display-name lookup or a browser-supplied group.
AOT_JASSIST_PILOT_GROUP_ID = "5273dd8a-1456-4985-b0a3-c00061267e26"

_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_DEVICE = re.compile(r"^[0-9]{1,24}$")


@dataclass(frozen=True)
class EntraGroupEvidence:
    """Server-validated Graph user account and membership, never self-asserted."""
    user_oid: str
    tenant_id: str
    group_id: str
    is_member: bool
    account_enabled: bool
    verified_by_graph: bool


class EntraGroupScreenAuthorizer:
    """Capability-specific image evidence gate; never an endpoint execution gate."""

    def __init__(
        self, *,
        group_id: str,
        resolve_entr_user_oid: Callable[[VerifiedTechnician], str | None],
        read_live_membership: Callable[[str, str, str], EntraGroupEvidence | None],
        device_in_aot_account: Callable[[str], bool],
    ) -> None:
        if (not isinstance(group_id, str) or
                group_id.casefold() != AOT_JASSIST_PILOT_GROUP_ID):
            raise ValueError("exact approved J-Assist group object ID required")
        if not (callable(resolve_entr_user_oid)
                and callable(read_live_membership)
                and callable(device_in_aot_account)):
            raise ValueError("all trusted identity, membership and device readers required")
        self._group_id = group_id.lower()
        self._resolve_oid = resolve_entr_user_oid
        self._membership = read_live_membership
        self._device = device_in_aot_account

    def __call__(self, technician: VerifiedTechnician, device_uid: str) -> bool:
        return self.can_access(technician, device_uid, surface="screen_assistance")

    def can_access(
        self, technician: VerifiedTechnician, device_uid: str, *, surface: str,
    ) -> bool:
        if surface != "screen_assistance":
            return False
        if not isinstance(technician, VerifiedTechnician) or technician.tenant_id != "aot":
            return False
        if not isinstance(device_uid, str) or not _DEVICE.fullmatch(device_uid):
            return False
        try:
            # This mapping must be derived from the verified Entra JWT object
            # ID and canonical individual technician binding on the server.
            oid = self._resolve_oid(technician)
            if not isinstance(oid, str) or not _GUID.fullmatch(oid):
                return False
            oid = oid.lower()
            proof = self._membership(AOT_ENTRA_TENANT_ID, oid, self._group_id)
            if (not isinstance(proof, EntraGroupEvidence)
                    or proof.user_oid.lower() != oid
                    or proof.tenant_id != AOT_ENTRA_TENANT_ID
                    or proof.group_id.lower() != self._group_id
                    or proof.is_member is not True
                    or proof.account_enabled is not True
                    or proof.verified_by_graph is not True):
                return False
            # Native Datto inventory is a separate mandatory gate.
            return self._device(device_uid) is True
        except Exception:
            return False
