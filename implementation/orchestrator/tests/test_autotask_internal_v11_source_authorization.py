"""AOT internal v11 governed reads use active Entra/JKD-001, not Graph email.

Tests run with zero provider network and never change existing v10 semantics.
All other internal/external disclosure restrictions remain fail-closed.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from connectors.autotask.impersonating_connector import AUTOTASK_REQUESTER_AUTH_MODE_ENV
from orchestrator.autotask_information_authorizer import (
    AutotaskImpersonationInformationAuthorizer,
)
from orchestrator.information_authorization import (
    InformationAction, InformationHandlingClass,
)
from orchestrator.provider_read_capability_catalog import (
    SERVICE_ENTITY_READ, SERVICE_ENTITY_SEARCH, SERVICE_TICKET_COUNT,
    SERVICE_TICKET_READ, SERVICE_TICKET_SEARCH,
)
from test_autotask_information_authorizer import _Delegate, _request, _resolution


V10 = "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10"
V11 = "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"
JIT = "person-entra-" + "a" * 32


class BindingResolver:
    def __init__(self, *, active=True, client=None, matching=True):
        self.binding = SimpleNamespace(
            jason_identity_id=JIT if matching else "person-different",
            status="active" if active else "disabled",
            client_id=client,
            email_address=None,  # Live directory lookup may be unavailable.
        )

    def find_active_by_jason_identity(self, *, jason_identity_id):
        return self.binding


def evaluated(capability, *, request=None, raw=None, enriched=None, content=None):
    request = request or _request(capability, principal_id=JIT)
    return AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(
            content or {"provider": "autotask", "data": {"items": [{"id": 101}]}}
        ),
        bindings=enriched,
        internal_bindings=raw,
    ).invoke(request=request, resolution=_resolution(capability))


@pytest.fixture(autouse=True)
def mode(monkeypatch):
    monkeypatch.setenv(AUTOTASK_REQUESTER_AUTH_MODE_ENV, "jason_managed")
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V11)


@pytest.mark.parametrize("capability", [
    SERVICE_TICKET_COUNT, SERVICE_TICKET_SEARCH, SERVICE_TICKET_READ,
    SERVICE_ENTITY_SEARCH, SERVICE_ENTITY_READ,
])
def test_aot_internal_v11_active_binding_allows_governed_source_release_without_graph(
    capability,
):
    # Live Microsoft/Jason binding is active, human authority is positive, no
    # customer client binding. Graph enrichment unavailable in this fixture.
    invocation = evaluated(capability, raw=BindingResolver(), enriched=None)
    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is True
    assert "aot_internal_active_entra_binding" in release.authorization_basis
    assert "jkd001_authority_context" in release.authorization_basis
    assert "not_provider_native_impersonation" in release.authorization_basis


def test_legacy_v10_keeps_directory_enriched_fail_closed_rule(monkeypatch):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V10)
    invocation = evaluated(SERVICE_TICKET_SEARCH, raw=BindingResolver(), enriched=None)
    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


@pytest.mark.parametrize("candidate", [
    _request(SERVICE_TICKET_SEARCH, principal_id=JIT, authority_allowed=False),
    _request(SERVICE_TICKET_SEARCH, principal_id=JIT, authority_context_id=None),
    _request(SERVICE_TICKET_SEARCH, principal_id=JIT, permission_mode="execute"),
    _request(SERVICE_TICKET_SEARCH, principal_id=JIT, requester_kind="service"),
    replace(_request(SERVICE_TICKET_SEARCH, principal_id=JIT), client_id="customer-100"),
    replace(_request(SERVICE_TICKET_SEARCH, principal_id=JIT), organization_id="other-org"),
])
def test_internal_identity_never_overrides_missing_jkd001_or_customer_scope(candidate):
    invocation = evaluated(SERVICE_TICKET_SEARCH, request=candidate, raw=BindingResolver())
    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


@pytest.mark.parametrize("raw", [
    BindingResolver(active=False),
    BindingResolver(client="customer-100"),
    BindingResolver(matching=False),
    None,
])
def test_disabled_customer_bound_mismatched_or_missing_binding_cannot_release(raw):
    invocation = evaluated(SERVICE_ENTITY_SEARCH, raw=raw)
    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


def test_caller_claiming_aot_human_does_not_override_provider_impersonation(monkeypatch):
    monkeypatch.setenv(AUTOTASK_REQUESTER_AUTH_MODE_ENV, "impersonated")
    invocation = evaluated(SERVICE_TICKET_SEARCH, raw=BindingResolver(), enriched=None)
    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


def test_sensitive_internal_source_result_remains_derived_only():
    invocation = evaluated(
        SERVICE_TICKET_SEARCH,
        raw=BindingResolver(),
        content={"provider": "autotask", "data": {
            "items": [{"id": 101, "secretKey": "DO-NOT-RELEASE"}]}},
    )
    assert invocation.information_authorization.handling_class is InformationHandlingClass.DERIVED_OUTPUT_ONLY


def test_client_bound_requester_must_not_use_internal_generic_cross_customer_read():
    request = replace(_request(SERVICE_ENTITY_SEARCH, principal_id=JIT), client_id="customer-100")
    invocation = evaluated(SERVICE_ENTITY_SEARCH, request=request, raw=BindingResolver())
    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


def test_real_durable_sqlite_binding_survives_graph_email_lookup_failure(tmp_path):
    """Actual user binding still proves AOT internal release under v11."""
    from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
    from orchestrator.teams_identity_binding_sqlite import (
        SQLiteMicrosoftIdentityBindingStore,
        DirectoryEnrichedMicrosoftIdentityBindingResolver,
    )

    class DirectoryUnavailable:
        def resolve_email(self, *, microsoft_tenant_id, microsoft_object_id):
            return None

    store = SQLiteMicrosoftIdentityBindingStore(tmp_path / "aot-identity.sqlite3")
    store.put(MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-aot",
        microsoft_object_id="object-aot-owner",
        jason_identity_id=JIT,
        client_id=None,
        email_address=None,
        status="active",
    ))
    enriched = DirectoryEnrichedMicrosoftIdentityBindingResolver(
        bindings=store, directory=DirectoryUnavailable()
    )
    assert enriched.find_active_by_jason_identity(jason_identity_id=JIT) is None
    assert store.find_active_by_jason_identity(jason_identity_id=JIT) is not None
    for capability in (SERVICE_TICKET_COUNT, SERVICE_TICKET_SEARCH, SERVICE_ENTITY_SEARCH):
        invocation = evaluated(capability, raw=store, enriched=enriched)
        release = invocation.information_authorization.require_allowed(
            InformationAction.RELEASE
        )
        assert release.allowed is True
        assert "aot_internal_active_entra_binding" in release.authorization_basis
    store.close()


def test_provider_read_builder_wires_durable_binding_to_internal_aot_only():
    import inspect
    from jason_runtime.provider_reads import build_provider_read_invoker
    implementation = inspect.getsource(build_provider_read_invoker)
    assert "bindings=effective_bindings" in implementation
    assert "internal_bindings=raw_microsoft_bindings" in implementation
