from dataclasses import replace

import pytest

from orchestrator.organization_matching import (
    OrganizationRecord, VerifiedOrganizationLink, match_organizations,
)


def at(source_id="100", name="Acme Corporation", **kwargs):
    return OrganizationRecord(
        source="autotask", source_id=source_id, scope_id="aot",
        name=name, **kwargs,
    )


def qb(source_id="9", name="ACME LLC", **kwargs):
    return OrganizationRecord(
        source="quickbooks", source_id=source_id, scope_id="aot",
        name=name, **kwargs,
    )


def match(left, right, **kwargs):
    return match_organizations(left, right, scope_id="aot",
                               left_source="autotask", right_source="quickbooks",
                               **kwargs)


def test_exact_legal_name_not_enough_to_verify():
    result = match([at()], [qb()])[0]
    assert result.status == "possible"
    assert result.candidates[0].score == 55
    assert "name_exact" in result.candidates[0].signals


def test_distinctive_phone_and_name_propose_probable_only():
    result = match([at(phone="757-555-0123")], [qb(phone="+1 (757) 555-0123")])[0]
    assert result.status == "probable"
    assert "phone_exact" in result.candidates[0].signals


def test_address_and_postal_are_independent_evidence():
    result = match(
        [at(street="101 Main Street", postal_code="23505")],
        [qb(street="101 MAIN STREET", postal_code="23505-1234")],
    )[0]
    assert result.status == "probable"
    assert "street_postal_exact" in result.candidates[0].signals


def test_public_email_domain_cannot_raise_confidence():
    result = match([at(email="owner@gmail.com")], [qb(email="different@gmail.com")])[0]
    assert result.status == "possible"
    assert "business_domain_exact" not in result.candidates[0].signals


def test_internal_test_domain_intuit_cannot_raise_confidence():
    result = match([at(email="a@intuit.com")], [qb(email="b@intuit.com")])[0]
    assert result.status == "possible"


def test_business_domain_and_name_can_propose_probable():
    result = match([at(website="https://www.acme-co.example.org")],
                   [qb(email="billing@acme-co.example.org")])[0]
    assert result.status == "possible"  # sample .example.org is not authoritative


def test_competing_customer_records_are_ambiguous():
    result = match([at(phone="7575550101")],
                   [qb("9", phone="7575550101"),
                    qb("10", phone="7575550101")])[0]
    assert result.status == "ambiguous"
    assert len(result.candidates) == 2


def test_same_quickbooks_target_claimed_by_multiple_autotask_companies():
    results = match([at("100", phone="7575550101"), at("101", phone="7575550101")],
                    [qb(phone="7575550101")])
    assert {r.status for r in results} == {"ambiguous"}


def test_unmatched_is_not_invented():
    result = match([at()], [qb(name="Unrelated Furniture")])[0]
    assert result.status == "unmatched"
    assert result.candidates == ()


def test_fuzzy_name_is_only_possible():
    result = match([at(name="Atlantic Office Technologie")],
                   [qb(name="Atlantic Office Technologies")])[0]
    assert result.status == "possible"
    assert "name_similar" in result.candidates[0].signals


def test_verified_link_requires_independent_approval_evidence():
    result = match(
        [at()], [qb()],
        verified_links=[VerifiedOrganizationLink("100", "9", "approval-20261012-1")],
    )[0]
    assert result.status == "verified"
    assert result.candidates[0].signals == ("approved_mapping",)


@pytest.mark.parametrize("links", [
    [VerifiedOrganizationLink("100", "9", "")],
    [VerifiedOrganizationLink("unseen", "9", "approval")],
    [VerifiedOrganizationLink("100", "missing", "approval")],
    [VerifiedOrganizationLink("100", "9", "a"),
     VerifiedOrganizationLink("100", "9", "b")],
])
def test_unapproved_missing_or_duplicate_links_fail_closed(links):
    with pytest.raises(ValueError):
        match([at()], [qb()], verified_links=links)


def test_rejects_cross_tenant_or_cross_provider_records():
    with pytest.raises(PermissionError):
        match([replace(at(), scope_id="other-msp")], [qb()])
    with pytest.raises(PermissionError):
        match([at()], [replace(qb(), source="other-ledger")])


def test_duplicate_provider_identity_fails_closed():
    with pytest.raises(ValueError):
        match([at("100"), at("100")], [qb()])


def test_no_automatic_matching_across_two_provider_instances():
    with pytest.raises(ValueError):
        match_organizations(
            [at()], [qb()], scope_id="aot",
            left_source="autotask", right_source="autotask",
        )


def test_unknown_email_alone_is_not_an_organization_match():
    result = match([at(name="East Office", email="staff@samplebiz.org")],
                   [qb(name="West Office", email="staff@samplebiz.org")])[0]
    assert result.status == "unmatched"


def test_reproducible_score_and_stable_order():
    a = [at("101", name="Acme, Inc", phone="7575550123")]
    b = [qb("9", name="Acme LLC", phone="7575550123")]
    assert match(a, b) == match(a, b)
