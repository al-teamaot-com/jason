"""Regression checks for the versioned evidence-only Autotask coverage reporter."""
from copy import deepcopy

import pytest

from tools.autotask_technician_gap_report import build_report


def inventory():
    return {
        "provider_operations": [{
            "method": "PATCH", "path": "/V1.0/Tickets",
            "operation": "Update ticket",
        }],
        "technician_ui_operations": [{
            "feature_id": "tickets.merge",
            "surface": "ticket.tools",
            "operation": "Merge into another ticket",
        }],
        "entity_metadata": [{
            "entity": "Tickets",
            "evidence_ref": "corr-read-only-autotask",
            "data": {"info": {
                "name": "Ticket",
                "canCreate": True, "canUpdate": True, "canDelete": False, "canQuery": True,
                "userAccessForCreate": "None", "userAccessForUpdate": "None",
                "userAccessForDelete": "None", "userAccessForQuery": "All",
            }},
        }],
    }


def test_correlated_api_and_ui_gap_report_is_non_executable():
    report = build_report(inventory())
    assert report["schema_version"] == 2
    assert report["authority"] == "evidence_only_no_execution"
    update = next(row for row in report["entity_action_matrix"] if row["action"] == "update")
    assert update["status"] == "api_identity_denied"
    assert "autotask.ticket.update" in update["provider_route_names"]
    assert report["findings"][0]["status"] == "registered_provider_route"
    ui = next(row for row in report["findings"] if row["source"] == "technician_ui")
    assert ui["path"] == ""
    assert ui["method"] == "UI"
    assert ui["status"] == "candidate_requires_review"


def test_metadata_delta_is_review_only():
    prior = build_report(inventory())
    updated = inventory()
    updated["entity_metadata"][0]["data"]["info"]["canDelete"] = True
    result = build_report(updated, prior)
    assert [x["action"] for x in result["entity_action_changes"]] == ["delete"]
    assert result["entity_action_changes"][0]["status"] == "candidate_requires_review"


def test_missing_current_snapshot_cannot_count_as_provider_revoke():
    old = build_report(inventory())
    current = deepcopy(inventory())
    current.pop("entity_metadata")
    with pytest.raises(ValueError, match="cannot compare"):
        build_report(current, old)


@pytest.mark.parametrize("wrong", ["invalid", {}, {"entity_metadata": {}}])
def test_invalid_inventory_and_prior_reports_rejected(wrong):
    if wrong == {}:
        with pytest.raises(ValueError, match="prior report"):
            build_report(inventory(), wrong)
    else:
        with pytest.raises(ValueError):
            build_report(wrong)
