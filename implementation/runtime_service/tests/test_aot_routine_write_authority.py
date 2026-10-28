import pytest
from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from jason_runtime.aot_routine_write_authority import (
    AOT_ROUTINE_WRITE_GRANT_ID, AOT_ROUTINE_WRITE_PROFILE,
    AOT_ROUTINE_WRITE_PROFILE_ENV, configured_aot_routine_autotask_write,
    ensure_aot_routine_autotask_write_authority,
)
from orchestrator.provider_read_authority import AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY


def authority():
    return IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
    )


def test_opt_in_exact_profile(monkeypatch):
    monkeypatch.delenv(AOT_ROUTINE_WRITE_PROFILE_ENV, raising=False)
    assert not configured_aot_routine_autotask_write()
    monkeypatch.setenv(AOT_ROUTINE_WRITE_PROFILE_ENV, "true")
    assert not configured_aot_routine_autotask_write()
    monkeypatch.setenv(AOT_ROUTINE_WRITE_PROFILE_ENV, AOT_ROUTINE_WRITE_PROFILE)
    assert configured_aot_routine_autotask_write()


def test_enable_seeds_one_exact_approval_bound_grant_only():
    service = authority()
    assert not ensure_aot_routine_autotask_write_authority(service, enabled=False)
    assert service.grants.get(AOT_ROUTINE_WRITE_GRANT_ID) is None
    assert ensure_aot_routine_autotask_write_authority(service, enabled=True)
    assert not ensure_aot_routine_autotask_write_authority(service, enabled=True)
    grant = service.grants.get(AOT_ROUTINE_WRITE_GRANT_ID)
    assert grant.subject_id == "organization:aot"
    assert grant.capability == AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY
    assert grant.client_id is None
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True


def test_conflict_does_not_silently_widen_authority():
    service = authority()
    conflict = AuthorityGrant(
        AOT_ROUTINE_WRITE_GRANT_ID, "organization:aot",
        AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY,
        "aot", None, PermissionMode.EXECUTE, approval_required=False,
    )
    service.grants.put(conflict)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_aot_routine_autotask_write_authority(service, enabled=True)
    assert service.grants.get(AOT_ROUTINE_WRITE_GRANT_ID) == conflict
