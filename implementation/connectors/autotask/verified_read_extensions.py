"""Reviewed, metadata-proven read-only Autotask entity candidates for future v12.

This intentionally does NOT activate v12 in runtime, MCP, release manager or
production. The v11 source profile retains its exact previously approved scope.
These names were individually confirmed through the governed
service.entity.describe route with canQuery=true, userAccessForQuery=All.
Provider record query, pagination, exact ID and disclosure tests are still
required before an eventual explicit v12 production release.
"""
from __future__ import annotations

import os

V12_PROFILE = "itglue-autotask-entra-broad-evidence-read-catalog-v12"

V12_ADDITIONAL_READ_ENTITIES = frozenset({
    "Phases",
    "TaskNotes",
    "TaskPredecessors",
    "TaskSecondaryResources",
    "ServiceCallTasks",
    "ServiceCallTickets",
    "ServiceCallTaskResources",
    "ServiceCallTicketResources",
    "CompanyLocations",
    "TicketCategories",
    "TicketChecklistItems",
    "TicketSecondaryResources",
    "TicketChangeRequestApprovals",
    "InventoryLocations",
    "InventoryProducts",
    "InventoryStockedItems",
    "InventoryItemSerialNumbers",
})


def v12_entity_read_enabled(entity: object) -> bool:
    """Exact source-bound profile is required for additional read-only names."""
    return bool(
        isinstance(entity, str)
        and entity in V12_ADDITIONAL_READ_ENTITIES
        and os.getenv("JASON_PROVIDER_READ_ACTIVATION_PROFILE", "").strip() == V12_PROFILE
    )
