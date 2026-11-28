"""Do not duplicate or weaken #2144's promoted-note / handoff boundaries."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from implementation.connectors.autotask.existing_ticket_workflows import (
    action_reuse_index, inventory_ticket_workflows,
)
from tools.autotask_technician_gap_report import build_report

REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "autonomous_remediation" / "playbook_registry.json"
)


def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_existing_note_and_handoff_registration_are_reused_without_owner_promotion():
    source = inventory_ticket_workflows(registry())
    by_id = {item["playbook_id"]: item for item in source}
    notes = by_id["unsupported_readonly_triage_note"]
    handoff = by_id["unsupported_triage_human_review"]
    assert set(notes["ticket_capabilities"]) == {
        "service.ticket.note.create", "service.ticket.note.update",
    }
    assert handoff["ticket_capabilities"] == ["service.ticket.update"]
    for item in (notes, handoff):
        assert item["version"] == "1.0.0"
        assert item["pilot_ticket_ids"] == [143305, 143272]
        assert item["source_review_status"] == "pilot_registered_not_owner_promoted"
        assert item["status"] == "source_registered_promotion_unverified"
        assert item["live_promotion_verified"] is False
        assert "exact_owner_promotion" in item["required_gates"]
    assert "verified_internal_investigation_note" in handoff["required_gates"]
    assert "duplicate_suppression" in notes["required_gates"]
    assert set(action_reuse_index(source)["service.ticket.note.update"]) >= {
        "unsupported_readonly_triage_note"
    }


def test_all_existing_ticket_workflows_are_inventoried_without_granting_authority():
    rows = inventory_ticket_workflows(registry())
    assert len(rows) >= 2
    assert all(row["status"] == "source_registered_promotion_unverified" for row in rows)
    assert all(row["live_promotion_verified"] is False for row in rows)
    assert "service.ticket.update" in action_reuse_index(rows)
    assert "service.ticket.note.create" in action_reuse_index(rows)
    assert "service.ticket.merge" not in action_reuse_index(rows)


def test_merge_ui_remains_separate_candidate_not_a_ticket_update_equivalent():
    inventory = {
        "technician_ui_operations": [{
            "feature_id": "ticket.merge.into", "surface": "ticket.tools",
            "operation": "Merge Into Another Ticket",
        }],
    }
    report = build_report(inventory, workflow_registry=registry())
    assert report["workflow_registry_supplied"] is True
    assert report["authority"] == "evidence_only_no_execution"
    assert report["findings"][0]["status"] == "candidate_requires_review"
    assert report["findings"][0]["method"] == "UI"
    assert report["findings"][0]["path"] == ""
    assert "service.ticket.update" in report["existing_ticket_action_reuse"]
    assert "service.ticket.merge" not in report["existing_ticket_action_reuse"]


def test_missing_registry_stays_unverified_not_implicitly_empty_coverage():
    report = build_report({"provider_operations": []})
    assert report["workflow_registry_supplied"] is False
    assert report["source_registered_ticket_workflows"] == []


def test_duplicate_playbook_id_rejected():
    d = registry()
    d["playbooks"].append(deepcopy(d["playbooks"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        inventory_ticket_workflows(d)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"schema_version": 99}),
    lambda d: d.update({"playbooks": []}),
    lambda d: d["playbooks"][0].update({"id": "../../admin"}),
    lambda d: d["playbooks"][0]["autonomy"].update({"policy_id": "playbook-autonomy:all"}),
    lambda d: d["playbooks"][0]["autonomy"].update({"pilot_ticket_ids": [0]}),
    lambda d: d["playbooks"][0]["autonomy"].update({"allowed_capabilities": [123]}),
])
def test_malformed_registry_fails_closed(mutate):
    d = registry()
    mutate(d)
    with pytest.raises(ValueError):
        inventory_ticket_workflows(d)
