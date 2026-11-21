"""Real Autotask entityInformation shape and fail-closed dynamic coverage proof."""
from copy import deepcopy

import pytest

from implementation.connectors.autotask.entity_feature_matrix import (
    diff_entity_metadata,
    project_entity_metadata,
)


def ticket_metadata():
    return {
        "entity": "Tickets",
        "evidence_ref": "corr-governed-schema-ticket",
        "data": {"info": {
            "name": "Ticket",
            "canCreate": True, "canUpdate": True,
            "canQuery": True, "canDelete": False,
            "userAccessForCreate": "None",
            "userAccessForUpdate": "None",
            "userAccessForQuery": "All",
            "userAccessForDelete": "None",
        }},
    }


def test_live_shape_routes_are_distinct_from_api_user_authority():
    matrix = project_entity_metadata([ticket_metadata()])
    assert [(x["action"], x["status"]) for x in matrix] == [
        ("create", "api_identity_denied"),
        ("delete", "unsupported_by_rest"),
        ("query", "api_identity_all"),
        ("update", "api_identity_denied"),
    ]
    rows = {x["action"]: x for x in matrix}
    assert "autotask.ticket.update" in rows["update"]["provider_route_names"]
    assert "autotask.ticket.create" in rows["create"]["provider_route_names"]
    assert "autotask.ticket.search" in rows["query"]["provider_route_names"]
    assert rows["delete"]["provider_route_names"] == []
    assert all(row["evidence_ref"] == "corr-governed-schema-ticket" for row in matrix)


def test_unknown_rest_entity_is_candidate_without_fabricated_api_route():
    row = ticket_metadata()
    row["entity"] = "TomorrowTickets"
    row["data"]["info"]["name"] = "TomorrowTicket"
    rows = project_entity_metadata([row])
    assert all(not x["provider_route_names"] for x in rows)
    assert [x["status"] for x in rows if x["action"] == "create"] == [
        "api_identity_denied"
    ]


def test_restricted_is_not_treated_as_all_access():
    row = ticket_metadata()
    row["data"]["info"]["userAccessForUpdate"] = "Restricted"
    result = project_entity_metadata([row])
    assert next(x for x in result if x["action"] == "update")["status"] == (
        "api_identity_restricted"
    )


@pytest.mark.parametrize("field,value", [
    ("canUpdate", "true"),
    ("canQuery", 1),
    ("canCreate", None),
    ("userAccessForUpdate", "FULL"),
    ("userAccessForQuery", 0),
    ("userAccessForDelete", None),
])
def test_metadata_flags_fail_closed(field, value):
    row = ticket_metadata()
    row["data"]["info"][field] = value
    with pytest.raises(ValueError):
        project_entity_metadata([row])


@pytest.mark.parametrize("mutation", [
    lambda x: x.pop("data"),
    lambda x: x.update({"evidence_ref": None}),
    lambda x: x.update({"entity": "../Tickets"}),
    lambda x: x["data"].update({"info": {}}),
    lambda x: x["data"]["info"].update({"name": "../Ticket"}),
])
def test_missing_or_injected_metadata_rejected(mutation):
    row = ticket_metadata()
    mutation(row)
    with pytest.raises(ValueError):
        project_entity_metadata([row])


def test_duplicate_or_empty_entity_snapshots_rejected():
    item = ticket_metadata()
    for batch in ([], [item, deepcopy(item)]):
        with pytest.raises(ValueError):
            project_entity_metadata(batch)


def test_detect_feature_and_access_changes_without_promoting():
    before = project_entity_metadata([ticket_metadata()])
    next_metadata = ticket_metadata()
    next_metadata["data"]["info"]["userAccessForUpdate"] = "All"
    next_metadata["data"]["info"]["canDelete"] = True
    after = project_entity_metadata([next_metadata])
    changes = diff_entity_metadata(before, after)
    assert {x["action"] for x in changes} == {"update", "delete"}
    assert all(x["status"] == "candidate_requires_review" for x in changes)
    assert all(x["change"] == "changed" for x in changes)
    assert diff_entity_metadata(after, after) == []


def test_new_entity_is_detected_and_existing_is_preserved():
    before = project_entity_metadata([ticket_metadata()])
    add = ticket_metadata()
    add["entity"] = "FutureRequests"
    add["data"]["info"]["name"] = "FutureRequest"
    after = project_entity_metadata([ticket_metadata(), add])
    changes = diff_entity_metadata(before, after)
    assert len(changes) == 4
    assert all(x["entity"] == "FutureRequests" and x["change"] == "added" for x in changes)


def test_matrix_diff_does_not_accept_duplicate_evidence():
    row = project_entity_metadata([ticket_metadata()])[0]
    with pytest.raises(ValueError, match="duplicate"):
        diff_entity_metadata([row, row], [])


@pytest.mark.parametrize("entity,action,known", [
    ("TicketNotes", "create", "autotask.ticket.note.create"),
    ("TicketNotes", "update", "autotask.ticket.note.update"),
    ("TicketNotes", "query", "autotask.ticket.notes.list"),
    ("TicketCharges", "create", "autotask.ticket.charge.create"),
    ("TicketAttachments", "create", "autotask.ticket.attachment.create"),
    ("TicketAttachments", "query", "autotask.ticket.attachments.list"),
])
def test_existing_nested_provider_routes_are_not_missed(entity, action, known):
    item = ticket_metadata()
    item["entity"] = entity
    item["data"]["info"]["name"] = entity.rstrip("s")
    row = next(x for x in project_entity_metadata([item]) if x["action"] == action)
    assert known in row["provider_route_names"]
    # This is merely a registered route, not a permission grant.
    assert row["status"] == ("api_identity_all" if action == "query" else "api_identity_denied")


def test_unhashable_permission_metadata_rejected_deterministically():
    item = ticket_metadata()
    item["data"]["info"]["userAccessForQuery"] = []
    with pytest.raises(ValueError):
        project_entity_metadata([item])
