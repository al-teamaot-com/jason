"""Dormant preproduction guard for contract-scoped Autotask ContractServices GET.

This module performs no I/O and does not register a capability.  It is an
explicitly scoped proof primitive, not authorization to access ContractServices
under the read-only identity or to broaden dynamic schema queries.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any


def _id(value: object, *, label: str) -> int:
    if type(value) is not int or value < 1:
        raise PermissionError(f"AUTOTASK_CONTRACT_SERVICE_{label}_INVALID")
    return value


def scoped_contract_service_query(
    *,
    contract_id: int,
    expected_company_id: int,
    verified_parent_contract: Mapping[str, Any],
    provider_info: Mapping[str, Any],
    provider_fields: Sequence[Mapping[str, Any]],
    page_size: int = 25,
) -> str:
    """Return the only approved exact-contract query after parent verification.

    The caller must obtain the parent contract through an independently
    authorized governed read and bind its company to the authenticated client's
    canonical company identity. Provider metadata is supplied by the *same*
    execution credential used for the eventual GET; this does not grant a
    standing commercial RW read capability.
    """
    contract = _id(contract_id, label="ID")
    company = _id(expected_company_id, label="COMPANY")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PAGE_LIMIT")
    if not isinstance(verified_parent_contract, Mapping):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_UNVERIFIED")
    if (verified_parent_contract.get("id") != contract
            or verified_parent_contract.get("companyID") != company):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_SCOPE_MISMATCH")
    info = provider_info.get("info", provider_info)
    if not isinstance(info, Mapping) or info.get("canQuery") is not True:
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_QUERY_NOT_SUPPORTED")
    if info.get("userAccessForQuery") not in ("All", "Restricted"):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PROVIDER_DENIED")
    if (not isinstance(provider_fields, (list, tuple))
            or any(not isinstance(f, Mapping) for f in provider_fields)):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_FIELDS_UNVERIFIED")
    fields = {str(f.get("name")): f for f in provider_fields}
    if not all(fields.get(n, {}).get("isQueryable") is True
               for n in ("id", "contractID")):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_SCOPE_FIELD_UNVERIFIED")
    return json.dumps(
        {"filter": [{"op": "eq", "field": "contractID", "value": contract}],
         "MaxRecords": page_size},
        sort_keys=True, separators=(",", ":"),
    )


def verify_contract_service_page(
    *,
    items: object,
    exact_contract_id: int,
    expected_company_id: int,
    verified_parent_contract: Mapping[str, Any],
    max_records: int = 100,
) -> tuple[dict[str, Any], ...]:
    """Return child records only after checking all rows; never leak partials.

    This is a page verifier, not proof that the provider's entire result
    set/pagination was exhausted. The caller must implement a separately
    reviewed bounded continuation strategy and information-release gate.
    """
    contract = _id(exact_contract_id, label="ID")
    company = _id(expected_company_id, label="COMPANY")
    if (not isinstance(verified_parent_contract, Mapping)
            or verified_parent_contract.get("id") != contract
            or verified_parent_contract.get("companyID") != company):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_SCOPE_MISMATCH")
    if type(max_records) is not int or not 1 <= max_records <= 100:
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PAGE_LIMIT")
    if (not isinstance(items, list) or len(items) > max_records
            or any(not isinstance(row, Mapping) for row in items)):
        raise PermissionError("AUTOTASK_CONTRACT_SERVICE_RESPONSE_INVALID")
    verified: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in items:
        record_id = row.get("id")
        if (type(record_id) is not int or record_id < 1
                or record_id in seen or row.get("contractID") != contract):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_ROW_SCOPE_MISMATCH")
        if ("companyID" in row and row["companyID"] != company):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_ROW_COMPANY_MISMATCH")
        seen.add(record_id)
        verified.append(dict(row))
    return tuple(verified)
