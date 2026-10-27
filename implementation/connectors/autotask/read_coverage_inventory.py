"""Evidence-driven Autotask REST read coverage assessment (no provider calls).

Publicly documented entity names, source connector coverage, provider metadata,
and requester disclosure are separate facts. A name in a public index NEVER
gives the running application the authority to query it or release its data.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
import re
from typing import Any

from .operations import APPROVED_AUTOTASK_ENTITIES

_SPECIALIZED_READ_ENTITIES = frozenset({
    "TimeEntries", "TicketAttachments", "TicketNotes",
    "ProjectAttachments", "Contracts", "TicketCharges",
})
_PILOT_GENERIC_ENTITIES = frozenset({
    "Projects", "Tasks", "ServiceCalls", "ProjectNotes",
    "TicketAdditionalConfigurationItems",
})
_ENTITY_NAME = re.compile(r"[A-Z][A-Za-z0-9]{1,79}\Z")

# Existing explicit canonical read routes (validated against the live MCP
# registry) must not be misreported as missing just because the newer generic
# service.entity.{search,read} path is not active.
NAMED_READ_ROUTES = {
    "Tickets": ("service.ticket.search", "service.ticket.read"),
    "Companies": ("service.company.search", "service.company.read"),
    "Contacts": ("service.contact.search", "service.contact.read"),
    "ConfigurationItems": ("service.configuration.search", "service.configuration.read"),
    "Invoices": ("service.invoice.search", "service.invoice.read"),
    "BillingItems": ("service.billing.item.search", "service.billing.item.read"),
    "Quotes": ("service.quote.search", "service.quote.read"),
    "PurchaseOrders": ("service.purchase.order.search", "service.purchase.order.read"),
    "PurchaseOrderItems": ("service.purchase.order.item.search",),
    "Products": ("service.product.search", "service.product.read"),
    "InventoryItems": ("service.inventory.item.search",),
    "ProductVendors": ("service.product.vendor.search",),
    "Services": ("service.service.search", "service.service.read"),
    "ServiceBundles": ("service.service.bundle.search", "service.service.bundle.read"),
    "Contracts": ("service.contract.search", "service.contract.read"),
    "Resources": ("service.resource.search", "service.resource.read"),
    "Opportunities": ("service.opportunity.search", "service.opportunity.read"),
    "NotificationHistory": ("service.notification.history.search",),
    "TicketNotes": ("service.ticket.notes.search",),
    "TimeEntries": ("service.ticket.time.entry.search",),
    "TicketCharges": ("service.ticket.charge.search", "service.ticket.charge.read"),
    "TicketAttachments": ("service.ticket.attachment.search", "service.ticket.attachment.read"),
}


def assess_coverage(
    *,
    provider_entity_information: Mapping[str, Mapping[str, Any]],
    active_capabilities: set[str] | frozenset[str],
    provider_fields: Mapping[str, list[Mapping[str, Any]]] | None = None,
    vendor_documented_entities: Collection[str] = (),
) -> dict[str, Any]:
    """Return a conservative, metadata-only map of candidate Autotask read gaps.

    Caller supplies actual authorized schema/field read evidence, independently
    of this pure assessment. Missing evidence remains unknown; no guesses.
    """
    if not isinstance(provider_entity_information, Mapping):
        raise TypeError("provider metadata mapping required")
    if not isinstance(active_capabilities, (set, frozenset)):
        raise TypeError("live active capability set required")
    if provider_fields is not None and not isinstance(provider_fields, Mapping):
        raise TypeError("field metadata mapping required")
    if isinstance(vendor_documented_entities, (str, bytes)):
        raise TypeError("vendor entities must be a collection of names")
    vendor_names = set(vendor_documented_entities)
    if len(vendor_documented_entities) > 500 or len(vendor_names) > 500 or any(
        not isinstance(name, str) or not _ENTITY_NAME.fullmatch(name)
        for name in vendor_names
    ):
        raise ValueError("invalid or over-broad vendor candidate name list")
    entities = sorted(APPROVED_AUTOTASK_ENTITIES | vendor_names)
    if len(entities) > 500:
        raise ValueError("entity inventory size exceeds review bound")

    rows: list[dict[str, Any]] = []
    for entity in entities:
        info = provider_entity_information.get(entity)
        metadata_observed = isinstance(info, Mapping)
        can_query = info.get("canQuery") if metadata_observed else None
        if type(can_query) is not bool:
            can_query = None
        raw_access = info.get("userAccessForQuery") if metadata_observed else None
        access = (
            raw_access if isinstance(raw_access, str) and raw_access in
            {"All", "Mine", "Restricted", "None"} else None
        )
        fields = (provider_fields or {}).get(entity)
        known_fields = isinstance(fields, list)
        if known_fields and any(
            not isinstance(field, Mapping) or not isinstance(field.get("name"), str)
            for field in fields
        ):
            raise ValueError("malformed provider field evidence")

        specialized = entity in _SPECIALIZED_READ_ENTITIES
        generic_source = entity in _PILOT_GENERIC_ENTITIES
        generic_active = (
            generic_source and
            {"service.entity.search", "service.entity.read"}.issubset(active_capabilities)
        )
        named_routes = NAMED_READ_ROUTES.get(entity, ())
        named_active = bool(named_routes) and any(
            route in active_capabilities for route in named_routes
        )
        if can_query is None:
            state = "provider_queryability_unverified"
        elif can_query is False:
            state = "provider_reports_not_queryable"
        elif access == "None":
            state = "provider_user_query_denied"
        elif access is None:
            state = "provider_user_query_access_unverified"
        elif access in {"Mine", "Restricted"}:
            state = "provider_user_query_scope_limited"
        elif specialized:
            state = "specialized_authorization_review_required"
        elif generic_active:
            state = "generic_registered_requires_live_read_proof"
        elif named_active:
            state = "named_route_active_requires_live_read_proof"
        elif generic_source:
            state = "generic_source_present_not_active"
        else:
            state = "governed_query_route_gap"
        rows.append({
            "entity": entity,
            "vendor_documented": entity in vendor_names,
            "source_connector_entity_registered": entity in APPROVED_AUTOTASK_ENTITIES,
            "provider_metadata_observed": metadata_observed,
            "provider_can_query": can_query,
            "provider_user_query_access": access,
            "field_metadata_observed": known_fields,
            "field_count": len(fields) if known_fields else None,
            "specialized_handling": specialized,
            "generic_source_registered": generic_source,
            "generic_capabilities_active": generic_active,
            "named_route_source_registered": bool(named_routes),
            "named_route_capabilities_active": [c for c in named_routes if c in active_capabilities],
            "assessment": state,
            "live_record_read_verified": False,
            "pagination_verified": False,
            "disclosure_negative_tests_verified": False,
        })
    return {
        "schema_version": "1.1",
        "scope": "publicly_documented_names_plus_source_registered_names",
        "complete_autotask_api_inventory": False,
        "entity_count": len(rows),
        "vendor_documented_entity_count": len(vendor_names),
        "source_registered_entity_count": len(APPROVED_AUTOTASK_ENTITIES),
        "rows": rows,
        "note": (
            "Public index is NOT provider permission; source registration is NOT "
            "an active capability; metadata is NOT successful record read; "
            "provider read is NOT requester disclosure authorization."
        ),
    }
