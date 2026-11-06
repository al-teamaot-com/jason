"""Opt-in standing authority for AOT human-requested INTERNAL Autotask notes.

The policy is separate from broader Autotask ticket writes, is disabled by
default and does not authorize autonomous/service principals. All request
approvals, Autotask requester permissions, provider impersonation and readback
remain governed by the existing note-create capability.
"""

import os

from kernel.identity_authority import AuthorityGrant, PermissionMode
from orchestrator.provider_read_authority import AOT_STAFF_INTERNAL_NOTE_POLICY

AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV = "JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE"
AOT_STAFF_INTERNAL_NOTE_PROFILE = "internal-note-v1"
AOT_STAFF_INTERNAL_NOTE_GRANT_ID = "grant-aot-human-internal-ticket-note-v1"


def configured_aot_staff_internal_note_write() -> bool:
    return (
        os.getenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, "").strip().casefold()
        == AOT_STAFF_INTERNAL_NOTE_PROFILE
    )


def ensure_aot_staff_internal_note_authority(
    identity_authority, *, enabled: bool,
) -> bool:
    """Idempotent single scope-limited grant; no authorization when disabled."""
    if not enabled:
        return False
    grant = AuthorityGrant(
        grant_id=AOT_STAFF_INTERNAL_NOTE_GRANT_ID,
        subject_id="organization:aot",
        capability=AOT_STAFF_INTERNAL_NOTE_POLICY,
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
        raise RuntimeError(
            "AOT internal note grant conflicts with immutable policy"
        )
    return False
