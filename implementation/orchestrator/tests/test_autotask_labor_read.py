from __future__ import annotations
import json
from types import SimpleNamespace
import pytest
from connectors.autotask.capability_manifest import build_autotask_manifest
from connectors.autotask.operations import resolve_operation
from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments, GovernedProviderReadConnectorInvoker
from orchestrator.provider_read_capability_catalog import SERVICE_TICKET_TIME_ENTRY_SEARCH

def test_labor_manifest_is_read_only_and_discoverable():
    operations={op.capability_name:op for resource in build_autotask_manifest().resources for op in resource.operations}
    op=operations[SERVICE_TICKET_TIME_ENTRY_SEARCH]
    assert op.read_only is True
    assert op.collection_supported is True
    assert "ticket_id" in op.selector_names

def test_bounded_ticket_labor_query_cannot_be_broad():
    args=adapt_autotask_arguments(SERVICE_TICKET_TIME_ENTRY_SEARCH,{"company_id":827,"ticket_id":143168,"page_size":20})
    assert args["entity"]=="TimeEntries"
    fields=json.loads(args["search"])
    assert fields["MaxRecords"]==20
    assert fields["filter"]==[{"field":"ticketID","op":"eq","value":143168}]
    assert resolve_operation("autotask.entity.query",args)[0:2]==("GET","/V1.0/TimeEntries/query")
    for bad in ({"company_id":827},{"company_id":827,"ticket_id":"143168"},{"company_id":827,"ticket_id":0},{"company_id":827,"ticket_id":143168,"filters":{"id":1}},{"company_id":827,"ticket_id":143168,"search":"{}"},{"company_id":827,"ticket_id":143168,"page_size":501}):
        with pytest.raises(ValueError):
            adapt_autotask_arguments(SERVICE_TICKET_TIME_ENTRY_SEARCH,bad)

def test_time_entry_fails_closed_before_transport_in_jason_managed(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","jason_managed")
    class NoTransport:
        def request(self,**kwargs):
            raise AssertionError("provider I/O prohibited")
    class NoSecret:
        def resolve(self,*args,**kwargs):
            raise AssertionError("credential lookup prohibited")
    from orchestrator.autotask_information_authorizer import AutotaskImpersonationInformationAuthorizer
    from orchestrator.service import InvocationResult
    class Delegate:
        def invoke(self,**kwargs):
            return InvocationResult(output={"data":{"items":[{"id":1,"hoursWorked":4}]}})
    authorizer=AutotaskImpersonationInformationAuthorizer(delegate=Delegate(),bindings=None)
    with pytest.raises(PermissionError,match="PERMISSION_NOT_PROVEN"):
        authorizer.invoke(request=SimpleNamespace(),resolution=SimpleNamespace(selected_provider_id="autotask",capability_name=SERVICE_TICKET_TIME_ENTRY_SEARCH))

class _LaborSecrets:
    def resolve(self, name, context):
        assert name == "autotask.readonly"
        return {"username": "synthetic@example.invalid", "secret": "test-secret", "integration_code": "test-code"}

class _LaborAudit:
    def record(self, *args, **kwargs):
        pass

class _LaborBinding:
    email_address = "technician@example.invalid"

class _LaborBindings:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        return _LaborBinding() if jason_identity_id == "technician" else None

class _LaborTransport:
    def __init__(self, *, ticket_company=827, entries=None):
        self.ticket_company=ticket_company
        self.entries=entries if entries is not None else [{"id": 100, "ticketID": 143168, "resourceID": 29, "hoursWorked": 0.5}]
        self.paths=[]
        self.query_headers=[]
    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
        self.paths.append(url)
        if url.endswith("/v1.0/zoneInformation"):
            return {"url": "https://webservices.example.invalid/atservicesrest/"}
        if url.endswith("/V1.0/Tickets/query"):
            return {"items": [{"id":143168,"companyID":self.ticket_company}]}
        if url.endswith("/V1.0/Resources/query"):
            return {"items": [{"id": 29, "email": "technician@example.invalid", "isActive": True}]}
        if url.endswith("/V1.0/TimeEntries/query"):
            self.query_headers.append(dict(headers))
            return {"items": self.entries}
        raise AssertionError("Unexpected provider route: " + url)

def _time_request(*, company=827, principal="technician"):
    from connectors.core.contracts import ConnectorContext, ConnectorRequest
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="labor-test", principal_id=principal,
            organization_id="aot", client_id=str(company),
            capability="autotask.entity.query", mode="observe",
        ),
        arguments=adapt_autotask_arguments(
            SERVICE_TICKET_TIME_ENTRY_SEARCH,
            {"company_id":company,"ticket_id":143168,"page_size":10},
        ),
    )

