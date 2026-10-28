from dataclasses import replace

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
)
from connectors.microsoft_graph.standard_user_create import (
    CAPABILITY, GRAPH_USER_URL, PROFILE_ENV, PROFILE_VALUE,
    MicrosoftGraphCreateUserWriter, MicrosoftGraphStandardUserCreateConnector,
    ScopedGraphCreateToken, SealedInitialPassword, TrustedCloudUserScope,
)


class FakeScope:
    allowed = True
    tenant_id = "tenant-xyz"
    source = "entra_cloud"
    def require_approved_request(self, *, context, request_id):
        if (not self.allowed or context.principal_id != "tech"
                or context.client_id != "client-17" or request_id != "REQ-12345"):
            raise ConnectorAuthorizationError("UNAUTHORIZED_ONBOARDING")
        return TrustedCloudUserScope(
            client_id="client-17", tenant_id=self.tenant_id,
            managed_domains=frozenset({"contoso.example"}),
            source_authority=self.source,
            approved_user_principal_name="jane.smith@contoso.example",
        )


class FakeSecrets:
    password = "A_Strong_Example_Password_ABC123!"
    reference = "sealed:request-123"
    def read_for_onboarding(self, *, client_id, request_id, upn):
        assert client_id == "client-17"
        assert request_id == "REQ-12345"
        assert upn.endswith("@contoso.example")
        return SealedInitialPassword(self.reference, self.password)


class FakeDirectory:
    def __init__(self):
        self.users = {}
        self.force_mismatch = False
    def search_users(self, *, microsoft_tenant_id, selector, value, maximum_records=10):
        assert selector == "user_principal_name"
        assert microsoft_tenant_id == "tenant-xyz"
        return tuple(x for x in self.users.values()
                     if x["userPrincipalName"].casefold() == value.casefold())
    def read_user(self, *, microsoft_tenant_id, microsoft_object_id):
        assert microsoft_tenant_id == "tenant-xyz"
        result = dict(self.users[microsoft_object_id])
        if self.force_mismatch:
            result["accountEnabled"] = True
        return result


class FakeTokens:
    profile = "user-create"
    tenant = "tenant-xyz"
    def token_for_tenant(self, *, tenant_id, profile):
        assert tenant_id == "tenant-xyz"
        assert profile == "user-create"
        return ScopedGraphCreateToken(
            tenant_id=self.tenant, profile=self.profile,
            access_token="private-bearer-token",
        )


class FakeTransport:
    def __init__(self, directory):
        self.directory = directory
        self.calls = []
        self.created = 0
    def request(self, *, method, url, headers, params=None, json=None,
                timeout_seconds=20, **kwargs):
        self.calls.append((method, url, json))
        assert method == "POST"
        assert url == GRAPH_USER_URL
        assert headers["Authorization"] == "Bearer private-bearer-token"
        assert json["accountEnabled"] is False
        assert set(json["passwordProfile"]) == {
            "forceChangePasswordNextSignIn", "password",
        }
        assert json["passwordProfile"]["forceChangePasswordNextSignIn"] is True
        assert "password" not in str(json["displayName"]).lower()
        self.created += 1
        object_id = f"object-{self.created}"
        self.directory.users[object_id] = {
            "id": object_id,
            "displayName": json["displayName"],
            "userPrincipalName": json["userPrincipalName"],
            "accountEnabled": False,
        }
        return {"id": object_id}


class FakeAudit:
    def __init__(self):
        self.events = []
    def record(self, name, context, details):
        self.events.append((name, details))


@pytest.fixture
def profile(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, PROFILE_VALUE)


def harness():
    directory = FakeDirectory()
    tokens = FakeTokens()
    transport = FakeTransport(directory)
    scope = FakeScope()
    secrets = FakeSecrets()
    audit = FakeAudit()
    connector = MicrosoftGraphStandardUserCreateConnector(
        reader=directory, writer=MicrosoftGraphCreateUserWriter(
            tokens=tokens, transport=transport,
        ), authority=scope, credentials=secrets, audit=audit,
    )
    return connector, directory, tokens, transport, scope, secrets, audit


def request(*, principal="tech", client="client-17", org="aot",
            mode="execute", capability=CAPABILITY, **kwargs):
    raw = {
        "onboarding_request_id": "REQ-12345",
        "user_principal_name": "jane.smith@contoso.example",
        "display_name": "Jane Smith",
        "mail_nickname": "jane.smith",
    }
    raw.update(kwargs)
    return ConnectorRequest(
        ConnectorContext(
            correlation_id="corr-test", principal_id=principal,
            organization_id=org, client_id=client,
            capability=capability, mode=mode,
        ), raw,
    )


def test_prepared_cloud_user_has_exact_plan_and_one_verified_disabled_creation(profile):
    connector, directory, _, transport, _, secrets, audit = harness()
    plan = connector.prepare_governed_execution(request(
        given_name="Jane", surname="Smith", usage_location="us",
    ))
    assert plan.action_method == "POST"
    assert plan.normalized_path == "/users"
    assert plan.resource_identifier == "jane.smith@contoso.example"
    assert plan.payload["accountEnabled"] is False
    assert plan.payload["usageLocation"] == "US"
    assert secrets.password not in str(plan.payload)
    assert secrets.password not in repr(plan)
    assert "private-bearer-token" not in repr(plan)
    assert transport.calls == []

    result = connector.execute_governed_execution(plan)
    assert transport.created == 1
    assert result.data["object_id"] == "object-1"
    assert result.data["account_enabled"] is False
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert result.data["credential_delivery"] == "separate_secure_workflow_required"
    assert secrets.password not in str(result.data)
    assert secrets.password not in str(audit.events)
    assert [e[0] for e in audit.events] == [
        "connector.mutation.requested", "connector.mutation.verified",
    ]


