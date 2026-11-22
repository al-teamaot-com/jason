"""Bounded runtime registration tests: no live Graph, OpenBao or group writes."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.microsoft_group_admin_activation import (
    PROFILE, PROFILE_ENV, register_group_admin_foundation,
)
from orchestrator.microsoft_group_admin_catalog import (
    AOT_PILOT_CLIENT_ID, AOT_PILOT_OWNER_PRINCIPAL_ID,
    GROUP_ADMIN_CAPABILITIES, GROUP_ADMIN_PROVIDER,
    require_group_pilot_client_scope,
)


def _regs():
    return (CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
            ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()))


def test_default_disabled_and_without_active_provider_or_mcp_actions():
    c, p = _regs()
    status = register_group_admin_foundation(
        capabilities=c, providers=p, now=datetime.now(timezone.utc), profile=None)
    assert status.enabled is False
    assert p.get(GROUP_ADMIN_PROVIDER).lifecycle_status.value == "planned"
    for name in GROUP_ADMIN_CAPABILITIES:
        item = c.get(capability_name=name, version="1.0")
        assert item.lifecycle_status.value == "building"
        assert item.metadata["mcp_action_enabled"] == "true"
        assert item.approval.required and item.maximum_attempts == 1


def test_exact_profile_activates_only_approved_group_capabilities():
    c, p = _regs()
    status = register_group_admin_foundation(
        capabilities=c, providers=p, now=datetime.now(timezone.utc), profile=PROFILE)
    assert status.enabled
    assert p.get(GROUP_ADMIN_PROVIDER).lifecycle_status.value == "available"
    assert p.get(GROUP_ADMIN_PROVIDER).approval_status.value == "pilot"
    assert {x.capability_name for x in c.list_all()} == GROUP_ADMIN_CAPABILITIES
    for name in GROUP_ADMIN_CAPABILITIES:
        item = c.get_current(capability_name=name)
        assert item.metadata["mcp_action_enabled"] == "true"
        assert item.metadata["conversation_authenticated_imperative_is_approval"] == "false"
        assert item.tenant_isolation_required and item.client_isolation_required


def test_unreviewed_profile_fails_closed():
    c,p = _regs()
    with pytest.raises(PermissionError, match="UNAPPROVED_ACTIVATION"):
        register_group_admin_foundation(
            capabilities=c, providers=p, now=datetime.now(timezone.utc),
            profile="wildcard-all-tenant-write")


@pytest.mark.parametrize("principal,client,organization,success", [
    (AOT_PILOT_OWNER_PRINCIPAL_ID, None, "aot", True),
    (AOT_PILOT_OWNER_PRINCIPAL_ID, AOT_PILOT_CLIENT_ID, "aot", True),
    (AOT_PILOT_OWNER_PRINCIPAL_ID, "other-client", "aot", False),
    ("person-entra-00000000000040008000000000000000", None, "aot", False),
    (AOT_PILOT_OWNER_PRINCIPAL_ID, None, "other-org", False),
])
def test_exact_aot_client_context_does_not_widen_other_tenants(principal, client, organization, success):
    if success:
        assert require_group_pilot_client_scope(
            capability_name="identity.group.create", principal_id=principal,
            organization_id=organization, bound_client_id=client) == AOT_PILOT_CLIENT_ID
    else:
        with pytest.raises(PermissionError):
            require_group_pilot_client_scope(
                capability_name="identity.group.create", principal_id=principal,
                organization_id=organization, bound_client_id=client)


def test_unrelated_capability_keeps_original_bound_client():
    assert require_group_pilot_client_scope(
        capability_name="service.ticket.update", principal_id="anything",
        organization_id="anywhere", bound_client_id=None) is None
