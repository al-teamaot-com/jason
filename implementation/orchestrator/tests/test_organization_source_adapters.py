import pytest

from orchestrator.organization_matching import match_organizations
from orchestrator.organization_source_adapters import autotask_company, quickbooks_customer


def test_live_shaped_autotask_company_to_qbo_customer_candidate():
    at = autotask_company({
        "id": 180,
        "companyName": "Freeman Sporting Goods",
        "phone": "(757) 555-0101",
        "address1": "42 Shore Road",
        "postalCode": "23505",
        "webAddress": "https://freemansporting.com",
    }, scope_id="aot")
    qb = quickbooks_customer({
        "Id": "7",
        "DisplayName": "Freeman Sporting Goods",
        "CompanyName": "Freeman Sporting Goods",
        "PrimaryPhone": {"FreeFormNumber": "757-555-0101"},
        "BillAddr": {"Line1": "42 SHORE ROAD", "PostalCode": "23505"},
    }, scope_id="aot")
    result = match_organizations(
        [at], [qb], scope_id="aot",
        left_source="autotask", right_source="quickbooks",
    )
    assert result[0].status == "probable"
    assert result[0].candidates[0].right_id == "7"
    assert at.source_id == "180"
    assert qb.source_id == "7"


def test_qbo_subcustomers_sharing_company_name_are_ambiguous():
    at = autotask_company({"id": 1, "companyName": "Freeman Sporting Goods"}, scope_id="aot")
    customers = [
        quickbooks_customer({"Id": "8", "DisplayName": "0969 Ocean View Road",
                             "CompanyName": "Freeman Sporting Goods"}, scope_id="aot"),
        quickbooks_customer({"Id": "9", "DisplayName": "55 Twin Lane",
                             "CompanyName": "Freeman Sporting Goods"}, scope_id="aot"),
    ]
    result = match_organizations([at], customers, scope_id="aot",
                                 left_source="autotask", right_source="quickbooks")
    assert result[0].status == "ambiguous"
    assert {c.right_id for c in result[0].candidates} == {"8", "9"}


def test_no_hardcoded_aot_scope():
    at = autotask_company({"id": 100, "companyName": "ACME LLC"}, scope_id="msp-other:client-1")
    qb = quickbooks_customer({"Id": "12", "DisplayName": "ACME LLC"}, scope_id="msp-other:client-1")
    result = match_organizations(
        [at], [qb], scope_id="msp-other:client-1",
        left_source="autotask", right_source="quickbooks")
    assert result[0].status == "possible"


def test_missing_ids_fail_closed():
    with pytest.raises(ValueError):
        autotask_company({"companyName": "Unknown"}, scope_id="aot")
    with pytest.raises(ValueError):
        quickbooks_customer({"DisplayName": "Unknown"}, scope_id="aot")


def test_cross_tenant_mixed_inputs_fail_closed():
    at = autotask_company({"id": 1, "companyName": "ACME LLC"}, scope_id="aot")
    qb = quickbooks_customer({"Id": "2", "DisplayName": "ACME LLC"}, scope_id="other")
    with pytest.raises(PermissionError):
        match_organizations([at], [qb], scope_id="aot",
                            left_source="autotask", right_source="quickbooks")
