"""One generic provider-schema query, not one function for each Autotask entity.

All provider responses are fixtures; network disabled by fake transport.
No production activation, credentials or data writes.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from connectors.autotask.dynamic_schema_read import (
    DYNAMIC_READ_PROFILE, dynamic_generic_entity_eligible,
    proven_queryable_fields,
)
from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.autotask.operations import resolve_operation_request
from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
)
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import (
    SERVICE_ENTITY_READ, SERVICE_ENTITY_SEARCH,
)


class Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == "autotask.readonly"
        return {
            "username": "synthetic@invalid.example",
            "integration_code": "synthetic-only",
            "secret": "synthetic-only",
        }


class Audit:
    def record(self, *args, **kwargs):
        pass


class Transport:
    def __init__(self):
        self.requests = []
        self.access = "All"
        self.queryable = True
        self.fields = [
            {"name": "id", "isQueryable": True},
            {"name": "name", "isQueryable": True},
            {"name": "createdDate", "isQueryable": True},
            {"name": "internalValue", "isQueryable": False},
        ]

    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
        assert method == "GET"
        self.requests.append((url,params))
        if url.endswith("/v1.0/zoneInformation"):
            return {"url":"https://webservices3.autotask.net/atservicesrest"}
        entity = url.split("/V1.0/")[-1].split("/")[0]
        if url.endswith("/entityInformation"):
            return {"info":{
                "name":entity, "canQuery":self.queryable,
                "userAccessForQuery":self.access,
            }}
        if url.endswith("/entityInformation/fields"):
            return {"fields": self.fields}
        if url.endswith("/query"):
            return {"items":[
                {"id":23,"name":"Visible","createdDate":"2026-10-28",
                 "internalValue":"SHOULD_NOT_RETURN_WHEN_PROJECTED"},
            ]}
        raise AssertionError("unexpected provider route: "+url)


@pytest.fixture(autouse=True)
def v13(monkeypatch):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE",DYNAMIC_READ_PROFILE)
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE","jason_managed")


def context(capability="autotask.entity.query", **kw):
    return ConnectorContext(
        correlation_id="test-dynamic-AOT", principal_id=kw.get("principal_id","person-al"),
        organization_id=kw.get("organization_id","aot"),
        client_id=kw.get("client_id"), capability=capability, mode=kw.get("mode","observe"),
    )


def request(entity="ActionTypes", *, read=False, **args):
    operation=SERVICE_ENTITY_READ if read else SERVICE_ENTITY_SEARCH
    selectors={"entity":entity,**args}
    adapted=adapt_autotask_arguments(operation,selectors)
    return ConnectorRequest(context=context(),arguments=adapted)


def connector(transport):
    return AutotaskImpersonatingConnector(
        secrets=Secrets(),transport=transport,audit=Audit()
    )


def test_arbitrary_provider_entity_uses_same_single_dynamic_route_with_live_metadata():
    for entity in ("ActionTypes","Appointments","TaxRegions","TicketHistory","CompanyToDos"):
        transport=Transport()
        r=connector(transport).execute(request(entity,filters={"name":{"op":"contains","value":"Vis"}},page_size=5))
        assert r.data["items"][0]["id"]==23
        assert len(transport.requests)==4
        assert transport.requests[1][0].endswith(f"/{entity}/entityInformation")
        assert transport.requests[2][0].endswith(f"/{entity}/entityInformation/fields")
        url,params=transport.requests[3]
        assert url.endswith(f"/{entity}/query")
        assert json.loads(params["search"])=={"MaxRecords":5,"filter":[
            {"field":"name","op":"contains","value":"Vis"}
        ]}


def test_select_only_requested_fields_even_if_provider_ignores_include_fields():
    transport=Transport()
    r=connector(transport).execute(request(select=["name"],page_size=1))
    assert r.data["items"]==[{"id":23,"name":"Visible"}]
    raw=json.loads(transport.requests[-1][1]["search"])
    assert raw["IncludeFields"]==["id","name"]
    assert "internalValue" not in json.dumps(r.data)


def test_exact_id_generic_read_preserves_unique_proven_readback():
    transport=Transport()
    r=connector(transport).execute(request(resource_id=23,read=True,select=["name"]))
    assert r.data["items"]==[{"id":23,"name":"Visible"}]
    query=json.loads(transport.requests[-1][1]["search"])
    assert query["MaxRecords"]==2
    assert query["filter"]==[{"field":"id","op":"eq","value":23}]


def test_live_metadata_denial_refuses_query_before_record_content_is_requested():
    t=Transport()
    t.access="None"
    with pytest.raises(PermissionError,match="QUERY_NOT_AUTHORIZED"):
        connector(t).execute(request())
    assert len(t.requests)==2
    assert not any(url.endswith("/query") for url,_ in t.requests)


@pytest.mark.parametrize("access", ["Restricted","Mine",None,"unknown"])
def test_restricted_or_ambiguous_provider_rights_fail_closed(access):
    t=Transport()
    t.access=access
    with pytest.raises(PermissionError, match="QUERY_NOT_AUTHORIZED"):
        connector(t).execute(request("Appointments"))
    assert not any(url.endswith("/query") for url,_ in t.requests)


@pytest.mark.parametrize("entity", ["TimeEntries","TicketAttachments","TaskAttachments","TicketCharges","TicketNotes","../../secrets","ClientPortalUsers/query"])
def test_specialized_or_noncanonical_entity_cannot_use_generic_path(entity):
    with pytest.raises(ValueError,match="not yet API-accepted"):
        request(entity)
    assert not dynamic_generic_entity_eligible(entity)


def test_query_field_must_be_actually_queryable_in_live_api_schema():
    t=Transport()
    with pytest.raises(PermissionError,match="FILTER_FIELD_NOT_QUERYABLE"):
        connector(t).execute(request(filters={"internalValue":123}))
    assert len(t.requests)==3


def test_unknown_field_or_provider_malformed_schema_is_refused():
    t=Transport()
    with pytest.raises(PermissionError,match="FILTER_FIELD_NOT_QUERYABLE"):
        connector(t).execute(request(filters={"unrecognizedField":123}))
    assert len(t.requests)==3
    t=Transport()
    t.fields=[{"name":"id","isQueryable":False}]
    with pytest.raises(PermissionError,match="ID_NOT_QUERYABLE"):
        connector(t).execute(request())


@pytest.mark.parametrize("context_override",[
    {"client_id":"customer-14"}, {"organization_id":"another-org"},
    {"principal_id":"svc-jason"}, {"mode":"execute"},
])
def test_dynamic_generic_cross_client_or_service_not_authorized(context_override):
    t=Transport()
    req=request()
    r=ConnectorRequest(context=context(**context_override),arguments=req.arguments)
    with pytest.raises((PermissionError, ConnectorAuthorizationError)):
        connector(t).execute(r)
    assert not any(url.endswith("/query") for url,_ in t.requests)


def test_even_bare_provider_call_with_dynamic_name_and_raw_search_fails():
    t=Transport()
    r=ConnectorRequest(
        context=context(), arguments={"entity":"TaxRegions",
             "search":'{"MaxRecords":1,"filter":[{"field":"id","op":"exist"}]}'}
    )
    with pytest.raises(PermissionError,match="CANONICAL_SELECTOR"):
        connector(t).execute(r)
    assert not any(url.endswith("/query") for url,_ in t.requests)


def test_dormant_legacy_profile_does_not_accept_new_entity(monkeypatch):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE",
                       "itglue-autotask-entra-comprehensive-entity-read-catalog-v11")
    with pytest.raises(ValueError,match="not yet API-accepted"):
        request("ActionTypes")
    with pytest.raises(ValueError,match="not approved"):
        resolve_operation_request("autotask.entity.query",{
            "entity":"ActionTypes","search":'{"filter":[]}'
        })


def test_unknown_mutation_remains_unregistered_in_dynamically_enabled_profile():
    for operation in ("autotask.entity.create","autotask.entity.update","autotask.entity.delete"):
        with pytest.raises(ValueError,match="Unsupported capability"):
            resolve_operation_request(operation,{"entity":"ActionTypes","payload":{"id":23}})


def test_filter_operator_and_pagination_compile_dynamically():
    args=adapt_autotask_arguments(SERVICE_ENTITY_SEARCH,{
        "entity":"ActionTypes","filters":{
            "name":{"op":"beginsWith","value":"A"},
            "createdDate":{"op":"gte","value":"2026-01-01"},
        },"after_resource_id":45,"page_size":100,
        "select":["name","createdDate"],
    })
    search=json.loads(args["search"])
    assert search["MaxRecords"]==100
    assert search["IncludeFields"]==["id","name","createdDate"]
    assert search["filter"]==[
        {"field":"name","op":"beginsWith","value":"A"},
        {"field":"createdDate","op":"gte","value":"2026-01-01"},
        {"field":"id","op":"gt","value":45},
    ]


@pytest.mark.parametrize("filters",[
    {"name":{"op":"eval","value":"x"}},
    {"name":{"op":"contains","value":"x"*513}},
    {"name":{"op":"in","value":list(range(31))}},
    {"name":{"op":"contains","value":{"raw":"x"}}},
])
def test_raw_query_or_unsupported_filter_is_rejected_before_provider(filters):
    with pytest.raises(ValueError):
        request(filters=filters)


def test_provider_live_schema_is_rechecked_each_call_not_cached():
    t=Transport()
    c=connector(t)
    c.execute(request("ActionTypes"))
    t.access="None"
    with pytest.raises(PermissionError,match="QUERY_NOT_AUTHORIZED"):
        c.execute(request("ActionTypes"))
    assert sum(1 for url,_ in t.requests if url.endswith("/entityInformation"))==2
    assert sum(1 for url,_ in t.requests if url.endswith("/query"))==1


def test_api_reports_not_queryable_refuses_record_get():
    t=Transport()
    t.queryable=False
    with pytest.raises(PermissionError,match="QUERY_NOT_AUTHORIZED"):
        connector(t).execute(request("TaxRegions"))
    assert not any(url.endswith("/query") for url,_ in t.requests)


def test_customer_bound_disclosure_is_denied_even_if_provider_api_returns_records():
    from types import SimpleNamespace
    from orchestrator.autotask_information_authorizer import (
        AutotaskImpersonationInformationAuthorizer,
    )
    from orchestrator.information_authorization import (
        InformationAction,
    )
    from orchestrator.tests.test_autotask_information_authorizer import (
        _Bindings, _Delegate, _request, _resolution,
    )
    from orchestrator.provider_read_capability_catalog import SERVICE_ENTITY_SEARCH
    result = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate({"provider":"autotask","data":{
            "items":[{"id":23,"companyID":14,"name":"private-client-data"}],
        }}),
        bindings=_Bindings(SimpleNamespace(client_id="14")),
    ).invoke(
        request=_request(SERVICE_ENTITY_SEARCH),
        resolution=_resolution(SERVICE_ENTITY_SEARCH),
    )
    decision=result.information_authorization.require_allowed(InformationAction.RELEASE)
    assert decision.allowed is False
