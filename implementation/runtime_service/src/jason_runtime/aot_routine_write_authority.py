"""Opt-in standing authority for routine human-requested Autotask ticket work.

Only named existing ticket capabilities qualify. Provider impersonation, exact
approval recording, client checks, plan fingerprints, audit and readback remain
in force. Setting the profile off disables matching even if a durable grant
was previously provisioned.
"""

import os

from kernel.identity_authority import AuthorityGrant, PermissionMode
from orchestrator.provider_read_authority import (
    AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY,
)

AOT_ROUTINE_WRITE_PROFILE_ENV = "JASON_AOT_ROUTINE_RW_PROFILE"
AOT_ROUTINE_WRITE_PROFILE = "autotask-ticket-v1"
AOT_ROUTINE_WRITE_GRANT_ID = "grant-aot-human-routine-autotask-ticket-v1"


def configured_aot_routine_autotask_write() -> bool:
    return os.getenv(AOT_ROUTINE_WRITE_PROFILE_ENV, "").strip().casefold() == AOT_ROUTINE_WRITE_PROFILE


def ensure_aot_routine_autotask_write_authority(identity_authority, *, enabled: bool) -> bool:
    if not enabled:
        return False
    grant = AuthorityGrant(
        grant_id=AOT_ROUTINE_WRITE_GRANT_ID,
        subject_id="organization:aot",
        capability=AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.EXECUTE,
        approval_required=True,
        status="active",
    )
    existing = identity_authority.grants.get(grant.grant_id)
    if existing is None:
        identity_authority.grants.put(grant)
        return True
    if existing != grant:
        raise RuntimeError("AOT routine Autotask write grant conflicts with immutable policy")
    return False
