from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
)
from connectors.autotask.operations import resolve_operation_request
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_company_udf_admin import (
    AUTOTASK_COMPANY_UDF_ADMIN_PROFILE,
    AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV,
    AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER,
    SERVICE_COMPANY_UDF_DEFINITION_CREATE,
    SERVICE_COMPANY_UDF_CHOICE_CREATE,
    AutotaskCompanyUdfAdminConnector,
    AutotaskCompanyUdfAdminError,
    company_udf_admin_enabled,
    register_autotask_company_udf_admin_foundation,
)
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)


def registries():
    return (
        CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
        ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()),
    )


def test_schema_admin_dormant_without_exact_profile(monkeypatch):
    monkeypatch.delenv(AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, raising=False)
    caps, providers = registries()
    assert not register_autotask_company_udf_admin_foundation(
        capabilities=caps, providers=providers, now=datetime.now(timezone.utc))
    assert caps.get(
        capability_name=SERVICE_COMPANY_UDF_DEFINITION_CREATE, version="1.0",
    ).lifecycle_status is CapabilityLifecycle.BUILDING
    assert providers.get(
        AUTOTASK_COMPANY_UDF_ADMIN_PROVIDER
    ).lifecycle_status is ProviderLifecycle.PLANNED
    assert company_udf_admin_enabled() is False


def test_schema_admin_exact_profile_requires_native_mutation_gate(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, AUTOTASK_COMPANY_UDF_ADMIN_PROFILE)
    monkeypatch.delenv(AUTOTASK_MUTATION_ENABLED_ENV, raising=False)
    with pytest.raises(AutotaskCompanyUdfAdminError, match="MUTATION_DISABLED"):
        company_udf_admin_enabled()
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    caps, providers = registries()
    assert register_autotask_company_udf_admin_foundation(
        capabilities=caps, providers=providers, now=datetime.now(timezone.utc))
    assert caps.get_current(
        capability_name=SERVICE_COMPANY_UDF_CHOICE_CREATE
    ).lifecycle_status is CapabilityLifecycle.ACTIVE
    assert caps.get_current(
        capability_name=SERVICE_COMPANY_UDF_DEFINITION_CREATE
    ).approval.required is True
    assert caps.get_current(
        capability_name=SERVICE_COMPANY_UDF_DEFINITION_CREATE
    ).maximum_attempts == 1


def test_company_udf_definition_payload_is_narrow_and_disabled_by_default():
    result = AutotaskCompanyUdfAdminConnector.validated_payload(
        "autotask.udf.definition.create",
        {"name": "enable_jason_outbound_comm", "description": "AOT approval gate"},
    )
    assert result["udfType"] == 1
    assert result["dataType"] == 3
    assert result["defaultValue"] == ""
    assert result["isRequired"] is False
    assert result["isVisibleToClientPortal"] is False
    assert result["name"] == "enable_jason_outbound_comm"
    with pytest.raises(AutotaskCompanyUdfAdminError, match="FIELD_NOT_ALLOWED"):
        AutotaskCompanyUdfAdminConnector.validated_payload(
            "autotask.udf.definition.create",
            {"name": "new_field", "udfType": 2},
        )


@pytest.mark.parametrize("name", ["../../unsafe", "x", "foo bar", "name\nheader"])
def test_company_udf_definition_rejects_untrusted_names(name):
    with pytest.raises(ValueError):
        AutotaskCompanyUdfAdminConnector.validated_payload(
            "autotask.udf.definition.create", {"name": name})


def test_choice_payload_rejects_extra_fields_and_invalid_identifier():
    assert AutotaskCompanyUdfAdminConnector.validated_payload(
        "autotask.udf.list.item.create",
        {"udfFieldId": 999, "valueForDisplay": "True", "valueForExport": "True"},
    ) == {
        "udfFieldId": 999, "valueForDisplay": "True",
        "valueForExport": "True", "isActive": True,
    }
    with pytest.raises(AutotaskCompanyUdfAdminError, match="CHOICE_FIELDS_INVALID"):
        AutotaskCompanyUdfAdminConnector.validated_payload(
            "autotask.udf.list.item.create",
            {"udfFieldId": 1, "valueForDisplay": "Yes", "valueForExport": "Yes",
             "isActive": False},
        )
    with pytest.raises(ValueError):
        AutotaskCompanyUdfAdminConnector.validated_payload(
            "autotask.udf.list.item.create",
            {"udfFieldId": 0, "valueForDisplay": "True", "valueForExport": "True"},
        )


def test_provider_operation_resolves_only_exact_static_schema_paths():
    for capability, path in [
        ("autotask.udf.definition.create", "/V1.0/UserDefinedFieldDefinitions"),
        ("autotask.udf.list.item.create", "/V1.0/UserDefinedFieldListItems"),
    ]:
        method, actual, params, body = resolve_operation_request(
            capability, {"payload": {"name": "safe"}},
        )
        assert method == "POST"
        assert actual == path
        assert params is None
        assert body == {"name": "safe"}


