"""Read-all internally / disclose only to trusted AOT principals."""
from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.autotask.operations import APPROVED_AUTOTASK_ENTITIES
from orchestrator.autotask_information_authorizer import (
    AutotaskImpersonationInformationAuthorizer,
)
from orchestrator.information_authorization import (
    FailClosedInformationReleaseAuthorizer,
    InformationHandlingClass,
)
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    SERVICE_ENTITY_READ,
    SERVICE_ENTITY_SEARCH,
)
from test_autotask_information_authorizer import _Bindings, _Delegate, _request, _resolution


@pytest.mark.parametrize("entity", [
    "Projects", "Tasks", "ServiceCalls", "ProjectNotes",
    "TicketAdditionalConfigurationItems",
])
def test_new_canonical_entity_families_are_real_bounded_provider_queries(entity):
    assert entity in APPROVED_AUTOTASK_ENTITIES
    args = adapt_autotask_arguments(
        SERVICE_ENTITY_SEARCH,
        {"entity": entity, "filters": {"companyID": 14}, "page_size": 5},
    )
    query = json.loads(args["search"])
    assert args["entity"] == entity
    assert query["MaxRecords"] == 5
    assert query["filter"] == [{"op": "eq", "field": "companyID", "value": 14}]


def test_entity_search_supports_unscoped_internal_read_with_bounded_pagination():
    result = adapt_autotask_arguments(
        SERVICE_ENTITY_SEARCH, {"entity": "Projects", "page_size": 25,
                                 "after_resource_id": 456},
    )
    search = json.loads(result["search"])
    assert search["MaxRecords"] == 25
    assert search["filter"] == [{"op": "gt", "field": "id", "value": 456}]


def test_exact_entity_read_reuses_query_and_sets_validated_identity():
    result = adapt_autotask_arguments(
        SERVICE_ENTITY_READ, {"entity": "ServiceCalls", "resource_id": 817},
    )
    assert result["jason_exact_entity_read_id"] == 817
    payload = json.loads(result["search"])
    assert payload["MaxRecords"] == 2
    assert payload["filter"] == [{"op": "eq", "field": "id", "value": 817}]
    request = SimpleNamespace(
        context=SimpleNamespace(capability="autotask.entity.query"),
        arguments={"jason_exact_entity_read_id": 817},
    )
    response = SimpleNamespace(data={"items": [{"id": 817, "ticketID": 32}]})
    assert AutotaskImpersonatingConnector._verify_generic_exact_entity_result(
        request, response
    ) is response


@pytest.mark.parametrize("items", [
    [], [{"id": 818}], [{"id": 817}, {"id": 817}],
    [{"id": "not-an-id"}], None,
])
def test_exact_read_refuses_missing_duplicate_or_wrong_provider_record(items):
    request = SimpleNamespace(
        context=SimpleNamespace(capability="autotask.entity.query"),
        arguments={"jason_exact_entity_read_id": 817},
    )
    result = SimpleNamespace(data={"items": items})
    with pytest.raises(PermissionError, match="AUTOTASK_EXACT_ENTITY"):
        AutotaskImpersonatingConnector._verify_generic_exact_entity_result(
            request, result
        )


@pytest.mark.parametrize("entity", [
    "TimeEntries", "TicketAttachments", "TicketNotes", "Contracts",
    "ProjectAttachments", "Secrets", "../Tickets", "Projects/query",
])
def test_generic_query_does_not_bypass_specialized_or_unproven_data_paths(entity):
    with pytest.raises(ValueError, match="not yet API-accepted"):
        adapt_autotask_arguments(
            SERVICE_ENTITY_SEARCH, {"entity": entity, "page_size": 5},
        )


@pytest.mark.parametrize("selectors", [
    {"search": '{"filter":[]}'},
    {"filters": {"companyID": {"op": "ne", "value": 1}}},
    {"filters": {"id;DELETE": 1}},
    {"filters": {"field": ["unexpected"]}},
    {"page_size": 501},
    {"after_resource_id": -1},
    {"resource_id": 1, "after_resource_id": 2},
])
def test_generic_query_never_accepts_raw_or_unbounded_provider_queries(selectors):
    with pytest.raises(ValueError):
        adapt_autotask_arguments(
            SERVICE_ENTITY_SEARCH, {"entity": "Projects", **selectors},
        )


def test_broad_internal_read_and_narrow_disclosure_are_different_decisions(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "jason_managed")
    assert SERVICE_ENTITY_SEARCH in AUTOTASK_CAPABILITIES
    assert SERVICE_ENTITY_READ in AUTOTASK_CAPABILITIES
    output = {"provider": "autotask", "data": {"items": [{"id": 91, "projectName": "Example"}]}}
    request = _request(SERVICE_ENTITY_SEARCH)
    resolution = _resolution(SERVICE_ENTITY_SEARCH)
    internal = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(output), bindings=_Bindings(SimpleNamespace(client_id=None)),
    ).invoke(request=request, resolution=resolution)
    release = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request, resolution=resolution, output=output,
        authorization=internal.information_authorization,
    )
    assert release.allowed is True

    # An authenticated customer binding still permits the provider fetch to
    # be used internally, but cannot receive this cross-customer collection.
    client = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(output),
        bindings=_Bindings(SimpleNamespace(client_id="14")),
    ).invoke(request=request, resolution=resolution)
    denied = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request, resolution=resolution, output=output,
        authorization=client.information_authorization,
    )
    assert denied.allowed is False
    assert denied.output == {}


def test_unverified_aot_requester_cannot_receive_cross_customer_content(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "jason_managed")
    output = {"data": {"items": [{"id": 5, "companyID": 7}]}}
    request = replace(_request(SERVICE_ENTITY_READ), authority_allowed=False)
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(output),
        bindings=_Bindings(SimpleNamespace(client_id=None)),
    ).invoke(request=request, resolution=_resolution(SERVICE_ENTITY_READ))
    release = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request, resolution=_resolution(SERVICE_ENTITY_READ),
        output=output, authorization=invocation.information_authorization,
    )
    assert release.allowed is False


def test_sensitive_read_result_remains_derived_only_not_raw_release(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "jason_managed")
    request = _request(SERVICE_ENTITY_SEARCH)
    resolution = _resolution(SERVICE_ENTITY_SEARCH)
    output = {"provider": "autotask", "data": {"items": [{
        "id": 41, "password": "not-a-real-secret",
    }]}}
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(output),
        bindings=_Bindings(SimpleNamespace(client_id=None)),
    ).invoke(request=request, resolution=resolution)
    assert invocation.information_authorization.handling_class is InformationHandlingClass.DERIVED_OUTPUT_ONLY
    assert not FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request, resolution=resolution, output=output,
        authorization=invocation.information_authorization,
    ).allowed
