"""Read coverage is evidence-based; no provider or output grants result."""
import pytest

from connectors.autotask.read_coverage_inventory import assess_coverage


def test_unverified_is_never_complete():
    report = assess_coverage(provider_entity_information={}, active_capabilities=set())
    assert report["complete_autotask_api_inventory"] is False
    assert report["entity_count"] > 20
    assert all(row["assessment"] == "provider_queryability_unverified" for row in report["rows"])
    assert all(not row["live_record_read_verified"] for row in report["rows"])


def test_queryable_with_access_all_but_no_generic_path_is_gap():
    report = assess_coverage(
        provider_entity_information={"Invoices": {"canQuery": True, "userAccessForQuery": "All"}},
        active_capabilities={"service.entity.search", "service.entity.read"},
        provider_fields={"Invoices": [{"name": "id"}, {"name": "invoiceNumber"}]},
    )
    item = next(row for row in report["rows"] if row["entity"] == "Invoices")
    assert item["assessment"] == "governed_query_route_gap"
    assert item["field_count"] == 2


def test_provider_user_denial_overrides_capability_and_queryability():
    report = assess_coverage(
        provider_entity_information={"Invoices": {"canQuery": True, "userAccessForQuery": "None"}},
        active_capabilities={"service.entity.search", "service.entity.read"},
    )
    row = next(row for row in report["rows"] if row["entity"] == "Invoices")
    assert row["assessment"] == "provider_user_query_denied"


@pytest.mark.parametrize("metadata", [{"canQuery": True}, {"canQuery": True, "userAccessForQuery": "unexpected"}])
def test_access_unknown_is_not_a_governed_read_gap_without_proof(metadata):
    report = assess_coverage(provider_entity_information={"Projects": metadata},
                             active_capabilities=set())
    row = next(row for row in report["rows"] if row["entity"] == "Projects")
    assert row["assessment"] == "provider_user_query_access_unverified"


def test_sensitive_entities_are_not_auto_added_to_generic_path():
    report = assess_coverage(
        provider_entity_information={"TimeEntries": {"canQuery": True, "userAccessForQuery": "All"},
                                     "ProjectAttachments": {"canQuery": True, "userAccessForQuery": "All"}},
        active_capabilities={"service.entity.search", "service.entity.read"},
    )
    for name in ("TimeEntries", "ProjectAttachments"):
        row = next(row for row in report["rows"] if row["entity"] == name)
        assert row["assessment"] == "specialized_authorization_review_required"
        assert row["generic_capabilities_active"] is False


def test_source_registered_not_active_until_release():
    report = assess_coverage(provider_entity_information={
        "Projects": {"canQuery": True, "userAccessForQuery": "All"}},
        active_capabilities=set())
    row = next(row for row in report["rows"] if row["entity"] == "Projects")
    assert row["assessment"] == "generic_source_present_not_active"


@pytest.mark.parametrize("metadata", [{"canQuery": "true"}, {"canQuery": 1}, {}])
def test_provider_queryability_requires_boolean_evidence(metadata):
    report = assess_coverage(provider_entity_information={"Tasks": metadata},
                             active_capabilities=set())
    row = next(row for row in report["rows"] if row["entity"] == "Tasks")
    assert row["provider_can_query"] is None


def test_vendor_names_do_not_expand_real_connector_permissions():
    report = assess_coverage(
        provider_entity_information={"ActionTypes": {"canQuery": True, "userAccessForQuery": "All"}},
        active_capabilities={"service.entity.search", "service.entity.read"},
        vendor_documented_entities=("ActionTypes", "Projects"),
    )
    row = next(row for row in report["rows"] if row["entity"] == "ActionTypes")
    assert row["vendor_documented"]
    assert not row["source_connector_entity_registered"]
    assert not row["generic_source_registered"]
    assert row["assessment"] == "governed_query_route_gap"
    assert not row["live_record_read_verified"]


def test_vendor_catalog_does_not_assume_nonqueryable_families():
    report = assess_coverage(
        provider_entity_information={"ContractServiceAdjustments": {
            "canQuery": False, "userAccessForQuery": "None"}},
        active_capabilities=set(),
        vendor_documented_entities=("ContractServiceAdjustments",),
    )
    row = next(row for row in report["rows"] if row["entity"] == "ContractServiceAdjustments")
    assert row["assessment"] == "provider_reports_not_queryable"


@pytest.mark.parametrize("names", [("Tickets", "../Secrets"), ["aot;DROP"], ["Tickets"] * 501, "Tickets"])
def test_invalid_candidate_catalog_is_rejected(names):
    with pytest.raises((TypeError, ValueError)):
        assess_coverage(provider_entity_information={}, active_capabilities=set(),
                        vendor_documented_entities=names)


def test_bad_field_metadata_refused():
    with pytest.raises(ValueError, match="malformed"):
        assess_coverage(provider_entity_information={}, active_capabilities=set(),
                        provider_fields={"Projects": [{"wrong": "key"}]})


def test_existing_named_ticket_read_is_not_misreported_as_missing_route():
    report = assess_coverage(
        provider_entity_information={"Tickets": {"canQuery": True, "userAccessForQuery": "All"}},
        active_capabilities={"service.ticket.read", "service.ticket.search"},
        vendor_documented_entities=["Tickets"],
    )
    ticket = next(row for row in report["rows"] if row["entity"] == "Tickets")
    assert ticket["assessment"] == "named_route_active_requires_live_read_proof"
    assert ticket["named_route_capabilities_active"] == ["service.ticket.search", "service.ticket.read"]
    assert not ticket["live_record_read_verified"]


def test_known_named_routes_are_in_governed_catalog_not_unregistered_strings():
    from connectors.autotask.read_coverage_inventory import NAMED_READ_ROUTES
    from orchestrator.provider_read_capability_catalog import AUTOTASK_CAPABILITIES
    from connectors.autotask.operations import APPROVED_AUTOTASK_ENTITIES

    assert set(NAMED_READ_ROUTES) <= APPROVED_AUTOTASK_ENTITIES
    assert all(
        route in AUTOTASK_CAPABILITIES
        for routes in NAMED_READ_ROUTES.values()
        for route in routes
    )
