"""A future v12 may expand internal read only, never v10/v11 or writes."""
from __future__ import annotations

import json

import pytest

from connectors.autotask.operations import resolve_operation_request
from connectors.autotask.verified_read_extensions import (
    V12_ADDITIONAL_READ_ENTITIES,
    V12_PROFILE,
)
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import SERVICE_ENTITY_READ, SERVICE_ENTITY_SEARCH


@pytest.mark.parametrize("profile", [
    "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10",
    "itglue-autotask-entra-comprehensive-entity-read-catalog-v11",
    "garbage", "",
])
def test_no_v12_entity_is_activated_by_other_read_profile(monkeypatch, profile):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", profile)
    for entity in V12_ADDITIONAL_READ_ENTITIES:
        with pytest.raises(ValueError, match="not yet API-accepted"):
            adapt_autotask_arguments(SERVICE_ENTITY_SEARCH, {"entity": entity, "page_size": 1})
        with pytest.raises(ValueError, match="not approved"):
            resolve_operation_request("autotask.entity.query",
                                      {"entity": entity, "search": '{"filter":[]}'})
    # The five already-approved v11 source entities keep the same adapter path.
    args = adapt_autotask_arguments(SERVICE_ENTITY_SEARCH,
                                   {"entity": "Projects", "page_size": 1})
    assert args["entity"] == "Projects"


@pytest.mark.parametrize("entity", sorted(V12_ADDITIONAL_READ_ENTITIES))
def test_v12_allows_only_bounded_canonical_read_selectors(monkeypatch, entity):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V12_PROFILE)
    req = adapt_autotask_arguments(SERVICE_ENTITY_SEARCH,
                                  {"entity": entity, "page_size": 3})
    query = json.loads(req["search"])
    assert query == {"MaxRecords": 3, "filter": [{"op": "exist", "field": "id"}]}
    method, path, params, body = resolve_operation_request("autotask.entity.query", req)
    assert (method, path, params, body) == (
        "GET", f"/V1.0/{entity}/query", {"search": req["search"]}, None)
    exact = adapt_autotask_arguments(SERVICE_ENTITY_READ,
                                    {"entity": entity, "resource_id": 25})
    assert exact["jason_exact_entity_read_id"] == 25
    get_method, get_path, _, get_body = resolve_operation_request(
        "autotask.entity.get", {"entity": entity, "entity_id": 25})
    assert (get_method, get_path, get_body) == ("GET", f"/V1.0/{entity}/25", None)


@pytest.mark.parametrize("entity", [
    "TimeEntries", "ProjectAttachments", "TicketAttachments",
    "TicketNotes", "ClientPortalUsers", "ContractRates",
    "ContractNotes", "TicketTagAssociations", "CompanySiteConfigurations",
    "InvoiceTemplates", "Invoices", "BillingItems",
    "../Tickets", "Phases/query", "Secrets",
])
def test_v12_refuses_sensitive_unauthorized_or_unproven_generic_names(monkeypatch, entity):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V12_PROFILE)
    with pytest.raises(ValueError, match="not yet API-accepted"):
        adapt_autotask_arguments(SERVICE_ENTITY_SEARCH,
                                {"entity": entity, "page_size": 1})


def test_v12_path_does_not_enable_raw_entity_mutation(monkeypatch):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V12_PROFILE)
    with pytest.raises(ValueError, match="Unsupported capability"):
        resolve_operation_request("autotask.entity.create",
                                  {"entity": "Phases", "payload": {"id": 1}})
    with pytest.raises(ValueError, match="Unsupported capability"):
        resolve_operation_request("autotask.entity.update",
                                  {"entity": "Phases", "payload": {"id": 1}})
    with pytest.raises(ValueError, match="Unsupported capability"):
        resolve_operation_request("autotask.entity.delete", {"entity": "Phases"})


@pytest.mark.parametrize("bad", [
    {"entity": "Phases", "search": '{"filter":[]}'},
    {"entity": "Phases", "page_size": 501},
    {"entity": "Phases", "filters": {"companyID": {"op": "ne", "value": 2}}},
    {"entity": "Phases", "resource_id": 1, "after_resource_id": 3},
])
def test_v12_does_not_bypass_structured_query_bounds(monkeypatch, bad):
    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V12_PROFILE)
    with pytest.raises(ValueError):
        adapt_autotask_arguments(SERVICE_ENTITY_SEARCH, bad)


def test_v12_names_are_proven_in_governed_schema_not_guessed_from_public_index():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    proof = json.loads(
        (root / "docs/operations/Autotask-Live-Schema-Observations-20261027.json").read_text()
    )["entities"]
    for name in V12_ADDITIONAL_READ_ENTITIES:
        assert proof[name]["canQuery"] is True
        assert proof[name]["userAccessForQuery"] == "All"


def test_v12_cross_client_generic_result_not_released_to_customer(monkeypatch):
    from types import SimpleNamespace

    from orchestrator.autotask_information_authorizer import (
        AutotaskImpersonationInformationAuthorizer,
    )
    from orchestrator.information_authorization import (
        FailClosedInformationReleaseAuthorizer,
    )
    from test_autotask_information_authorizer import _Bindings, _Delegate, _request, _resolution

    monkeypatch.setenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", V12_PROFILE)
    monkeypatch.setenv("JASON_AUTOTASK_REQUESTER_AUTH_MODE", "jason_managed")
    output = {"provider": "autotask", "data": {
        "items": [{"id": 101, "companyID": 7, "title": "Test-only fixture"}]}}
    request = _request(SERVICE_ENTITY_SEARCH)
    resolution = _resolution(SERVICE_ENTITY_SEARCH)
    internal = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(output),
        bindings=_Bindings(SimpleNamespace(client_id="14")),
    ).invoke(request=request, resolution=resolution)
    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request, resolution=resolution,
        output=output, authorization=internal.information_authorization,
    )
    assert decision.allowed is False
    assert not decision.output


def test_v12_is_not_the_selected_released_provider_read_profile():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    selected = json.loads((root / "config/autotask-entity-read-profile.json").read_text())["read_profile"]
    assert selected == "itglue-autotask-entra-comprehensive-entity-read-catalog-v11"
    assert selected != V12_PROFILE
