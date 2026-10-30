"""The genuine live Autotask ActionTypes resource has a valid ID 0 row.

Never weaken ticket/Projects positive-ID acceptance to accommodate this
specialized enum-like dynamic resource. These tests are source-only;
they do not fabricate successful production canary receipts.
"""
from jason_mcp.production_read_acceptance import _safe_event

ARGS = {"entity": "ActionTypes", "page_size": 1, "select": ["id", "name"]}


def result(rows, status="succeeded"):
    return {
        "status": status,
        "evidence": {"data": {"items": rows}},
    }


def test_live_actiontype_zero_id_qualifies_for_metadata_only_dynamic_evidence():
    evidence = _safe_event(
        "service.entity.search", ARGS,
        result([{"id": 0, "name": "Actual Autotask Action Type"}]),
    )
    assert evidence == {"kind": "dynamic_schema_search", "items": 1}
    assert "Actual Autotask Action Type" not in str(evidence)


def test_dynamic_evidence_fails_on_negative_boolean_or_noninteger_ids():
    for invalid in (-1, True, False, "0", None, 0.0):
        assert _safe_event(
            "service.entity.search", ARGS,
            result([{"id": invalid, "name": "Not Valid"}]),
        ) is None


def test_dynamic_evidence_requires_selected_name_and_strips_unexpected_fields():
    for row in (
        {"id": 0},
        {"id": 0, "name": None},
        {"id": 0, "name": ""},
        {"id": 0, "name": "  "},
        {"id": 0, "name": "Valid", "description": "unexpected private content"},
        "not an object",
    ):
        assert _safe_event("service.entity.search", ARGS, result([row])) is None


def test_accepted_actiontype_id_zero_is_not_valid_for_project_or_ticket_reads():
    assert _safe_event(
        "service.entity.search", {"entity": "Projects", "page_size": 1},
        result([{"id": 0, "name": "Not a positive Project"}]),
    ) is None
    assert _safe_event(
        "service.ticket.read", {"resource_id": 0},
        result([{"id": 0, "name": "Not a positive ticket"}]),
    ) is None


def test_v13_actiontype_requires_normal_authorized_success_and_exact_shape():
    assert _safe_event(
        "service.entity.search", ARGS,
        result([{"id": 0, "name": "No denied receipt"}], status="denied"),
    ) is None
    assert _safe_event(
        "service.entity.search",
        {**ARGS, "filter": [{"field": "id", "op": "eq", "value": 0}]},
        result([{"id": 0, "name": "Unexpected query shape"}]),
    ) is None
    assert _safe_event(
        "service.entity.search", ARGS,
        result([{"id": 0, "name": "First"}, {"id": 1, "name": "Second"}]),
    ) is None
