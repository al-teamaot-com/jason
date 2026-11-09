from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV, AutotaskMutationConnector,
)
from connectors.autotask.operations import resolve_operation_request
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_company_outbound_opt_in_update import (
    AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE,
    AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV,
    AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER,
    SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE,
    AutotaskCompanyOutboundOptInConnector,
    AutotaskCompanyOutboundOptInError,
    _parse_existing_company,
    company_outbound_opt_in_update_enabled,
    register_autotask_company_outbound_opt_in_foundation,
)
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)
from orchestrator.connector_invoker import ProviderPreparedExecution

FIELD = "enable_jason_outbound_comm"
COMPANY_ID = 1158
COMPANY_NAME = "XYZ Test Company"
OPERATION = "autotask.company.outbound.optin.update"


def _registries():
    return (
        CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
        ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()),
    )


def _request(company_id=COMPANY_ID, enabled=True, **extra):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-xyz-u1", principal_id="person-al",
            organization_id="aot", client_id=None,
            capability=OPERATION, mode="execute",
        ),
        arguments={"payload": {
            "company_id": company_id, "enabled": enabled, **extra,
        }},
    )


def _enable(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV,
        AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE,
    )
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")


def _company(value=None, company_id=COMPANY_ID):
    return {
        "id": company_id,
        "companyName": COMPANY_NAME,
        "userDefinedFields": [
            {"name": "Business_Hours", "value": "Monday to Friday"},
            {"name": FIELD, "value": value},
        ],
    }


def test_registration_remains_dormant_until_independent_profile_and_native_gate(monkeypatch):
    monkeypatch.delenv(AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV, raising=False)
    c, p = _registries()
    assert not register_autotask_company_outbound_opt_in_foundation(
        capabilities=c, providers=p, now=datetime.now(timezone.utc),
    )
    assert c.get(
        capability_name=SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE, version="1.0",
    ).lifecycle_status == CapabilityLifecycle.BUILDING
    assert p.get(AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROVIDER).lifecycle_status == ProviderLifecycle.PLANNED
    assert not company_outbound_opt_in_update_enabled()
    monkeypatch.setenv(
        AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE_ENV,
        AUTOTASK_COMPANY_OUTBOUND_OPT_IN_PROFILE,
    )
    monkeypatch.delenv(AUTOTASK_MUTATION_ENABLED_ENV, raising=False)
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="MUTATION_DISABLED"):
        company_outbound_opt_in_update_enabled()
    _enable(monkeypatch)
    c, p = _registries()
    assert register_autotask_company_outbound_opt_in_foundation(
        capabilities=c, providers=p, now=datetime.now(timezone.utc),
    )
    item = c.get_current(capability_name=SERVICE_COMPANY_OUTBOUND_OPT_IN_UPDATE)
    assert item.approval.required is True
    assert item.lifecycle_status == CapabilityLifecycle.ACTIVE
    assert item.maximum_attempts == 1
    assert item.metadata["controlled_field"] == FIELD


def test_native_patch_restricted_only_to_one_company_id_and_named_udf():
    company_id, value, patch = AutotaskCompanyOutboundOptInConnector.validated_payload(
        {"company_id": COMPANY_ID, "enabled": True},
    )
    assert company_id == COMPANY_ID
    assert value == "True"
    assert patch == {
        "id": COMPANY_ID,
        "userDefinedFields": [{"name": FIELD, "value": "True"}],
    }
    method, route, params, body = resolve_operation_request(
        OPERATION, {"payload": patch},
    )
    assert (method, route, params, body) == (
        "PATCH", "/V1.0/Companies", None, patch,
    )
    for bad in (
        {"company_id": 1158, "enabled": "True"},
        {"company_id": True, "enabled": True},
        {"company_id": 0, "enabled": True},
        {"company_id": COMPANY_ID, "enabled": True, "other": "change company"},
        {"company_id": COMPANY_ID},
    ):
        with pytest.raises((ValueError, AutotaskCompanyOutboundOptInError)):
            AutotaskCompanyOutboundOptInConnector.validated_payload(bad)


def test_company_state_parser_rejects_duplicates_wrong_company_unknown_value():
    assert _parse_existing_company(_company("False"), COMPANY_ID)[0] == "False"
    assert _parse_existing_company(_company(None), COMPANY_ID)[0] is None
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="MISMATCH"):
        _parse_existing_company(_company("False", company_id=597), COMPANY_ID)
    duplicate = _company("True")
    duplicate["userDefinedFields"].append({"name": FIELD, "value": "False"})
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="AMBIGUOUS"):
        _parse_existing_company(duplicate, COMPANY_ID)
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="VALUE_INVALID"):
        _parse_existing_company(_company("Yes"), COMPANY_ID)


class _Secrets:
    def resolve(self, *_):
        return {}


class _Audit:
    def record(self, *args, **kwargs):
        pass


class _Transport:
    def __init__(self, value=None, *, schema_present=True, choices_valid=True):
        self.value = value
        self.schema_present = schema_present
        self.choices_valid = choices_valid
        self.calls = []
        self.concurrent_change = False

    def request(self, **kwargs):
        method, url = kwargs["method"], kwargs["url"]
        self.calls.append((method, url, kwargs.get("json")))
        if url.endswith("/UserDefinedFieldDefinitions/query"):
            return {"items": [{
                "id": 16001, "name": FIELD, "udfType": 1, "dataType": 3,
                "isActive": True, "isVisibleToClientPortal": False,
            }] if self.schema_present else []}
        if url.endswith("/UserDefinedFieldListItems/query"):
            if not self.choices_valid:
                return {"items": [{
                    "udfFieldId": 16001, "valueForDisplay": "True",
                    "valueForExport": "True", "isActive": True,
                }]}
            return {"items": [
                {"udfFieldId": 16001, "valueForDisplay": v,
                 "valueForExport": v, "isActive": True}
                for v in ("True", "False")
            ]}
        if url.endswith(f"/Companies/{COMPANY_ID}") and method == "GET":
            result = _company(self.value)
            if self.concurrent_change:
                result["userDefinedFields"][0]["value"] = "Changed"
            return {"item": result}
        if url.endswith("/Companies") and method == "PATCH":
            body = kwargs["json"]
            assert set(body) == {"id", "userDefinedFields"}
            assert body["id"] == COMPANY_ID
            assert body["userDefinedFields"][0]["name"] == FIELD
            self.value = body["userDefinedFields"][0]["value"]
            return {"itemId": COMPANY_ID}
        raise AssertionError(f"unexpected provider request: {method} {url}")


