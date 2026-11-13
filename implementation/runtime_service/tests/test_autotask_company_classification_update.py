from dataclasses import replace
from datetime import datetime, timezone

import pytest
from connectors.autotask.mutation_connector import AUTOTASK_MUTATION_ENABLED_ENV, AutotaskMutationConnector
from connectors.autotask.operations import resolve_operation_request
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_company_classification_update import (
    CAPABILITY, OPERATION, PROFILE_ENV, PROFILE, PROVIDER, UDF_NAME,
    CompanyClassificationConnector, CompanyClassificationError, _state, enabled,
    register_foundation,
)
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry

ID = 724


def company(kind=3, udf="Prospect"):
    return {"id": ID, "companyName": "OnPoint Building Services", "companyType": kind,
            "userDefinedFields": [{"name": UDF_NAME, "value": udf},
                                  {"name": "Business_Hours", "value": "9 to 5"}]}


def request(kind=3, udf="Prospect", target=1, target_udf="Client", **extra):
    return ConnectorRequest(context=ConnectorContext(
        correlation_id="corr-classify-test", principal_id="person-al",
        organization_id="aot", client_id=None, capability=OPERATION, mode="execute"),
        arguments={"payload": {"company_id": ID, "expected_company_type": kind,
                               "expected_udf": udf, "target_company_type": target,
                               "target_udf": target_udf, **extra}})


class Secrets:
    def resolve(self, *_):
        return {}


class Audit:
    def record(self, *args, **kwargs):
        pass


class Transport:
    def __init__(self):
        self.record = company()
        self.calls = []
        self.change_before_write = False

    def request(self, **kwargs):
        method, url = kwargs["method"], kwargs["url"]
        self.calls.append((method, url, kwargs.get("json")))
        if method == "GET" and url.endswith(f"/Companies/{ID}"):
            if self.change_before_write:
                self.record["userDefinedFields"][1]["value"] = "changed"
            return {"item": dict(self.record)}
        if method == "PATCH" and url.endswith("/Companies"):
            body = kwargs["json"]
            assert set(body) == {"id", "companyType", "userDefinedFields"}
            assert body["id"] == ID
            assert body["userDefinedFields"] == [{"name": UDF_NAME, "value": "Client"}]
            self.record["companyType"] = body["companyType"]
            self.record["userDefinedFields"][0]["value"] = body["userDefinedFields"][0]["value"]
            return {"itemId": ID}
        raise AssertionError(f"unexpected provider request: {method} {url}")


def fake_prepare(self, request, _creds):
    return PreparedRequest(method="PATCH", url="https://psa.example/V1.0/Companies",
                           headers={"ImpersonationResourceId": "29682885"},
                           params=None, json=request.arguments["payload"],
                           audit_operation="/V1.0/Companies")


def connector(monkeypatch, transport):
    monkeypatch.setattr(AutotaskMutationConnector, "prepare_request", fake_prepare)
    return CompanyClassificationConnector(secrets=Secrets(), transport=transport,
                                          audit=Audit(), bindings=None)


def activate(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV, PROFILE)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")


def test_dormant_requires_separate_activation_and_approval(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    c = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    p = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    assert register_foundation(capabilities=c, providers=p, now=datetime.now(timezone.utc)) is False
    item = c.get(capability_name=CAPABILITY, version="1.0")
    assert item.lifecycle_status == CapabilityLifecycle.BUILDING
    assert item.approval.required is True
    assert item.maximum_attempts == 1
    assert enabled() is False
    monkeypatch.setenv(PROFILE_ENV, PROFILE)
    monkeypatch.delenv(AUTOTASK_MUTATION_ENABLED_ENV, raising=False)
    with pytest.raises(CompanyClassificationError, match="MUTATION_DISABLED"):
        enabled()


def test_no_arbitrary_update_payloads_or_invalid_transitions():
    good = request().arguments["payload"]
    assert CompanyClassificationConnector._payload(good) == (ID, 3, "Prospect", 1, "Client")
    for altered in ({**good, "companyName": "A different company"},
                    {**good, "company_id": 0},
                    {**good, "target_company_type": 7},
                    {**good, "target_udf": "Customer"},
                    {**good, "target_company_type": True},
                    {**good, "expected_udf": "Former Client"}):
        with pytest.raises((CompanyClassificationError, ValueError)):
            CompanyClassificationConnector._payload(altered)
    patch = {"id": ID, "companyType": 1,
             "userDefinedFields": [{"name": UDF_NAME, "value": "Client"}]}
    assert resolve_operation_request(OPERATION, {"payload": patch}) == (
        "PATCH", "/V1.0/Companies", None, patch)


def test_duplicate_udf_or_wrong_company_rejected():
    assert _state(company(), ID)[1:3] == (3, "Prospect")
    duplicate = company()
    duplicate["userDefinedFields"].append({"name": UDF_NAME, "value": "Client"})
    with pytest.raises(CompanyClassificationError, match="AMBIGUOUS"):
        _state(duplicate, ID)
    with pytest.raises(CompanyClassificationError, match="ID_MISMATCH"):
        _state(company(), 999)


def test_exact_change_requires_pre_post_readback_and_preserves_udfs(monkeypatch):
    activate(monkeypatch)
    transport = Transport()
    c = connector(monkeypatch, transport)
    plan = c.prepare_governed_execution(request())
    assert plan.resource_identifier == str(ID)
    assert not any(call[0] == "PATCH" for call in transport.calls)
    result = c.execute_governed_execution(plan)
    assert result.data["jasonVerification"] == {
        "readbackVerified": True, "companyType": 1,
        "CW_CompanyType": "Client", "unrelatedUdfsPreserved": True,
    }
    assert transport.record["userDefinedFields"][1]["value"] == "9 to 5"
    assert sum(call[0] == "PATCH" for call in transport.calls) == 1
    assert sum(call[0] == "GET" for call in transport.calls) == 3


def test_stale_state_and_tampered_plans_fail_before_write(monkeypatch):
    activate(monkeypatch)
    transport = Transport()
    c = connector(monkeypatch, transport)
    plan = c.prepare_governed_execution(request())
    for altered in (replace(plan, resource_identifier="999"),
                    replace(plan, payload={**plan.payload, "phone": "555"}),
                    replace(plan, action_method="POST")):
        with pytest.raises(CompanyClassificationError, match="PLAN_MISMATCH"):
            c.execute_governed_execution(altered)
    transport.change_before_write = True
    with pytest.raises(CompanyClassificationError, match="CONCURRENT_CHANGE"):
        c.execute_governed_execution(plan)
    assert not any(call[0] == "PATCH" for call in transport.calls)
