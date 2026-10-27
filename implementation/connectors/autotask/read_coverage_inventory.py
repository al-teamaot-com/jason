"""Evidence-driven read coverage inventory; never grants or executes provider access.

Only source-owned known names can be assessed. An entity is not accepted for
generic query merely because it appears in provider metadata or this report.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .operations import APPROVED_AUTOTASK_ENTITIES

# Preserve specialized requester/sensitive-data handling; never infer that
# generic read is safe from the presence of a provider query endpoint.
SPECIALIZED_READ_ENTITIES = frozenset({
    "TimeEntries", "TicketAttachments", "TicketNotes",
    "ProjectAttachments", "Contracts", "TicketCharges",
})
PILOT_GENERIC_ENTITIES = frozenset({
    "Projects", "Tasks", "ServiceCalls", "ProjectNotes",
    "TicketAdditionalConfigurationItems",
})


def assess_coverage(
    *,
    provider_entity_information: Mapping[str, Mapping[str, Any]],
    active_capabilities: set[str] | frozenset[str],
    provider_fields: Mapping[str, list[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build bounded, non-sensitive evidence of remaining read gaps.

    Metadata must be supplied by a separately authorized read operation.
    Missing data is unknown, not 'unsupported' or 'denied'.
    """
    if not isinstance(provider_entity_information, Mapping):
        raise TypeError("provider metadata mapping required")
    if not isinstance(active_capabilities, (set, frozenset)):
        raise TypeError("live active capability set required")
    if provider_fields is not None and not isinstance(provider_fields, Mapping):
        raise TypeError("field metadata mapping required")
    rows: list[dict[str, Any]] = []
    for entity in sorted(APPROVED_AUTOTASK_ENTITIES):
        info = provider_entity_information.get(entity)
        metadata_observed = isinstance(info, Mapping)
        can_query = info.get("canQuery") if metadata_observed else None
        if type(can_query) is not bool:
            can_query = None
        fields = (provider_fields or {}).get(entity)
        known_fields = isinstance(fields, list)
        if known_fields and any(
            not isinstance(field, Mapping) or not isinstance(field.get("name"), str)
            for field in fields
        ):
            raise ValueError("malformed provider field evidence")
        specialized = entity in SPECIALIZED_READ_ENTITIES
        generic_source = entity in PILOT_GENERIC_ENTITIES
        generic_active = (generic_source and
                          {"service.entity.search", "service.entity.read"}.issubset(active_capabilities))
        if can_query is None:
            state = "provider_queryability_unverified"
        elif not can_query:
            state = "provider_reports_not_queryable"
        elif specialized:
            state = "specialized_authorization_review_required"
        elif generic_active:
            state = "generic_registered_requires_live_read_proof"
        elif generic_source:
            state = "generic_source_present_not_active"
        else:
            state = "governed_query_route_gap"
        rows.append({
            "entity": entity,
            "provider_metadata_observed": metadata_observed,
            "provider_can_query": can_query,
            "field_metadata_observed": known_fields,
            "field_count": len(fields) if known_fields else None,
            "specialized_handling": specialized,
            "generic_source_registered": generic_source,
            "generic_capabilities_active": generic_active,
            "assessment": state,
            "live_record_read_verified": False,
            "pagination_verified": False,
            "disclosure_negative_tests_verified": False,
        })
    return {
        "schema_version": "1.0",
        "scope": "source-approved-autotask-entities-only",
        "complete_autotask_api_inventory": False,
        "provider_entity_count": len(rows),
        "rows": rows,
        "unlisted_provider_entities": "not inventoried; discover via authoritative schema separately",
        "note": "No permissions, provider calls, production activation or disclosure granted.",
    }