def test_no_duplicate_post_when_existing_user_found(profile):
    connector, directory, _, transport, *_ = harness()
    directory.users["existing"] = {
        "id": "existing", "userPrincipalName": "jane.smith@contoso.example",
        "displayName": "Jane Smith", "accountEnabled": False,
    }
    with pytest.raises(ConnectorAuthorizationError, match="USER_ALREADY_EXISTS"):
        connector.prepare_governed_execution(request())
    assert transport.calls == []


def test_duplicate_appearing_after_plan_cancels_post(profile):
    connector, directory, _, transport, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    directory.users["existing"] = {
        "id": "existing", "userPrincipalName": "jane.smith@contoso.example",
        "displayName": "Jane Smith", "accountEnabled": False,
    }
    with pytest.raises(ConnectorAuthorizationError, match="USER_ALREADY_EXISTS"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


@pytest.mark.parametrize("overrides", [
    {"user_principal_name": "wrong@another.example"},
    {"user_principal_name": "admin@contoso.example"},
    {"user_principal_name": "administrator@contoso.example"},
    {"user_principal_name": "double..dot@contoso.example"},
    {"user_principal_name": "not-an-email"},
    {"user_principal_name": "@contoso.example"},
    {"user_principal_name": "jane.smith@contoso.example@"},
    {"display_name": ""},
    {"mail_nickname": ""},
    {"mail_nickname": "bad alias"},
    {"usage_location": "USA"},
    {"given_name": None},
    {"password": "bad"},
    {"accountEnabled": True},
    {"role": "Global Administrator"},
    {"license_sku": "paid"},
    {"group_ids": ["GlobalAdmins"]},
    {"onPremisesImmutableId": "ad-sync"},
])
def test_nonstandard_or_privilege_bearing_payload_is_rejected(profile, overrides):
    connector, _, _, transport, *_ = harness()
    with pytest.raises((ValueError, ConnectorAuthorizationError)):
        connector.prepare_governed_execution(request(**overrides))
    assert transport.calls == []


@pytest.mark.parametrize("overrides", [
    {"principal": "autonomy"},
    {"client": "other-client"},
    {"client": None},
    {"org": "other-org"},
    {"mode": "observe"},
    {"capability": "identity.user.admin.create"},
    {"onboarding_request_id": "NOT-APPROVED"},
])
def test_untrusted_identity_scope_or_onboarding_request_denied(profile, overrides):
    connector, _, _, transport, *_ = harness()
    with pytest.raises((ValueError, PermissionError, ConnectorAuthorizationError)):
        connector.prepare_governed_execution(request(**overrides))
    assert transport.calls == []


def test_synced_source_authority_not_allowed_cloud_creation(profile):
    connector, _, _, transport, scope, *_ = harness()
    scope.source = "on_premises_ad"
    with pytest.raises(ConnectorAuthorizationError, match="CLOUD_SOURCE_AUTHORITY"):
        connector.prepare_governed_execution(request())
    assert transport.calls == []


def test_onboarding_scope_revoked_before_post(profile):
    connector, _, _, transport, scope, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    scope.allowed = False
    with pytest.raises(ConnectorAuthorizationError, match="UNAUTHORIZED_ONBOARDING"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_tenant_switch_after_plan_denied(profile):
    connector, _, _, transport, scope, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    scope.tenant_id = "attacker-tenant"
    with pytest.raises(ConnectorAuthorizationError, match="AUTHORITY_CHANGED"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_changed_secret_after_plan_denied(profile):
    connector, _, _, transport, _, secrets, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    secrets.password = "Different_Password_Example_ABC12345"
    with pytest.raises(ConnectorAuthorizationError, match="CREDENTIAL_COMMITMENT_CHANGED"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_plan_tamper_denied(profile):
    connector, _, _, transport, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    plan.payload["accountEnabled"] = True
    with pytest.raises(ConnectorAuthorizationError, match="EXECUTION_PLAN_MISMATCH"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_provider_wrong_write_profile_or_tenant_denied(profile):
    connector, _, tokens, transport, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    tokens.profile = "directory-read"
    with pytest.raises(ConnectorAuthorizationError, match="TOKEN_SCOPE_MISMATCH"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_disabled_at_prepare_and_after_prepare(profile, monkeypatch):
    connector, _, _, transport, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    monkeypatch.delenv(PROFILE_ENV)
    with pytest.raises(PermissionError, match="DISABLED"):
        connector.prepare_governed_execution(request())
    with pytest.raises(PermissionError, match="DISABLED"):
        connector.execute_governed_execution(plan)
    assert transport.calls == []


def test_unverified_user_never_reported_as_created(profile):
    connector, directory, _, transport, *_ = harness()
    plan = connector.prepare_governed_execution(request())
    directory.force_mismatch = True
    with pytest.raises(RuntimeError, match="READBACK_FAILED"):
        connector.execute_governed_execution(plan)
    assert transport.created == 1


def test_connector_direct_execute_is_denied(profile):
    connector, _, _, transport, *_ = harness()
    with pytest.raises(ConnectorAuthorizationError, match="GOVERNED_EXECUTION_PLAN_REQUIRED"):
        connector.execute(request())
    assert transport.calls == []
