import pytest

from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from jason_runtime.aot_staff_internal_note_authority import (
    AOT_STAFF_INTERNAL_NOTE_GRANT_ID, AOT_STAFF_INTERNAL_NOTE_PROFILE,
    AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV,
    configured_aot_staff_internal_note_write,
    ensure_aot_staff_internal_note_authority,
)
from orchestrator.provider_read_authority import AOT_STAFF_INTERNAL_NOTE_POLICY


def authority():
    return IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
    )


def test_staff_note_profile_is_explicitly_opt_in(monkeypatch):
    monkeypatch.delenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, raising=False)
    assert not configured_aot_staff_internal_note_write()
    monkeypatch.setenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, "true")
    assert not configured_aot_staff_internal_note_write()
    monkeypatch.setenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, AOT_STAFF_INTERNAL_NOTE_PROFILE)
    assert configured_aot_staff_internal_note_write()


def test_staff_note_grant_is_idempotent_approval_required_and_exact():
    service = authority()
    assert not ensure_aot_staff_internal_note_authority(service, enabled=False)
    assert service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID) is None
    assert ensure_aot_staff_internal_note_authority(service, enabled=True)
    assert not ensure_aot_staff_internal_note_authority(service, enabled=True)
    grant = service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID)
    assert grant.subject_id == "organization:aot"
    assert grant.capability == AOT_STAFF_INTERNAL_NOTE_POLICY
    assert grant.organization_id == "aot"
    assert grant.client_id is None
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert grant.status == "active"


def test_grant_conflict_fails_closed():
    service = authority()
    conflict = AuthorityGrant(
        AOT_STAFF_INTERNAL_NOTE_GRANT_ID, "organization:aot",
        AOT_STAFF_INTERNAL_NOTE_POLICY, "aot", None,
        PermissionMode.EXECUTE, approval_required=False,
    )
    service.grants.put(conflict)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_aot_staff_internal_note_authority(service, enabled=True)
    assert service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID) == conflict
