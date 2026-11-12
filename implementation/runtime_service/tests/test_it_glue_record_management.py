"""IT Glue named write registry and trusted existing client boundary tests."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.client_boundaries import BoundaryStatus
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)
from jason_runtime.it_glue_record_management import (
    CANONICAL_CAPABILITIES, PROFILE_ENV, PROFILE_VALUE,
    ItGlueWriteActivationError, ValidatedClientItGlueWriteAuthority,
    build_it_glue_write_invoker, register_it_glue_write_foundation,
    register_it_glue_write_invoker, PROVIDER_ID,
)


class Bindings:
    def __init__(self):
        self.active = True

    def find_active_by_jason_identity(self, *, jason_identity_id):
        if self.active and jason_identity_id == "technician":
            return SimpleNamespace(email_address="technician@teamaot.com")
        return None


class Boundaries:
    def __init__(self):
        self.status = BoundaryStatus.VALIDATED
        self.client = "client-17"
        self.org = "81"
        self.reverse_client = "client-17"
        self.reverse_id = "binding-1"
        self.validated = True

    def find_active_for_client(self, *, client_id, provider):
        assert provider == "it_glue"
        if client_id != self.client:
            return None
        return SimpleNamespace(
            id="binding-1", provider="it_glue", client_id=client_id,
            external_tenant_id=self.org, status=self.status,
            validated_at=datetime.now(timezone.utc) if self.validated else None)

    def find_active_for_external_tenant(self, *, provider, external_tenant_id):
        assert provider == "it_glue"
        if str(external_tenant_id) != str(self.org):
            return None
        return SimpleNamespace(
            id=self.reverse_id, client_id=self.reverse_client,
            status=self.status,
        )


def context(principal="technician", client="client-17"):
    return ConnectorContext(
        correlation_id="test", principal_id=principal,
        organization_id="aot", client_id=client,
        capability="it_glue.document.update", mode="execute",
    )


def registry():
    return (
        CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
        ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()),
    )


def test_disabled_profile_registers_only_building_and_planned(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    caps, providers = registry()
    state = register_it_glue_write_foundation(
        capabilities=caps, providers=providers, now=datetime.now(timezone.utc))
    assert state.enabled is False
    assert state.capability_names == ()
    for name in CANONICAL_CAPABILITIES:
        c = caps.get(capability_name=name, version="1.0")
        assert c.lifecycle_status is CapabilityLifecycle.BUILDING
        assert c.approval.required
        assert c.maximum_attempts == 1
        assert c.client_isolation_required
        assert c.metadata["mcp_action_enabled"] == "true"
    assert providers.get(PROVIDER_ID).lifecycle_status is ProviderLifecycle.PLANNED


def test_exact_profile_only_activates_named_boundaries(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)
    caps, providers = registry()
    state = register_it_glue_write_foundation(
        capabilities=caps, providers=providers, now=datetime.now(timezone.utc))
    assert state.enabled is True
    assert set(state.capability_names) == set(CANONICAL_CAPABILITIES)
    for name in CANONICAL_CAPABILITIES:
        assert caps.get(capability_name=name, version="1.0").lifecycle_status is CapabilityLifecycle.ACTIVE
    assert providers.get(PROVIDER_ID).lifecycle_status is ProviderLifecycle.AVAILABLE


def test_unknown_profile_fails_closed(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, "anything-else")
    caps, providers = registry()
    with pytest.raises(ItGlueWriteActivationError, match="PROFILE"):
        register_it_glue_write_foundation(
            capabilities=caps, providers=providers, now=datetime.now(timezone.utc))


def test_trusted_mapping_is_reverse_verified_and_not_supplied_by_caller():
    bindings, boundaries = Bindings(), Boundaries()
    authority = ValidatedClientItGlueWriteAuthority(bindings, boundaries)
    authority.require_authorized(context())
    assert authority.organization_id_for_client(client_id="client-17") == 81
    boundaries.reverse_client = "other-client"
    with pytest.raises(ConnectorAuthorizationError, match="CONFLICT"):
        authority.organization_id_for_client(client_id="client-17")


@pytest.mark.parametrize("change,code", [
    ({"status": BoundaryStatus.PENDING}, "VALIDATED_CLIENT"),
    ({"validated": False}, "VALIDATED_CLIENT"),
    ({"org": "bad"}, "VALIDATED_CLIENT"),
    ({"reverse_id": "other-binding"}, "CONFLICT"),
    ({"reverse_client": "other-client"}, "CONFLICT"),
    ({"client": "other-client"}, "VALIDATED_CLIENT"),
])
def test_invalid_boundaries_rejected(change, code):
    boundaries = Boundaries()
    for key, value in change.items():
        setattr(boundaries, key, value)
    authority = ValidatedClientItGlueWriteAuthority(Bindings(), boundaries)
    with pytest.raises(ConnectorAuthorizationError, match=code):
        authority.require_authorized(context())


@pytest.mark.parametrize("principal", ["unbound", "jason-autonomy-worker"])
def test_non_human_or_unbound_principal_rejected(principal):
    authority = ValidatedClientItGlueWriteAuthority(Bindings(), Boundaries())
    with pytest.raises(ConnectorAuthorizationError):
        authority.require_authorized(context(principal=principal))


def test_disabled_invoker_builder_cannot_expose_write(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    with pytest.raises(ItGlueWriteActivationError, match="DISABLED"):
        build_it_glue_write_invoker(
            openbao_url="http://openbao:8200", transport=object(),
            audit=object(), bindings=Bindings(), boundaries=Boundaries())


def test_unprovisioned_write_approle_does_not_fallback_to_read(monkeypatch, tmp_path):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)
    with pytest.raises(ItGlueWriteActivationError, match="UNPROVISIONED"):
        build_it_glue_write_invoker(
            openbao_url="http://openbao:8200", transport=object(),
            audit=object(), bindings=Bindings(), boundaries=Boundaries(),
            role_id_path=tmp_path / "write-role-absent",
            secret_id_path=tmp_path / "write-secret-absent",
        )


def test_explicit_write_separate_secret_factory_and_scoped_canonical_map(monkeypatch, tmp_path):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)
    role = tmp_path / "role"
    secret = tmp_path / "secret"
    role.write_text("fake-role")
    secret.write_text("fake-secret")
    delegate = build_it_glue_write_invoker(
        openbao_url="http://openbao:8200", transport=object(), audit=object(),
        bindings=Bindings(), boundaries=Boundaries(),
        role_id_path=role, secret_id_path=secret, claims_path=tmp_path / "claims.db",
    )
    assert set(delegate.provider_capability_map.values()) == set(
        CANONICAL_CAPABILITIES.values())
    assert set(delegate.connectors) == {PROVIDER_ID}
    connector = delegate.connectors[PROVIDER_ID]
    assert set(connector.capabilities) == set(CANONICAL_CAPABILITIES.values())
    assert str(connector.credentials.role_id_path) == str(role)
    assert str(connector.credentials.secret_id_path) == str(secret)


def test_all_canonical_operations_are_explicit_approved_names():
    assert CANONICAL_CAPABILITIES == {
        "documentation.flexible.asset.create": "it_glue.flexible_asset.create",
        "documentation.flexible.asset.update": "it_glue.flexible_asset.update",
        "documentation.document.create": "it_glue.document.create",
        "documentation.document.update": "it_glue.document.update",
        "documentation.configuration.create": "it_glue.configuration.create",
    }
