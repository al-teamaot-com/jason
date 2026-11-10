"""Native V5 release evidence must independently bind signed regular Owner OID."""
from types import SimpleNamespace
from uuid import UUID

import pytest

from tools.release_mobile_approval_consumer import _authorized_policy_owner_identity
from implementation.runtime_service.tests.test_v5_service_originated_owner_release import v5
from implementation.runtime_service.tests.test_admin_separated_release_roles import (
    ADMIN, REGULAR, TENANT, binding,
)
from jason_runtime.mobile_release_approval import read_mobile_release_policy

OWNER_ROLE = "person-al"


def owner(oid, *, status="active", identity_type="human"):
    return SimpleNamespace(
        identity_id="person-entra-" + UUID(oid).hex,
        status=status, identity_type=identity_type, organization_id="aot",
    )


def require(tmp_path, oid=REGULAR, *, bound=None, actor=None):
    policy = read_mobile_release_policy(v5(tmp_path))
    return _authorized_policy_owner_identity(
        binding=bound or binding(oid),
        owner=actor or owner(oid),
        policy=policy, receipt_identity_id=OWNER_ROLE,
    )


def test_native_consumer_accepts_exact_signed_regular_owner_policy(tmp_path):
    assert require(tmp_path) == OWNER_ROLE


@pytest.mark.parametrize("oid", [ADMIN])
def test_native_consumer_rejects_admin_substitution(tmp_path, oid):
    with pytest.raises(PermissionError):
        require(tmp_path, oid=oid)


@pytest.mark.parametrize("bound", [
    binding(REGULAR, client="1158"),
    binding(REGULAR, status="disabled"),
    binding(REGULAR, identity=OWNER_ROLE),
])
def test_native_consumer_rejects_client_scoped_disabled_or_alias_binding(tmp_path, bound):
    with pytest.raises(PermissionError):
        require(tmp_path, bound=bound)


@pytest.mark.parametrize("actor", [
    owner(REGULAR, status="disabled"),
    owner(REGULAR, identity_type="service"),
])
def test_native_consumer_rejects_inactive_or_service_owner_identity(tmp_path, actor):
    with pytest.raises(PermissionError):
        require(tmp_path, actor=actor)
