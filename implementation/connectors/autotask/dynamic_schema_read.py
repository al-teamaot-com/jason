"""Source-bound dynamic Autotask GET query gate with live API schema proof.

An Autotask REST entity name is data, not a new capability. The sole governed
service.entity.search/read capability compiles all selectors. Query access and
filter/selection fields must be proven by this exact API account *immediately*
before the provider GET; no public index or stale cached grant can authorize it.
This v13 path is dormant until its immutable activation profile is selected.
"""
from __future__ import annotations

from collections.abc import Mapping
import os
import re
from typing import Any

DYNAMIC_READ_PROFILE = "itglue-autotask-entra-dynamic-schema-read-catalog-v13"
_ENTITY_NAME = re.compile(r"[A-Z][A-Za-z0-9]{1,79}\Z")
_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")

# These existing specialist contracts must not be bypassed with a generic
# service-account query (attachments can carry binary content; labor must
# bind an exact ticket/company). Other entities need no per-entity functions.
_SPECIALIZED_GENERIC_EXCLUSIONS = frozenset({
    "TimeEntries", "TicketCharges",
    "TicketNotes",
})


def dynamic_read_enabled(entity: object) -> bool:
    return bool(
        isinstance(entity, str)
        and _ENTITY_NAME.fullmatch(entity)
        and os.getenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", "").strip()
            == DYNAMIC_READ_PROFILE
    )


def dynamic_generic_entity_eligible(entity: object) -> bool:
    return bool(
        dynamic_read_enabled(entity)
        and entity not in _SPECIALIZED_GENERIC_EXCLUSIONS
        and not entity.endswith(("Attachment", "Attachments"))
    )


# Conditional API access is NOT general permission. Only these child entities
# may enter the exact-parent proof path. Other Restricted entities stay denied.
_CONTRACT_SCOPED_ENTITIES = frozenset({
    "ContractServices", "ContractServiceUnits",
    "ContractServiceBundles", "ContractServiceBundleUnits",
})

_CONTRACT_SCOPED_READ_FIELDS = {
    "ContractServices": frozenset({"id", "contractID", "serviceID"}),
    "ContractServiceUnits": frozenset({"id", "contractID", "contractServiceID", "serviceID", "units", "startDate", "endDate"}),
    "ContractServiceBundles": frozenset({"id", "contractID", "serviceBundleID"}),
    "ContractServiceBundleUnits": frozenset({"id", "contractID", "contractServiceBundleID", "serviceBundleID", "units", "startDate", "endDate"}),
}


def restricted_contract_visible_fields(entity: str) -> frozenset[str]:
    return _CONTRACT_SCOPED_READ_FIELDS.get(entity, frozenset())


def restricted_contract_id(*, entity: str, info: Mapping[str, Any],
                           query: Mapping[str, Any]) -> int | None:
    """Require one exact contract parent; never allow broad Restricted reads."""
    if entity not in _CONTRACT_SCOPED_ENTITIES or (
        info.get("canQuery") is not True
        or info.get("userAccessForQuery") != "Restricted"
    ):
        return None
    selected = query.get("IncludeFields")
    if selected is not None and (
        not isinstance(selected, list) or "contractID" not in selected
        or not set(selected).issubset(restricted_contract_visible_fields(entity))
    ):
        return None
    clauses = query.get("filter")
    if not isinstance(clauses, list):
        return None
    matches = [c for c in clauses if isinstance(c, Mapping)
               and c.get("field") == "contractID"
               and c.get("op") == "eq"
               and type(c.get("value")) is int and c["value"] > 0]
    if len(matches) != 1:
        return None
    return matches[0]["value"]


