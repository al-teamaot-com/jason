from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)
from orchestrator.contracts import OrchestrationMode
from orchestrator.information_authorization import InformationAction
from orchestrator.service import InvocationResult
from orchestrator.sharepoint_capability_catalog import (
    SHAREPOINT_CAPABILITIES, SHAREPOINT_PROVIDER,
)
from jason_runtime.sharepoint_read_activation import (
    APPROVED_PROFILE, PROFILE_ENV, register_sharepoint_runtime_foundation,
)
from jason_runtime.sharepoint_reads import AotSharePointAuthorizingInvoker


def registries():
    return (CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
            ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()))


def invoke_registration(monkeypatch, profile="", **kwargs):
    monkeypatch.setenv(PROFILE_ENV, profile)
    capabilities, providers = registries()
    active = register_sharepoint_runtime_foundation(
        capabilities=capabilities, providers=providers,
        now=datetime(2026, 11, 19, tzinfo=timezone.utc), **kwargs)
    return active, capabilities, providers


def test_profile_off_has_no_registration_or_provider_mutation(monkeypatch):
    active, capabilities, providers=invoke_registration(monkeypatch)
    assert active is False
    with pytest.raises(Exception):
        providers.get(SHAREPOINT_PROVIDER)
    for name in SHAREPOINT_CAPABILITIES:
        with pytest.raises(Exception):
            capabilities.get(capability_name=name, version="1.0")


def test_profile_on_without_complete_app_identity_fails_closed(monkeypatch):
    with pytest.raises(PermissionError):
        invoke_registration(monkeypatch, APPROVED_PROFILE,
                            app_boundary_approved=True,
                            app_credential_present=False,
                            site_registry_present=True)


def test_unknown_profile_fails_closed(monkeypatch):
    with pytest.raises(PermissionError):
        invoke_registration(monkeypatch, "sharepoint-unrestricted-writes")


def test_exact_profile_with_full_identity_evidence_registers_only_four_reads(monkeypatch):
    active, capabilities, providers = invoke_registration(
        monkeypatch, APPROVED_PROFILE,
        app_boundary_approved=True,
        app_credential_present=True, site_registry_present=True)
    assert active
    assert providers.get(SHAREPOINT_PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE
    for name in SHAREPOINT_CAPABILITIES:
        cap=capabilities.get(capability_name=name,version="1.0")
        assert cap.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert cap.metadata["read_only"]=="true"


@dataclass(frozen=True)
class FakeRequest:
    principal_id: str="verified-owner"
    organization_id: str="aot"
    client_id: str | None=None
    requester_kind: str="human"
    permission_mode: str="observe"
    authority_allowed: bool=True
    authority_context_id: str="authority-context"
    orchestration_mode: OrchestrationMode=OrchestrationMode.EXECUTE
    capability_name: str="knowledge.library.search"


class Binding:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        return object() if jason_identity_id=="verified-owner" else None


class Delegate:
    def __init__(self):
        self.calls=[]
    def invoke(self, *, request, resolution):
        self.calls.append((request, resolution))
        return InvocationResult(output={"provider":"microsoft_graph", "data":{"items":[]}})


def test_owner_read_uses_service_principal_without_delegated_token():
    delegate=Delegate()
    invoker=AotSharePointAuthorizingInvoker(
        delegate=delegate, approved_owner_ids=frozenset({"verified-owner"}),
        original_identity_bindings=Binding(), app_service_principal_id="jason-app-sp")
    result=invoker.invoke(
        request=FakeRequest(),
        resolution=SimpleNamespace(selected_provider_id=SHAREPOINT_PROVIDER))
    assert delegate.calls[0][0].principal_id=="jason-app-sp"
    assert delegate.calls[0][0].requester_kind=="service"
    assert result.information_authorization.decisions[InformationAction.RELEASE].allowed


def test_unapproved_human_is_denied_before_provider():
    delegate=Delegate()
    invoker=AotSharePointAuthorizingInvoker(
        delegate=delegate, approved_owner_ids=frozenset({"verified-owner"}),
        original_identity_bindings=Binding(), app_service_principal_id="jason-app-sp")
    with pytest.raises(PermissionError):
        invoker.invoke(
            request=FakeRequest(principal_id="random-user"),
            resolution=SimpleNamespace(selected_provider_id=SHAREPOINT_PROVIDER))
    assert delegate.calls==[]


def test_content_policy_denies_release_even_to_owner():
    delegate=Delegate()
    invoker=AotSharePointAuthorizingInvoker(
        delegate=delegate, approved_owner_ids=frozenset({"verified-owner"}),
        original_identity_bindings=Binding(), app_service_principal_id="jason-app-sp")
    result=invoker.invoke(
        request=FakeRequest(capability_name="knowledge.document.content.read"),
        resolution=SimpleNamespace(selected_provider_id=SHAREPOINT_PROVIDER))
    assert not result.information_authorization.decisions[InformationAction.RELEASE].allowed
