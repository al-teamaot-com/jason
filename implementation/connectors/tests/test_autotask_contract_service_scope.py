"""Fail-closed preproduction ContractServices guards; no provider network calls."""
from __future__ import annotations

import json
import pytest

from connectors.autotask.contract_service_scope import (
    scoped_contract_service_query,
    verify_contract_service_page,
)


PARENT = {"id": 101, "companyID": 32}
FIELDS = [
    {"name": "id", "isQueryable": True},
    {"name": "contractID", "isQueryable": True},
    {"name": "unitCost", "isQueryable": False},
]
INFO = {"info": {"canQuery": True, "userAccessForQuery": "Restricted"}}


def plan(**overrides):
    d = dict(contract_id=101, expected_company_id=32,
             verified_parent_contract=PARENT, provider_info=INFO,
             provider_fields=FIELDS, page_size=25)
    d.update(overrides)
    return scoped_contract_service_query(**d)


def page(**overrides):
    d = dict(items=[{"id": 4, "contractID": 101, "unitCost": 8.5}],
             exact_contract_id=101, expected_company_id=32,
             verified_parent_contract=PARENT)
    d.update(overrides)
    return verify_contract_service_page(**d)


def test_exact_scope_and_restricted_provider_metadata_compile_only_one_contract():
    compiled = json.loads(plan())
    assert compiled == {
        "MaxRecords": 25,
        "filter": [{"field": "contractID", "op": "eq", "value": 101}],
    }


@pytest.mark.parametrize("bad_parent", [
    None, {}, {"id": 101}, {"companyID": 32},
    {"id": 101, "companyID": 33},
    {"id": 102, "companyID": 32},
])
def test_mismatched_parent_fails_before_any_query(bad_parent):
    with pytest.raises(PermissionError):
        plan(verified_parent_contract=bad_parent)


@pytest.mark.parametrize("access", ["None", "Mine", None, "", "unknown"])
def test_unapproved_provider_query_scope_denied(access):
    with pytest.raises(PermissionError, match="PROVIDER_DENIED"):
        plan(provider_info={"info": {"canQuery": True,
                                     "userAccessForQuery": access}})


@pytest.mark.parametrize("size", [0, -1, 101, 1.5, True])
def test_query_pagination_is_bounded(size):
    with pytest.raises(PermissionError):
        plan(page_size=size)


def test_missing_queryable_contract_id_is_denied():
    with pytest.raises(PermissionError, match="SCOPE_FIELD_UNVERIFIED"):
        plan(provider_fields=[FIELDS[0], {"name": "contractID", "isQueryable": False}])


def test_provider_cannot_query_is_denied():
    with pytest.raises(PermissionError, match="QUERY_NOT_SUPPORTED"):
        plan(provider_info={"info": {"canQuery": False,
                                     "userAccessForQuery": "All"}})


def test_all_rows_verified_before_return_and_cost_not_modified():
    rows = page(items=[{"id": 1, "contractID": 101, "unitCost": 2.5},
                       {"id": 2, "contractID": 101, "unitCost": 6.0}])
    assert [r["unitCost"] for r in rows] == [2.5, 6.0]
    assert isinstance(rows, tuple)


@pytest.mark.parametrize("rows", [
    [{"id": 1, "contractID": 102}],
    [{"id": 1, "contractID": 101},
     {"id": 2, "contractID": 102}],
    [{"id": 1, "contractID": 101, "companyID": 33}],
    [{"id": 1, "contractID": 101}, {"id": 1, "contractID": 101}],
    [{"contractID": 101}],
    [{"id": True, "contractID": 101}],
    [None],
    {"items": []},
])
def test_wrong_cross_client_or_malformed_page_never_releases_partial_records(rows):
    with pytest.raises(PermissionError):
        page(items=rows)


def test_parent_context_must_remain_bound_during_postread():
    with pytest.raises(PermissionError, match="PARENT_SCOPE_MISMATCH"):
        page(verified_parent_contract={"id": 101, "companyID": 99})


def test_empty_page_is_valid_but_does_not_claim_pagination_complete():
    assert page(items=[]) == ()


def test_full_page_bound_enforced():
    with pytest.raises(PermissionError, match="RESPONSE_INVALID"):
        page(items=[{"id": x, "contractID": 101} for x in range(1, 102)])


def test_no_provider_or_credential_facilities_in_pure_scope_guard():
    # Pure module intentionally cannot retrieve credentials or dispatch I/O.
    from connectors.autotask import contract_service_scope as module
    assert not any(hasattr(module, attr) for attr in (
        "UrlLibJsonHttpTransport", "OpenBaoSecretResolver", "requests",
        "execute", "api_key", "secret",
    ))
