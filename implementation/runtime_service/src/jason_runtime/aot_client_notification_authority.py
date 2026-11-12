"""Explicit opt-in standing technician authority for source-approved client messages.

This is *not* a per-user grant or an alternate identity. Approval, exact source-
controlled message and contact verification remain in the normal governed path.
The organization-wide grant activates only with both intentional feature flags
and the already approved provider workflow profile. Disabled by default.
"""
from __future__ import annotations

import os

from kernel.identity_authority import AuthorityGrant, PermissionMode
from orchestrator.provider_read_authority import (
    AOT_APPROVED_CLIENT_NOTIFICATION_POLICY,
)

AOT_CLIENT_NOTIFICATION_TECH_PROFILE_ENV = "JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE"
AOT_CLIENT_NOTIFICATION_TECH_PROFILE = "approved-workflow-technician-v1"
AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV = "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE"
AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE = "approved-workflow-client-notification-v1"
AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID = (
    "grant-aot-human-approved-client-notification-v1"
)


def configured_aot_client_notification_technician_write() -> bool:
    return (
        os.getenv(AOT_CLIENT_NOTIFICATION_TECH_PROFILE_ENV, "").strip().casefold()
        == AOT_CLIENT_NOTIFICATION_TECH_PROFILE
        and os.getenv(AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV, "").strip().casefold()
        == AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE
    )


def ensure_aot_client_notification_technician_authority(
    identity_authority, *, enabled: bool,
) -> bool:
    if not enabled:
        return False
    grant = AuthorityGrant(
        grant_id=AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID,
        subject_id="organization:aot",
        capability=AOT_APPROVED_CLIENT_NOTIFICATION_POLICY,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.EXECUTE,
        approval_required=True,
        status="active",
    )
    current = identity_authority.grants.get(grant.grant_id)
    if current is None:
        identity_authority.grants.put(grant)
        return True
    if current != grant:
        raise RuntimeError("AOT client notification technician grant conflicts with reviewed policy")
    return False