def test_labor_native_path_requires_verified_ticket_company(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","impersonated")
    monkeypatch.setenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN","verified")
    transport=_LaborTransport(ticket_company=728)
    connector=AutotaskImpersonatingConnector(
        secrets=_LaborSecrets(), transport=transport, audit=_LaborAudit(), bindings=_LaborBindings(),
    )
    with pytest.raises(PermissionError, match="COMPANY_MISMATCH"):
        connector.execute(_time_request())
    assert not any(p.endswith("/V1.0/TimeEntries/query") for p in transport.paths)

def test_labor_native_path_sets_trusted_requester_and_verifies_rows(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","impersonated")
    monkeypatch.setenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN","verified")
    transport=_LaborTransport()
    connector=AutotaskImpersonatingConnector(
        secrets=_LaborSecrets(), transport=transport, audit=_LaborAudit(), bindings=_LaborBindings(),
    )
    result=connector.execute(_time_request())
    assert result.data["items"][0]["resourceID"]==29
    assert len(transport.query_headers)==1
    assert transport.query_headers[0]["ImpersonationResourceId"]=="29"

def test_labor_native_path_rejects_other_ticket_in_provider_payload(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","impersonated")
    monkeypatch.setenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN","verified")
    transport=_LaborTransport(entries=[{"id":200,"ticketID":143167,"hoursWorked":1}])
    connector=AutotaskImpersonatingConnector(
        secrets=_LaborSecrets(), transport=transport, audit=_LaborAudit(), bindings=_LaborBindings(),
    )
    with pytest.raises(PermissionError,match="RESPONSE_SCOPE_MISMATCH"):
        connector.execute(_time_request())

def test_labor_native_path_denies_unbound_requester(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","impersonated")
    monkeypatch.setenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN","verified")
    transport=_LaborTransport()
    connector=AutotaskImpersonatingConnector(
        secrets=_LaborSecrets(), transport=transport, audit=_LaborAudit(), bindings=_LaborBindings(),
    )
    with pytest.raises(PermissionError,match="TRUSTED_PRINCIPAL_BINDING_REQUIRED"):
        connector.execute(_time_request(principal="unknown"))
    assert not any(p.endswith("/V1.0/TimeEntries/query") for p in transport.paths)

def test_labor_rejects_native_read_without_production_permission_proof(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "impersonated")
    monkeypatch.delenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN", raising=False)
    from orchestrator.autotask_information_authorizer import AutotaskImpersonationInformationAuthorizer
    class Delegate:
        def invoke(self, **kwargs):
            raise AssertionError("Provider must not be called before proof of permissions")
    authorizer=AutotaskImpersonationInformationAuthorizer(delegate=Delegate(),bindings=None)
    with pytest.raises(PermissionError,match="PERMISSION_NOT_PROVEN"):
        authorizer.invoke(
            request=SimpleNamespace(),
            resolution=SimpleNamespace(
                selected_provider_id="autotask",
                capability_name=SERVICE_TICKET_TIME_ENTRY_SEARCH,
            ),
        )

def test_autotask_metadata_supports_arbitrary_valid_entity_and_udf_fields():
    from orchestrator.provider_read_capability_catalog import (
        SERVICE_ENTITY_DESCRIBE, SERVICE_ENTITY_FIELDS_DESCRIBE,
        SERVICE_ENTITY_UDF_FIELDS_DESCRIBE,
    )
    capabilities={op.capability_name:op for resource in build_autotask_manifest().resources for op in resource.operations}
    for cap in (SERVICE_ENTITY_DESCRIBE,SERVICE_ENTITY_FIELDS_DESCRIBE,SERVICE_ENTITY_UDF_FIELDS_DESCRIBE):
        assert capabilities[cap].read_only is True
        assert "entity" in capabilities[cap].selector_names
        request=adapt_autotask_arguments(cap,{"entity":"MyCustomCategory"})
        assert request=={"entity":"MyCustomCategory"}
    assert resolve_operation("autotask.entity.udf.fields.describe",{"entity":"MyCustomCategory"})[0]=="GET"

def test_time_entry_manifest_has_own_discoverable_resource():
    resources={resource.resource_type:resource for resource in build_autotask_manifest().resources}
    assert "service_ticket_time_entry" in resources
    time_resources=resources["service_ticket_time_entry"]
    assert {operation.capability_name for operation in time_resources.operations}=={SERVICE_TICKET_TIME_ENTRY_SEARCH}
    assert all(operation.read_only for operation in time_resources.operations)

def test_labor_rejects_client_context_mismatch_without_provider_io(monkeypatch):
    from dataclasses import replace
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "impersonated")
    monkeypatch.setenv("JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN", "verified")
    transport=_LaborTransport()
    connector=AutotaskImpersonatingConnector(
        secrets=_LaborSecrets(), transport=transport, audit=_LaborAudit(), bindings=_LaborBindings(),
    )
    request=_time_request()
    request=replace(request,context=replace(request.context,client_id="728"))
    with pytest.raises(PermissionError,match="REQUESTER_CLIENT_SCOPE_MISMATCH"):
        connector.execute(request)
    assert transport.paths==[]
