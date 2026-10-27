"""Read coverage must be evidence-based, not inferred from source whitelists."""
import pytest

from connectors.autotask.read_coverage_inventory import assess_coverage


def test_unverified_is_never_counted_as_complete():
    report = assess_coverage(provider_entity_information={}, active_capabilities=set())
    assert report["complete_autotask_api_inventory"] is False
    assert len(report["rows"]) > 20
    assert all(row["assessment"] == "provider_queryability_unverified" for row in report["rows"])
    assert all(row["live_record_read_verified"] is False for row in report["rows"])


def test_queryable_entity_without_generic_route_is_gap():
    report = assess_coverage(
        provider_entity_information={"Invoices": {"canQuery": True}},
        active_capabilities={"service.entity.search", "service.entity.read"},
        provider_fields={"Invoices": [{"name": "id"}, {"name": "invoiceNumber"}]},
    )
    item = next(row for row in report["rows"] if row["entity"] == "Invoices")
    assert item["assessment"] == "governed_query_route_gap"
    assert item["field_count"] == 2


def test_sensitive_entities_are_not_auto_added_to_generic_path():
    report = assess_coverage(
        provider_entity_information={"TimeEntries": {"canQuery": True},
                                     "ProjectAttachments": {"canQuery": True}},
        active_capabilities={"service.entity.search", "service.entity.read"},
    )
    for name in ("TimeEntries", "ProjectAttachments"):
        row = next(row for row in report["rows"] if row["entity"] == name)
        assert row["assessment"] == "specialized_authorization_review_required"
        assert row["generic_capabilities_active"] is False


def test_source_registered_not_active_until_release():
    report = assess_coverage(provider_entity_information={"Projects": {"canQuery": True}},
                             active_capabilities=set())
    row = next(row for row in report["rows"] if row["entity"] == "Projects")
    assert row["assessment"] == "generic_source_present_not_active"


@pytest.mark.parametrize("metadata", [{"canQuery": "true"}, {"canQuery": 1}, {}])
def test_provider_queryability_requires_boolean_evidence(metadata):
    report = assess_coverage(provider_entity_information={"Tasks": metadata},
                             active_capabilities=set())
    row = next(row for row in report["rows"] if row["entity"] == "Tasks")
    assert row["provider_can_query"] is None


def test_bad_field_metadata_refused():
    with pytest.raises(ValueError, match="malformed"):
        assess_coverage(provider_entity_information={},
                        active_capabilities=set(),
                        provider_fields={"Projects": [{"wrong": "key"}]})
