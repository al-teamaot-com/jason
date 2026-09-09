from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from kernel.resolution import CapabilityResolutionResult

from .connector_invoker import GovernedConnectorCapabilityInvoker
from .contracts import OrchestrationRequest
from .provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_CONFIGURATION_READ,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_CONTACT_READ,
    DOCUMENTATION_CONTACT_SEARCH,
    DOCUMENTATION_LOCATION_READ,
    DOCUMENTATION_LOCATION_SEARCH,
    DOCUMENTATION_ORGANIZATION_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_CONFIGURATION_READ,
    SERVICE_CONFIGURATION_SEARCH,
    SERVICE_CONTACT_READ,
    SERVICE_CONTACT_SEARCH,
    SERVICE_ENTITY_DESCRIBE,
    SERVICE_TICKET_NOTES_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
)
from .service import InvocationResult


_IT_GLUE_ENTITY = {
    DOCUMENTATION_ORGANIZATION_SEARCH: "Organizations",
    DOCUMENTATION_CONTACT_SEARCH: "Contacts",
    DOCUMENTATION_CONTACT_READ: "Contacts",
    DOCUMENTATION_LOCATION_SEARCH: "Locations",
    DOCUMENTATION_LOCATION_READ: "Locations",
    DOCUMENTATION_CONFIGURATION_SEARCH: "Configurations",
    DOCUMENTATION_CONFIGURATION_READ: "Configurations",
}

_AUTOTASK_SEARCH_FIELDS: Mapping[str, Mapping[str, str]] = {
    SERVICE_COMPANY_SEARCH: {
        "name": "companyName",
    },
    SERVICE_CONTACT_SEARCH: {
        "company_id": "companyID",
        "email": "emailAddress",
    },
    SERVICE_TICKET_SEARCH: {
        "ticket_number": "ticketNumber",
        "company_id": "companyID",
        "status": "status",
    },
    SERVICE_CONFIGURATION_SEARCH: {
        "company_id": "companyID",
        "name": "referenceTitle",
    },
}


def _resource_id(arguments: Mapping[str, Any]) -> Any:
    value = arguments.get("resource_id")
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("resource_id is required for an exact provider read")
    return value


def _canonical_filters(
    arguments: Mapping[str, Any],
    *,
    excluded: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    filters = arguments.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping when supplied")

    result = {
        str(key): value
        for key, value in filters.items()
        if str(key).strip()
    }
    ignored = {
        "requested_facts",
        "result_intent",
        "completeness_requirement",
        "resource_id",
        "filters",
        "page_number",
        "page_size",
    }
    ignored.update(excluded)
    for key, value in arguments.items():
        if key in ignored or value is None:
            continue
        result.setdefault(str(key), value)
    return result


def adapt_it_glue_arguments(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate canonical documentation reads into the existing IT Glue connector.

    The model never needs to provide IT Glue entity-path tokens. Password/vault
    resources are impossible here because only the fixed approved entity families
    below can be injected by this adapter.
    """

    if capability_name == DOCUMENTATION_ORGANIZATION_READ:
        return {"organization_id": _resource_id(arguments)}

    entity = _IT_GLUE_ENTITY.get(capability_name)
    if entity is None:
        raise ValueError(f"Unsupported IT Glue canonical capability: {capability_name}")

    if capability_name.endswith(".read"):
        return {
            "entity": entity,
            "entity_id": _resource_id(arguments),
        }

    result: dict[str, Any] = {
        "entity": entity,
        "filters": _canonical_filters(arguments),
    }
    if arguments.get("page_number") is not None:
        result["page_number"] = arguments["page_number"]
    if arguments.get("page_size") is not None:
        result["page_size"] = arguments["page_size"]
    return result


def _autotask_search(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> str:
    explicit = arguments.get("search")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    filters = arguments.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping when supplied")

    clauses: list[dict[str, Any]] = []
    for field, value in filters.items():
        field_name = str(field).strip()
        if not field_name:
            raise ValueError("Autotask filter field names must be non-empty")
        clauses.append({"op": "eq", "field": field_name, "value": value})

    for selector, provider_field in _AUTOTASK_SEARCH_FIELDS[capability_name].items():
        value = arguments.get(selector)
        if value is not None and not any(
            item["field"] == provider_field for item in clauses
        ):
            clauses.append({"op": "eq", "field": provider_field, "value": value})

    if not clauses:
        # Autotask requires a structured search expression. The empty filter is the
        # explicit bounded collection-query form used by Jason; pagination remains
        # governed by the provider response and higher-level completeness handling.
        return json.dumps({"filter": []}, separators=(",", ":"), sort_keys=True)

    return json.dumps({"filter": clauses}, separators=(",", ":"), sort_keys=True)


def adapt_autotask_arguments(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_name == SERVICE_COMPANY_READ:
        return {"company_id": _resource_id(arguments)}
    if capability_name == SERVICE_CONTACT_READ:
        return {"contact_id": _resource_id(arguments)}
    if capability_name == SERVICE_TICKET_READ:
        return {"ticket_id": _resource_id(arguments)}
    if capability_name == SERVICE_CONFIGURATION_READ:
        return {"configuration_item_id": _resource_id(arguments)}
    if capability_name == SERVICE_TICKET_NOTES_SEARCH:
        return {
            "ticket_id": arguments.get("ticket_id") or _resource_id(arguments)
        }
    if capability_name == SERVICE_ENTITY_DESCRIBE:
        entity = arguments.get("entity")
        if not isinstance(entity, str) or not entity.strip():
            raise ValueError("entity is required for schema description")
        return {"entity": entity.strip()}
    if capability_name in _AUTOTASK_SEARCH_FIELDS:
        return {"search": _autotask_search(capability_name, arguments)}
    raise ValueError(f"Unsupported Autotask canonical capability: {capability_name}")


def adapt_provider_read_arguments(
    *,
    provider_id: str,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if provider_id == IT_GLUE_PROVIDER:
        return adapt_it_glue_arguments(capability_name, arguments)
    if provider_id == AUTOTASK_PROVIDER:
        return adapt_autotask_arguments(capability_name, arguments)
    raise ValueError(f"No provider-read argument adapter for provider: {provider_id}")


@dataclass(frozen=True, slots=True)
class GovernedProviderReadConnectorInvoker:
    """Adapt canonical read arguments only after governed provider selection."""

    delegate: GovernedConnectorCapabilityInvoker

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        provider_id = (resolution.selected_provider_id or "").strip()
        if not provider_id:
            raise PermissionError("resolved provider is required before argument adaptation")

        adapted = adapt_provider_read_arguments(
            provider_id=provider_id,
            capability_name=resolution.capability_name,
            arguments=request.arguments,
        )
        return self.delegate.invoke(
            request=replace(request, arguments=adapted),
            resolution=resolution,
        )