def _fake_prepare(self, request, _credentials):
    return PreparedRequest(
        method="PATCH", url="https://psa.example/V1.0/Companies",
        headers={"ImpersonationResourceId": "29682885"},
        params=None, json=request.arguments["payload"],
        audit_operation="/V1.0/Companies",
    )


def _connector(monkeypatch, transport):
    monkeypatch.setattr(
        AutotaskMutationConnector, "prepare_request", _fake_prepare,
    )
    return AutotaskCompanyOutboundOptInConnector(
        secrets=_Secrets(), transport=transport, audit=_Audit(), bindings=None,
    )


def test_xyz_exact_optin_postwrite_readback_and_no_other_udf_mutations(monkeypatch):
    _enable(monkeypatch)
    transport = _Transport(value=None)
    connector = _connector(monkeypatch, transport)
    plan = connector.prepare_governed_execution(_request())
    assert plan.resource_identifier == str(COMPANY_ID)
    assert plan.resource_type == "service_company"
    assert plan.action_method == "PATCH"
    assert plan.payload["userDefinedFields"] == [{"name": FIELD, "value": "True"}]
    assert not any(call[0] == "PATCH" for call in transport.calls)
    result = connector.execute_governed_execution(plan)
    assert transport.value == "True"
    assert result.data["jasonVerification"] == {
        "readbackVerified": True,
        "companyID": COMPANY_ID,
        "field": FIELD,
        "value": "True",
        "unrelatedUdfsPreserved": True,
    }
    assert len([c for c in transport.calls if c[0] == "PATCH"]) == 1
    assert len([c for c in transport.calls if c[0] == "GET" and "/Companies/" in c[1]]) == 3


def test_disable_is_a_separate_exact_approved_update(monkeypatch):
    _enable(monkeypatch)
    transport = _Transport(value="True")
    connector = _connector(monkeypatch, transport)
    plan = connector.prepare_governed_execution(_request(enabled=False))
    assert plan.payload["userDefinedFields"] == [{"name": FIELD, "value": "False"}]
    result = connector.execute_governed_execution(plan)
    assert result.data["jasonVerification"]["value"] == "False"


def test_already_enabled_and_missing_schema_fail_without_write(monkeypatch):
    _enable(monkeypatch)
    transport = _Transport(value="True")
    connector = _connector(monkeypatch, transport)
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="ALREADY_SET"):
        connector.prepare_governed_execution(_request())
    assert not any(c[0] == "PATCH" for c in transport.calls)

    transport = _Transport(value=None, schema_present=False)
    connector = _connector(monkeypatch, transport)
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="SCHEMA_NOT_UNIQUE"):
        connector.prepare_governed_execution(_request())
    assert not any(c[0] == "PATCH" for c in transport.calls)


def test_missing_required_true_false_choices_denies_company_update(monkeypatch):
    _enable(monkeypatch)
    transport = _Transport(value=None, choices_valid=False)
    connector = _connector(monkeypatch, transport)
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="CHOICES_INVALID"):
        connector.prepare_governed_execution(_request())
    assert not any(c[0] == "PATCH" for c in transport.calls)


def test_tampered_execution_target_or_payload_and_concurrent_change_fail_closed(monkeypatch):
    _enable(monkeypatch)
    transport = _Transport()
    connector = _connector(monkeypatch, transport)
    plan = connector.prepare_governed_execution(_request())
    for altered in (
        replace(plan, resource_identifier="597"),
        replace(plan, payload={**plan.payload, "companyName": "wrong"}),
        replace(plan, action_method="POST"),
    ):
        with pytest.raises(AutotaskCompanyOutboundOptInError, match="PLAN_MISMATCH"):
            connector.execute_governed_execution(altered)
    transport.concurrent_change = True
    with pytest.raises(AutotaskCompanyOutboundOptInError, match="CONCURRENT_CHANGE"):
        connector.execute_governed_execution(plan)
    assert not any(c[0] == "PATCH" for c in transport.calls)


def test_native_company_update_access_none_blocks_before_post():
    class NativePermissionNone:
        def request(self, **kwargs):
            assert kwargs["method"] == "GET"
            assert kwargs["url"].endswith("/Companies/entityInformation")
            return {"info": {"userAccessForUpdate": "None"}}

    connector = AutotaskCompanyOutboundOptInConnector(
        secrets=_Secrets(), transport=NativePermissionNone(),
        audit=_Audit(), bindings=None,
    )
    with pytest.raises(PermissionError, match="AUTOTASK_REQUESTER_OPERATION_NOT_PERMITTED"):
        connector._preflight_requester_access(
            prepared=PreparedRequest(
                method="PATCH", url="https://psa.example/V1.0/Companies",
                headers={"ImpersonationResourceId": "29682885"},
                json={}, audit_operation="/V1.0/Companies",
            ),
            headers={"ImpersonationResourceId": "29682885"},
            operation=OPERATION,
        )
