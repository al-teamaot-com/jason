"""Exact, read-only activation guard for VulScan V2 notifications.

This module only checks an EXISTING durable playbook-autonomy approval. It does
not create approvals, grant capabilities, resolve identity by email, or enable
the production worker. Actual Teams send still uses canonical workflow and
audience authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

V2_PLAYBOOK_ID = "vulscan_patch_approval_aging"
V2_PLAYBOOK_VERSION = "2.0.0"
V2_POLICY_ID = "playbook-autonomy:vulscan_patch_approval_aging"
V2_TEAMS_CAPABILITY = "communication.teams.message.send"


@dataclass
class VulscanV2OwnerPromotionGate:
    approval_store: Any
    # Sourced from existing trusted owner-role registry; no caller assertions.
    owner_authorized: Callable[[str], bool]
    recipient_identity_ready: Callable[[], bool]
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def __call__(self) -> bool:
        current = self.now()
        if current.tzinfo is None:
            return False
        try:
            record = self.approval_store.find_scope_approved(
                playbook_id=V2_PLAYBOOK_ID,
                playbook_version=V2_PLAYBOOK_VERSION,
                policy_id=V2_POLICY_ID,
                required_capabilities=(V2_TEAMS_CAPABILITY,),
                now=current,
            )
            if record is None:
                return False
            # Disallow broad grants in a notification-only playbook.
            if (set(record.allowed_capabilities) != {V2_TEAMS_CAPABILITY}
                    or not self.owner_authorized(record.approved_by)
                    or self.recipient_identity_ready() is not True):
                return False
            return True
        except Exception:
            # Missing, duplicate, revoked, corrupt or unavailable authority
            # is never a reason to activate communication.
            return False
