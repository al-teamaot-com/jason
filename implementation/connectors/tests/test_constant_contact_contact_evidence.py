import pytest

from connectors.constant_contact.contact_evidence import (
    ProviderContactEvidenceError, evaluate_exact_contact_lookup,
    verify_imported_membership,
)

LIST = "11111111-2222-3333-4444-555555555555"


def response(permission="explicit", email="one@example.com", lists=None):
    return {"contacts": [{"email_address": {"address": email, "permission_to_send": permission},
                           "list_memberships": lists if lists is not None else [LIST]}],
            "_links": {}}


def test_matching_active_contact_and_membership():
    record = evaluate_exact_contact_lookup(expected_email="ONE@example.com", response=response())
    assert record.safe_for_import
    assert record.list_memberships == (LIST,)
    assert verify_imported_membership(expected_email="one@example.com",
                                      expected_list_ids=[LIST], response=response())


@pytest.mark.parametrize("status", ["unsubscribed", "temp_hold", "not_set", "deleted", "unknown"])
def test_not_safe_to_import_or_count_as_verified(status):
    record = evaluate_exact_contact_lookup(expected_email="one@example.com",
                                           response=response(permission=status))
    assert not record.safe_for_import
    assert not verify_imported_membership(expected_email="one@example.com",
                                          expected_list_ids=[LIST],
                                          response=response(permission=status))


def test_absent_contact_does_not_prove_import_completion():
    result = evaluate_exact_contact_lookup(expected_email="one@example.com",
                                           response={"contacts": [], "_links": {}})
    assert not result.exists
    assert result.safe_for_import
    assert not verify_imported_membership(expected_email="one@example.com",
                                          expected_list_ids=[LIST],
                                          response={"contacts": [], "_links": {}})


@pytest.mark.parametrize("payload", [
    {"contacts": [], "_links": {"next": {"href": "/v3/contacts?cursor=next"}}},
    {"contacts": [{"email_address": {"address": "other@example.com"}}], "_links": {}},
    {"contacts": [{"email_address": {"address": "one@example.com", "permission_to_send": "explicit"}}],
     "_links": {}},
    {"contacts": [1, 2], "_links": {}},
])
def test_incomplete_ambiguous_or_missing_evidence_refused(payload):
    with pytest.raises(ProviderContactEvidenceError):
        evaluate_exact_contact_lookup(expected_email="one@example.com", response=payload)
