"""Transport-only tests; no provider credentials or network access."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_procurement import (
    AUTOTASK_CATALOG_AUTH_MODE_ENV, AutotaskProductionProcurementConnector,
)


class Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == "autotask.write"
        assert context.principal_id == "authenticated-requester"
        return {"username": "jason-api@example.invalid", "secret": "test-secret", "integration_code": "test-code"}


class Bindings:
    def find_active_by_jason_identity(self, **kwargs):
        return SimpleNamespace(email_address="requester@example.invalid")


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context.principal_id, details))


class Transport:
    def __init__(self, access=1, readback_id=123):
        self.calls = []
        self.access = access
        self.readback_id = readback_id

    def request(self, **kwargs):
        self.calls.append(kwargs)
        url = kwargs["url"]
        if url.endswith("zoneInformation"):
            return {"url": "https://example.invalid/atservicesrest/"}
        if url.endswith("Resources/query"):
            return {"items": [{"id": 77, "email": "requester@example.invalid", "isActive": True}]}
        if url.endswith("entityInformation"):
            return {"userAccessForCreate": self.access, "userAccessForUpdate": self.access}
        if kwargs["method"] == "GET":
            return {"item": {"id": self.readback_id}}
        return {"itemId": 123}


def request(operation="autotask.service.create", **extra):
    payload = {"name": "Synthetic catalog entry", "billingCodeID": 1, "periodType": 1, "unitPrice": 0}
    if "bundle" in operation:
        payload.pop("periodType")
    if operation.endswith("update"):
        payload.pop("periodType", None)
        payload["id"] = 123
    return ConnectorRequest(
        context=ConnectorContext(correlation_id="test", principal_id="authenticated-requester",
            organization_id="aot", client_id=None, capability=operation, mode="execute"),
        arguments={"payload": payload, **extra},
    )


def connector(transport=None, bindings=None):
    return AutotaskProductionProcurementConnector(secrets=Secrets(),
        transport=transport or Transport(), audit=Audit(), bindings=bindings)


@pytest.fixture(autouse=True)
def catalog_configuration(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "true")
    monkeypatch.setenv(AUTOTASK_CATALOG_AUTH_MODE_ENV, "jason_managed")


@pytest.mark.parametrize("operation", ["autotask.service.create", "autotask.service.update",
    "autotask.service.bundle.create", "autotask.service.bundle.update"])
def test_catalog_uses_service_identity_and_preserves_requester_audit(operation):
    c = connector()
    prepared = c.prepare_governed_execution(request(operation))
    assert prepared.parameters["execution_account"] == "jason-api@example.invalid"
    assert prepared.parameters["execution_auth_mode"] == "jason_managed"
    assert "test-secret" not in repr(prepared.parameters)
    result = c.execute_governed_execution(prepared)
    assert result.data["jasonVerification"]["readbackVerified"] is True
    calls = c._transport.calls
    assert not any("Resources/query" in call["url"] for call in calls)
    provider_calls = calls[1:]
    assert all(call["headers"]["UserName"] == "jason-api@example.invalid" for call in provider_calls)
    assert all("ImpersonationResourceId" not in call["headers"] for call in provider_calls)
    assert provider_calls[0]["url"].endswith("entityInformation")
    assert provider_calls[-1]["method"] == "GET"
    assert all(event[1] == "authenticated-requester" for event in c._audit.events)


@pytest.mark.parametrize("access", [0, None, True, "invalid"])
def test_provider_access_denial_prevents_write(access):
    c = connector(Transport(access=access))
    with pytest.raises(PermissionError):
        c.execute(request())
    assert all(call["method"] == "GET" for call in c._transport.calls)


@pytest.mark.parametrize("mode", ["", "typo"])
def test_invalid_configuration_fails_before_provider(monkeypatch, mode):
    monkeypatch.setenv(AUTOTASK_CATALOG_AUTH_MODE_ENV, mode)
    c = connector()
    with pytest.raises(PermissionError, match="AUTH_MODE_INVALID"):
        c.prepare_governed_execution(request())
    assert c._transport.calls == []


def test_absent_setting_preserves_impersonation(monkeypatch):
    monkeypatch.delenv(AUTOTASK_CATALOG_AUTH_MODE_ENV)
    c = connector(bindings=Bindings())
    prepared = c.prepare_governed_execution(request())
    assert prepared.parameters["execution_auth_mode"] == "impersonated"
    assert prepared.opaque.prepared.headers["ImpersonationResourceId"] == "77"


def test_caller_cannot_select_service_execution(monkeypatch):
    monkeypatch.delenv(AUTOTASK_CATALOG_AUTH_MODE_ENV)
    c = connector()
    with pytest.raises(PermissionError, match="TRUSTED_PRINCIPAL_BINDING_REQUIRED"):
        c.prepare_governed_execution(request(execution_auth_mode="jason_managed"))


def test_other_procurement_operations_still_require_requester_binding():
    c = connector()
    req = replace(request(), context=replace(request().context, capability="autotask.product.create"),
        arguments={"payload": {"name": "Test", "isActive": False, "isSerialized": False}})
    with pytest.raises(PermissionError, match="TRUSTED_PRINCIPAL_BINDING_REQUIRED"):
        c.prepare_governed_execution(req)


@pytest.mark.parametrize("field,value", [("execution_account", "other@example.invalid"),
    ("execution_auth_mode", "impersonated"), ("impersonation_resource_id", "77")])
def test_execution_identity_is_bound_to_prepared_action(field, value):
    c = connector()
    prepared = c.prepare_governed_execution(request())
    altered = replace(prepared, parameters={**prepared.parameters, field: value})
    with pytest.raises(PermissionError, match="parameters changed"):
        c.execute_governed_execution(altered)
    assert all(call["method"] == "GET" for call in c._transport.calls)


def test_config_change_invalidates_prepared_execution(monkeypatch):
    c = connector()
    prepared = c.prepare_governed_execution(request())
    monkeypatch.setenv(AUTOTASK_CATALOG_AUTH_MODE_ENV, "impersonated")
    with pytest.raises(PermissionError, match="AUTH_MODE_CHANGED"):
        c.execute_governed_execution(prepared)
    assert all(call["method"] == "GET" for call in c._transport.calls)


def test_disabled_write_gate_still_blocks(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "false")
    c = connector()
    with pytest.raises(PermissionError, match="EXECUTION_DISABLED"):
        c.prepare_governed_execution(request())
    assert c._transport.calls == []


def test_readback_mismatch_is_not_success():
    c = connector(Transport(readback_id=999))
    with pytest.raises(ValueError, match="READBACK_ID_MISMATCH"):
        c.execute(request())
