"""No newly observed API or technician UI action can activate itself."""
import pytest

from implementation.connectors.autotask.technician_capability_inventory import discover_gaps


def test_known_operation_is_observed_not_authorized():
    rows = discover_gaps([{
        "method": "PATCH", "path": "/V1.0/Tickets", "operation": "Update ticket"
    }])
    assert len(rows) == 1
    assert rows[0]["status"] == "registered_provider_route"
    assert "authority" in rows[0]["reason"]


def test_new_action_is_candidate_never_executable():
    rows = discover_gaps([{
        "method": "POST", "path": "/V1.0/TicketMerges",
        "operation": "Merge tickets"
    }])
    assert rows[0]["status"] == "candidate_requires_review"


def test_ui_feature_without_matching_api_is_candidate():
    rows = discover_gaps([], technician_ui_operations=[{
        "method": "POST", "path": "/V1.0/TicketMerges",
        "operation": "Merge tickets in technician UI"
    }])
    assert rows[0]["source"] == "technician_ui"
    assert rows[0]["status"] == "candidate_requires_review"


@pytest.mark.parametrize("bad", [
    {"method": "POST", "path": "https://evil.test/V1.0/Tickets", "operation": "x"},
    {"method": "POST", "path": "/V1.0/../Users", "operation": "x"},
    {"method": "POST", "path": "/V1.0/Tickets?url=bad", "operation": "x"},
    {"method": "EXECUTE", "path": "/V1.0/Tickets", "operation": "x"},
])
def test_untrusted_observations_are_rejected(bad):
    with pytest.raises(ValueError):
        discover_gaps([bad])
