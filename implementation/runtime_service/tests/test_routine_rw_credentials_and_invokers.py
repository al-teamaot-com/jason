from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectors.core.contracts import ConnectorAuthorizationError
from connectors.microsoft_graph.token import MicrosoftApplicationToken
from jason_runtime import routine_rw_credentials as credentials_module
from jason_runtime.routine_rw_credentials import (
    GovernedGraphUserCreateTokens, OpenBaoOnboardingPasswordReader,
)
from jason_runtime.routine_rw_registration import (
    ENTRA_USER_CREATE, IT_GLUE_NOTES,
)
from jason_runtime.routine_rw_runtime import build_routine_rw_invokers


class FakeBoundaries:
    def __init__(self):
        self.boundary = SimpleNamespace(
            status="validated", profile="user-create",
            provider="microsoft_graph_user_create",
            client_id="client-1",
            external_tenant_id="tenant-1", application_id="app-1",
        )
    def find_active_for_external_tenant(self, *, provider, external_tenant_id):
        if provider != "microsoft_graph_user_create":
            return None
        if external_tenant_id != "tenant-1":
            return None
        return self.boundary


class FakeTokens:
    def acquire_for_client(self, *, client_id, correlation_id):
        assert client_id == "client-1"
        return MicrosoftApplicationToken(
            access_token="secret-token-not-for-logging",
            token_type="Bearer",
            expires_at_epoch=2000000000,
            tenant_id="tenant-1", application_id="app-1",
            scope="https://graph.microsoft.com/.default",
            certificate_thumbprint="A"*40,
        )


def test_scoped_token_uses_existing_validated_client_boundary():
    boundaries = FakeBoundaries()
    result = GovernedGraphUserCreateTokens(
        boundaries=boundaries, provider=FakeTokens(),
    ).token_for_tenant(tenant_id="tenant-1", profile="user-create")
    assert result.profile == "user-create"
    assert result.tenant_id == "tenant-1"
    assert "secret-token-not-for-logging" not in repr(result)


@pytest.mark.parametrize("tenant,profile", [
    ("another", "user-create"),
    ("tenant-1", "directory-read"),
])
def test_token_wrong_tenant_or_profile_does_not_fall_back(tenant, profile):
    with pytest.raises(ConnectorAuthorizationError):
        GovernedGraphUserCreateTokens(
            boundaries=FakeBoundaries(), provider=FakeTokens(),
        ).token_for_tenant(tenant_id=tenant, profile=profile)


def test_token_wrong_app_id_fails_closed():
    class WrongApp(FakeTokens):
        def acquire_for_client(self, *, client_id, correlation_id):
            return replace(
                super().acquire_for_client(
                    client_id=client_id, correlation_id=correlation_id,
                ), application_id="attacker-app",
            )
    with pytest.raises(ConnectorAuthorizationError, match="TOKEN_BOUNDARY"):
        GovernedGraphUserCreateTokens(
            boundaries=FakeBoundaries(), provider=WrongApp(),
        ).token_for_tenant(tenant_id="tenant-1", profile="user-create")


def test_sealed_password_is_read_only_from_single_hashed_scope(monkeypatch):
    got = {}
    password = "ExampleRandomCredentialForTest-0123456789"
    class FakeResolver:
        def __init__(self, *, mappings, allowed_fields, **kwargs):
            got["mappings"] = mappings
            got["fields"] = allowed_fields
        def resolve(self, logical_name, context):
            got["context"] = context
            assert logical_name == "microsoft_graph.onboarding_initial_password"
            return {
                "client_id": "client-1",
                "onboarding_request_id": "REQ-11111",
                "user_principal_name": "user@example.test",
                "credential_reference": "sealed:abc",
                "password": password,
            }
    monkeypatch.setattr(credentials_module, "OpenBaoSecretResolver", FakeResolver)
    reader = OpenBaoOnboardingPasswordReader(
        openbao_url="http://openbao:8200",
        role_id_path=Path("/fake/role"),
        secret_id_path=Path("/fake/secret"),
    )
    value = reader.read_for_onboarding(
        client_id="client-1", request_id="REQ-11111",
        upn="user@example.test",
    )
    assert value.reference == "sealed:abc"
    assert value.plaintext == password
    assert password not in repr(value)
    expected_digest = hashlib.sha256(
        b"client-1|REQ-11111|user@example.test"
    ).hexdigest()
    assert got["mappings"]["microsoft_graph.onboarding_initial_password"].endswith(
        f"/{expected_digest}"
    )


def test_mismatch_in_sealed_request_scope_denied(monkeypatch):
    class WrongResolver:
        def __init__(self, **kwargs): pass
        def resolve(self, logical_name, context):
            return {
                "client_id": "other-client",
                "onboarding_request_id": "REQ-11111",
                "user_principal_name": "user@example.test",
                "credential_reference": "sealed:abc",
                "password": "ExampleRandomCredentialForTest-0123456789",
            }
    monkeypatch.setattr(credentials_module, "OpenBaoSecretResolver", WrongResolver)
    with pytest.raises(ConnectorAuthorizationError, match="CREDENTIAL_MISMATCH"):
        OpenBaoOnboardingPasswordReader(
            openbao_url="http://openbao:8200",
            role_id_path=Path("/fake/role"),
            secret_id_path=Path("/fake/secret"),
        ).read_for_onboarding(
            client_id="client-1", request_id="REQ-11111",
            upn="user@example.test",
        )


def test_integrated_invokers_use_exact_named_provider_capabilities_only():
    invokers = build_routine_rw_invokers(
        enabled_capabilities=(IT_GLUE_NOTES, ENTRA_USER_CREATE),
        openbao_url="http://openbao:8200",
        boundaries=FakeBoundaries(),
        identities=SimpleNamespace(),
        approvals=SimpleNamespace(),
        directory=SimpleNamespace(),
        transport=SimpleNamespace(),
        audit=SimpleNamespace(),
    )
    assert set(invokers) == {IT_GLUE_NOTES, ENTRA_USER_CREATE}
    it_glue = invokers[IT_GLUE_NOTES]
    graph = invokers[ENTRA_USER_CREATE]
    assert it_glue.provider_capability_map == {
        ("it_glue_configuration_note_update", IT_GLUE_NOTES):
        "it_glue.configuration.update",
    }
    assert graph.provider_capability_map == {
        ("microsoft_graph_standard_user_create", ENTRA_USER_CREATE):
        ENTRA_USER_CREATE,
    }


def test_default_off_builder_creates_no_connectors_or_secrets():
    assert build_routine_rw_invokers(
        enabled_capabilities=(),
        openbao_url="http://openbao:8200",
        boundaries=FakeBoundaries(), identities=None,
        approvals=None, directory=None,
        transport=None, audit=None,
    ) == {}