def test_prepared_plan_verification_and_duplicate_gate(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, AUTOTASK_COMPANY_UDF_ADMIN_PROFILE)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    calls = []

    class Transport:
        def request(self, **kwargs):
            calls.append((kwargs["method"], kwargs["url"]))
            if kwargs["url"].endswith("/query"):
                return {"items": []}
            if kwargs["method"] == "POST":
                return {"itemId": 10001}
            if kwargs["method"] == "GET":
                return {"item": {
                    "id": 10001,
                    **AutotaskCompanyUdfAdminConnector.validated_payload(
                        "autotask.udf.definition.create", {
                            "name": "enable_jason_outbound_comm",
                        }
                    ),
                }}
            raise AssertionError("unexpected method")

    class Secrets:
        def resolve(self, logical_secret, context):
            assert logical_secret == "autotask.write"
            return {}

    class Audit:
        def record(self, *args, **kwargs):
            pass

    def fake_prepare(self, request, credentials):
        assert request.context.mode == "execute"
        entity = (
            "UserDefinedFieldDefinitions"
            if request.context.capability == "autotask.udf.definition.create"
            else "UserDefinedFieldListItems"
        )
        return PreparedRequest(
            method="POST", url=f"https://psa.example/V1.0/{entity}",
            headers={"ImpersonationResourceId": "123"}, params=None,
            json=request.arguments["payload"], audit_operation=f"/V1.0/{entity}",
        )

    monkeypatch.setattr(AutotaskMutationConnector, "prepare_request", fake_prepare)
    connector = AutotaskCompanyUdfAdminConnector(
        secrets=Secrets(), transport=Transport(), audit=Audit(), bindings=None)
    req = ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-test", principal_id="person-al",
            organization_id="aot", client_id=None,
            capability="autotask.udf.definition.create", mode="execute",
        ),
        arguments={"payload": {"name": "enable_jason_outbound_comm"}},
    )
    plan = connector.prepare_governed_execution(req)
    assert plan.payload["isVisibleToClientPortal"] is False
    assert calls == [("GET", "https://psa.example/V1.0/UserDefinedFieldDefinitions/query")]
    result = connector.execute_governed_execution(plan)
    assert result.data["itemId"] == 10001
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert len([x for x in calls if x[0] == "POST"]) == 1
    assert len([x for x in calls if x[0] == "GET" and x[1].endswith("/query")]) == 2
    with pytest.raises(AutotaskCompanyUdfAdminError, match="PLAN_MISMATCH"):
        connector.execute_governed_execution(
            SimpleNamespace(
                opaque=plan.opaque,
                provider_capability=plan.provider_capability,
                action_method="PATCH",
                resource_identifier=None,
                normalized_path=plan.normalized_path,
                payload=plan.payload,
                parameters=plan.parameters,
            )
        )


def test_preflight_existing_field_blocks_duplicate_without_mutation(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_COMPANY_UDF_ADMIN_PROFILE_ENV, AUTOTASK_COMPANY_UDF_ADMIN_PROFILE)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    calls = []

    class Transport:
        def request(self, **kwargs):
            calls.append(kwargs["method"])
            assert kwargs["method"] == "GET"
            return {"items": [{"id": 456, "name": "enable_jason_outbound_comm"}]}

    class Secrets:
        def resolve(self, *_):
            return {}

    class Audit:
        def record(self, *args, **kwargs):
            pass

    monkeypatch.setattr(
        AutotaskMutationConnector, "prepare_request",
        lambda self, req, creds: PreparedRequest(
            method="POST", url="https://psa.example/V1.0/UserDefinedFieldDefinitions",
            headers={}, json=req.arguments["payload"],
            audit_operation="/V1.0/UserDefinedFieldDefinitions",
        ),
    )
    connector = AutotaskCompanyUdfAdminConnector(
        secrets=Secrets(), transport=Transport(), audit=Audit(), bindings=None)
    req = ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-test", principal_id="person-al",
            organization_id="aot", client_id=None,
            capability="autotask.udf.definition.create", mode="execute",
        ),
        arguments={"payload": {"name": "enable_jason_outbound_comm"}},
    )
    with pytest.raises(AutotaskCompanyUdfAdminError, match="ALREADY_EXISTS"):
        connector.prepare_governed_execution(req)
    assert calls == ["GET"]

def test_company_udf_choice_preflight_never_trusts_incomplete_page():
    class Transport:
        def request(self, **kwargs):
            assert kwargs["method"] == "GET"
            import json
            search = json.loads(kwargs["params"]["search"])
            assert search["MaxRecords"] == 500
            return {"items": [{"udfFieldId": 111, "valueForDisplay": "False"}],
                    "pageDetails": {"nextPageUrl": "https://psa.example/next"}}

    class Secrets:
        def resolve(self, *_):
            raise AssertionError("secrets must not be needed for direct query test")

    class Audit:
        def record(self, *args, **kwargs):
            pass

    connector = AutotaskCompanyUdfAdminConnector(
        secrets=Secrets(), transport=Transport(), audit=Audit(), bindings=None,
    )
    prepared = PreparedRequest(
        method="POST",
        url="https://psa.example/V1.0/UserDefinedFieldListItems",
        headers={},
        audit_operation="/V1.0/UserDefinedFieldListItems",
    )
    with pytest.raises(AutotaskCompanyUdfAdminError, match="QUERY_INCOMPLETE"):
        connector._query(
            prepared, "UserDefinedFieldListItems", "udfFieldId", 111,
        )
