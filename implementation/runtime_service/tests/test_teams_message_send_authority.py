import pytest
from kernel.identity_authority import (
    AuthorityGrant,
    IdentityAuthorityService,
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)
from jason_runtime.teams_message_send import (
    CAPABILITY,
    EXECUTE_GRANT_ID,
    PROFILE,
    PROFILE_ENV,
    configured_teams_message_send,
    ensure_authority,
)


def authority():
    return IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
    )


def test_opt_in_exact_profile(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    assert not configured_teams_message_send()
    monkeypatch.setenv(PROFILE_ENV, "true")
    assert not configured_teams_message_send()
    monkeypatch.setenv(PROFILE_ENV, PROFILE)
    assert configured_teams_message_send()


# Regression: an authority-store/runtime rebuild must recreate the exact
# profile-approved grant without broadening approval or provider authority.
def test_enable_seeds_one_exact_approval_bound_grant_only():
    service = authority()
    assert not ensure_authority(service, enabled=False)
    assert service.grants.get(EXECUTE_GRANT_ID) is None
    assert ensure_authority(service, enabled=True)
    assert not ensure_authority(service, enabled=True)
    grant = service.grants.get(EXECUTE_GRANT_ID)
    assert grant.subject_id == "organization:aot"
    assert grant.capability == CAPABILITY
    assert grant.organization_id == "aot"
    assert grant.client_id is None
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert grant.status == "active"


def test_conflict_does_not_silently_widen_authority():
    service = authority()
    conflict = AuthorityGrant(
        EXECUTE_GRANT_ID,
        "organization:aot",
        CAPABILITY,
        "aot",
        None,
        PermissionMode.EXECUTE,
        approval_required=False,
    )
    service.grants.put(conflict)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_authority(service, enabled=True)
    assert service.grants.get(EXECUTE_GRANT_ID) == conflict
