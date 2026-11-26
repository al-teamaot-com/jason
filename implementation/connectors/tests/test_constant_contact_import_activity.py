import pytest
from connectors.constant_contact.import_activity import (
    ImportContractError, build_specification, classify_activity,
)
from connectors.constant_contact.import_preflight import preflight

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def preview():
    return preflight([{
        "email": "One@Example.com",
        "marketing_consent": "explicit",
        "consent_evidence": "form receipt",
        "first_name": "One",
    }], suppression_inventory_complete=True)


def test_bound_payload_is_deterministic_and_contains_no_consent_document():
    a = build_specification(preview(), list_ids=[LIST_ID])
    b = build_specification(preview(), list_ids=[LIST_ID, LIST_ID])
    assert a.sha256 == b.sha256
    assert a.contact_count == 1
    assert a.payload == {"import_data": [{"email": "one@example.com", "first_name": "One"}],
                         "list_ids": [LIST_ID]}
    assert "form receipt" not in repr(a.payload)


def test_no_lists_and_unapproved_list_rejected():
    for ids in ([], ["not-a-list"]):
        with pytest.raises(ImportContractError):
            build_specification(preview(), list_ids=ids)


def test_mixed_consent_rejected():
    invalid = preflight([{"email": "x@example.com", "marketing_consent": "unknown"}])
    with pytest.raises(ImportContractError):
        build_specification(invalid, list_ids=[LIST_ID])


def test_activity_completion_always_requires_readback():
    status = classify_activity({
        "activity_id": ACT_ID, "state": "completed", "percent_done": 100,
        "completed_at": "2026-11-09T18:00:00Z", "activity_errors": [],
    }, expected_activity_id=ACT_ID)
    assert status["state"] == "activity_complete_unverified"
    assert status["provider_readback_required"]


def test_activity_errors_and_mismatch_fail_closed():
    errors = classify_activity({
        "activity_id": ACT_ID, "state": "completed", "percent_done": 100,
        "activity_errors": [{"code": "bad"}],
    }, expected_activity_id=ACT_ID)
    assert errors["state"] == "failed"
    with pytest.raises(ImportContractError):
        classify_activity({"activity_id": ACT_ID, "percent_done": 100, "activity_errors": []},
                          expected_activity_id=LIST_ID)


def test_missing_status_stays_unverified():
    status = classify_activity({
        "activity_id": ACT_ID, "state": "nonsense", "percent_done": 100,
        "activity_errors": [],
    }, expected_activity_id=ACT_ID)
    assert status["state"] == "unverified"
