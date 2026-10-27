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