def proven_queryable_fields(
    *,
    entity: str,
    entity_metadata: Mapping[str, Any],
    field_metadata: Mapping[str, Any],
    query: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Validate v13 GET requests from live metadata, returning field descriptions.

    A queryable field is not necessarily a safe *disclosure*. The distinct
    Jason/JKD-001 source and response authorizers still decide that question.
    """
    if not dynamic_generic_entity_eligible(entity):
        raise PermissionError("AUTOTASK_DYNAMIC_ENTITY_NOT_ACTIVATED_OR_SPECIALIZED")
    info = entity_metadata.get("info", entity_metadata)
    if not isinstance(info, Mapping):
        raise PermissionError("AUTOTASK_DYNAMIC_SCHEMA_UNVERIFIED")
    # Datto REST metadata returns singular entity names (for example
    # ActionType from GET /ActionTypes/entityInformation). The trustworthy
    # route identifier is the strict entity path already sent to the API, not
    # this human/catalog display name. Require a bounded valid metadata name,
    # never falsely demand equal singular/plural spelling.
    metadata_name = info.get("name")
    if (not isinstance(metadata_name, str)
            or not _ENTITY_NAME.fullmatch(metadata_name)
            or info.get("canQuery") is not True
            or (info.get("userAccessForQuery") != "All"
                and restricted_contract_id(entity=entity, info=info, query=query) is None)):
        raise PermissionError("AUTOTASK_DYNAMIC_PROVIDER_QUERY_NOT_AUTHORIZED")
    raw_fields = field_metadata.get("fields")
    if (not isinstance(raw_fields, list) or not 1 <= len(raw_fields) <= 500
            or not all(isinstance(f, Mapping) for f in raw_fields)):
        raise PermissionError("AUTOTASK_DYNAMIC_FIELD_SCHEMA_UNVERIFIED")
    fields: dict[str, Mapping[str, Any]] = {}
    for field in raw_fields:
        name = field.get("name")
        if not isinstance(name, str) or not _FIELD_NAME.fullmatch(name):
            raise PermissionError("AUTOTASK_DYNAMIC_FIELD_SCHEMA_INVALID")
        if name in fields:
            raise PermissionError("AUTOTASK_DYNAMIC_FIELD_SCHEMA_AMBIGUOUS")
        fields[name] = field
    if "id" not in fields or fields["id"].get("isQueryable") is not True:
        raise PermissionError("AUTOTASK_DYNAMIC_ID_NOT_QUERYABLE")
    if set(query) - {"MaxRecords", "filter", "IncludeFields"}:
        raise PermissionError("AUTOTASK_DYNAMIC_QUERY_UNRECOGNIZED_KEYS")
    limit = query.get("MaxRecords")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise PermissionError("AUTOTASK_DYNAMIC_QUERY_LIMIT_INVALID")
    clauses = query.get("filter")
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= 14:
        raise PermissionError("AUTOTASK_DYNAMIC_FILTER_INVALID")
    allowed_ops = frozenset({
        "eq", "noteq", "gt", "gte", "lt", "lte",
        "contains", "beginsWith", "endsWith",
        "exist", "notExist", "in", "notIn",
    })
    def scalar(v: object) -> bool:
        return type(v) in (int, float, bool) or (
            isinstance(v, str) and 0 < len(v.strip()) <= 512
        )
    for clause in clauses:
        if not isinstance(clause, Mapping) or set(clause) - {"field", "op", "value"}:
            raise PermissionError("AUTOTASK_DYNAMIC_FILTER_INVALID")
        field = clause.get("field")
        op = clause.get("op")
        if not isinstance(field, str) or field not in fields or fields[field].get("isQueryable") is not True:
            raise PermissionError("AUTOTASK_DYNAMIC_FILTER_FIELD_NOT_QUERYABLE")
        if op not in allowed_ops:
            raise PermissionError("AUTOTASK_DYNAMIC_FILTER_OPERATOR_NOT_APPROVED")
        value = clause.get("value")
        if op in {"exist", "notExist"}:
            if "value" in clause:
                raise PermissionError("AUTOTASK_DYNAMIC_FILTER_VALUE_INVALID")
        elif op in {"in", "notIn"}:
            if (not isinstance(value, list) or not 1 <= len(value) <= 30
                    or not all(scalar(x) for x in value)):
                raise PermissionError("AUTOTASK_DYNAMIC_FILTER_VALUE_INVALID")
        elif not scalar(value):
            raise PermissionError("AUTOTASK_DYNAMIC_FILTER_VALUE_INVALID")
    selected = query.get("IncludeFields")
    if selected is not None:
        if (not isinstance(selected, list) or not 1 <= len(selected) <= 32
                or "id" not in selected or len(set(map(str, selected))) != len(selected)
                or any(not isinstance(x, str) or x not in fields for x in selected)):
            raise PermissionError("AUTOTASK_DYNAMIC_SELECTED_FIELDS_INVALID")
    return fields
