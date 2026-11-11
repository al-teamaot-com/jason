from datetime import datetime, timezone

import pytest
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderApproval, ProviderHealth, ProviderLifecycle,
)
from orchestrator.constant_contact_capability_catalog import (
    CAPABILITIES, PROVIDER, register_foundation,
)
from jason_runtime.constant_contact_activation import (
    PROFILE_ENV, READ_PROFILE, ConstantContactActivationError,
    apply_read_from_env, apply_read_profile,
)


def registries():
    caps = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_foundation(capabilities=caps, providers=providers,
                        now=datetime(2026, 11, 9, tzinfo=timezone.utc))
    return caps, providers


def test_default_dormant(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    caps, providers = registries()
    state = apply_read_from_env(capabilities=caps, providers=providers)
    assert not state.enabled
    assert providers.get(PROVIDER).lifecycle_status is ProviderLifecycle.PLANNED
    assert providers.get(PROVIDER).health_status is ProviderHealth.UNKNOWN
    assert providers.get(PROVIDER).approval_status is ProviderApproval.PILOT
    for name in CAPABILITIES:
        assert caps.get(capability_name=name, version="1.0").lifecycle_status is CapabilityLifecycle.PILOT


def test_unknown_profile_fails_closed():
    caps, providers = registries()
    with pytest.raises(ConstantContactActivationError):
        apply_read_profile(capabilities=caps, providers=providers, profile="constant-contact-write-v1")
    assert providers.get(PROVIDER).lifecycle_status is ProviderLifecycle.PLANNED


def test_exact_profile_can_activate_only_reads():
    caps, providers = registries()
    state = apply_read_profile(capabilities=caps, providers=providers, profile=READ_PROFILE)
    assert state.enabled
    assert set(state.capability_names) == CAPABILITIES
    assert providers.get(PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE
    for name in CAPABILITIES:
        assert caps.get(capability_name=name, version="1.0").lifecycle_status is CapabilityLifecycle.ACTIVE


def test_read_invoker_denies_before_provider_execution():
    """Unauthorized requester must never cause a Constant Contact HTTP read."""
    from types import SimpleNamespace
    from unittest.mock import Mock
    from jason_runtime.constant_contact_reads import RequesterBoundConstantContactInvoker

    delegate = Mock()
    bindings = Mock()
    bindings.find_active_by_jason_identity.return_value = None
    invoker = RequesterBoundConstantContactInvoker(delegate=delegate, bindings=bindings)
    request = SimpleNamespace(
        principal_id="unapproved-technician", organization_id="aot",
        authority_allowed=True, authority_context_id="valid-context",
        permission_mode="observe", requester_kind="human",
        orchestration_mode=__import__(
            "orchestrator.contracts", fromlist=["OrchestrationMode"]
        ).OrchestrationMode.EXECUTE,
    )
    resolution = SimpleNamespace(selected_provider_id="constant_contact")

    with pytest.raises(PermissionError, match="not authorized"):
        invoker.invoke(request=request, resolution=resolution)
    delegate.invoke.assert_not_called()

    bindings.find_active_by_jason_identity.return_value = object()
    request.organization_id = "another-client"
    with pytest.raises(PermissionError, match="not authorized"):
        invoker.invoke(request=request, resolution=resolution)
    delegate.invoke.assert_not_called()
