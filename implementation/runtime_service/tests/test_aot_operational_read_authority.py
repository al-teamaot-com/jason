import pytest
from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from jason_runtime.aot_operational_read_authority import (
    AOT_TECHNICIAN_READ_GRANT_ID, ensure_aot_technician_read_authority,
)
from orchestrator.provider_read_authority import AOT_TECHNICIAN_OPERATIONAL_READ_POLICY


def authority():
    return IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
    )


def test_new_standing_read_grant_is_idempotent_and_observe_only():
    service = authority()
    assert ensure_aot_technician_read_authority(service)
    assert not ensure_aot_technician_read_authority(service)
    grant = service.grants.get(AOT_TECHNICIAN_READ_GRANT_ID)
    assert grant.subject_id == "organization:aot"
    assert grant.capability == AOT_TECHNICIAN_OPERATIONAL_READ_POLICY
    assert grant.organization_id == "aot"
    assert grant.client_id is None
    assert grant.permission is PermissionMode.OBSERVE
    assert grant.approval_required is False


def test_conflicting_authority_grant_fails_closed_without_overwrite():
    service = authority()
    conflict = AuthorityGrant(
        grant_id=AOT_TECHNICIAN_READ_GRANT_ID,
        subject_id="organization:aot",capability="different.read",organization_id="aot",
        client_id=None,permission=PermissionMode.EXECUTE,approval_required=True,
    )
    service.grants.put(conflict)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_aot_technician_read_authority(service)
    assert service.grants.get(AOT_TECHNICIAN_READ_GRANT_ID) == conflict
