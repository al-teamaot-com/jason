"""Explicit, read-only adapters from approved provider records to organization identity."""
from __future__ import annotations

from typing import Any, Mapping

from .organization_matching import OrganizationRecord


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _nested(source: Mapping[str, Any], key: str, member: str) -> str:
    row = source.get(key)
    return _str(row.get(member)) if isinstance(row, Mapping) else ""


def _id(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int)):
        return str(value).strip()
    return ""


def autotask_company(record: Mapping[str, Any], *, scope_id: str) -> OrganizationRecord:
    """Adapt Autotask Company read/search evidence without requesting extra data."""
    if not isinstance(record, Mapping):
        raise ValueError("Autotask company must be a record")
    return OrganizationRecord(
        source="autotask",
        source_id=_id(record.get("id")),
        scope_id=scope_id,
        name=_str(record.get("companyName")),
        phone=_str(record.get("phone")),
        email=_str(record.get("email")),
        website=_str(record.get("webAddress")),
        street=_str(record.get("address1")),
        postal_code=_str(record.get("postalCode")),
    )


def quickbooks_customer(record: Mapping[str, Any], *, scope_id: str) -> OrganizationRecord:
    """Adapt QBO Customer; subcustomer display name and company legal name stay distinct."""
    if not isinstance(record, Mapping):
        raise ValueError("QuickBooks customer must be a record")
    display = _str(record.get("DisplayName"))
    company = _str(record.get("CompanyName"))
    return OrganizationRecord(
        source="quickbooks",
        source_id=_id(record.get("Id")),
        scope_id=scope_id,
        name=display or company,
        legal_name=company if company != display else "",
        phone=_nested(record, "PrimaryPhone", "FreeFormNumber"),
        email=_nested(record, "PrimaryEmailAddr", "Address"),
        website=_nested(record, "WebAddr", "URI"),
        street=_nested(record, "BillAddr", "Line1"),
        postal_code=_nested(record, "BillAddr", "PostalCode"),
    )
