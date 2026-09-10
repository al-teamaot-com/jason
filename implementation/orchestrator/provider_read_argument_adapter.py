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
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
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
    DOCUMENTATION_DOCUMENT_SEARCH: "Documents",
    DOCUMENTATION_DOCUMENT_READ: "Documents",
}

_IT_GLUE_SEARCH_CAPABILITIES = frozenset(
    {
        DOCUMENTATION_ORGANIZATION_SEARCH,
        DOCUMENTATION_CONTACT_SEARCH,
        DOCUMENTATION_LOCATION_SEARCH,
        DOCUMENTATION_CONFIGURATION_SEARCH,
        DOCUMENTATION_DOCUMENT_SEARCH,
    }
)

_IT_GLUE_SAFE_PAGINATION_META_KEYS = frozenset(
    {
        "current-page",
        "current_page",
        "next-page",
        "next_page",
        "prev-page",
        "prev_page",
        "previous-page",
        "previous_page",
        "total-pages",
        "total_pages",
        "total-count",
        "total_count",
        "page-size",
        "page_size",
        "per-page",
        "per_page",
    }
)

_AUTOTASK_SEARCH_FIELDS: Mapping[str, Mapping[str, str]] = {
    SERVICE_COMPANY_SEARCH: {
        "resource_id": "id",
        "name": "companyName",
    },
    SERVICE_CONTACT_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "first_name": "firstName",
        "last_name": "lastName",
        "email": "emailAddress",
    },
    SERVICE_TICKET_SEARCH: {
        "resource_id": "id",
        "ticket_number": "ticketNumber",
        "company_id": "companyID",
        "status": "status",
    },
    SERVICE_CONFIGURATION_SEARCH: {
        "resource_id": "id",
        "company_id": "companyID",
        "name": "referenceTitle",
    },
}

_DEFAULT_IT_GLUE_PAGE_SIZE = 100
_MAX_IT_GLUE_PAGE_SIZE = 1000
_DEFAULT_AUTOTASK_MAX_RECORDS = 100
_MAX_AUTOTASK_MAX_RECORDS = 500


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
        "after_resource_id",
    }
    ignored.update(excluded)
    for key, value in arguments.items():
        if key in ignored or value is None:
            continue
        result.setdefault(str(key), value)
    return result


def _it_glue_page_size(arguments: Mapping[str, Any]) -> int:
    value = arguments.get("page_size", _DEFAULT_IT_GLUE_PAGE_SIZE)
    if isinstance(value, bool):
        raise ValueError("page_size must be an integer between 1 and 1000")
    try:
        page_size = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("page_size must be an integer between 1 and 1000") from error
    if not 1 <= page_size <= _MAX_IT_GLUE_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 1000")
    return page_size


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
    if capability_name == DOCUMENTATION_DOCUMENT_READ:
        return {"document_id": _resource_id(arguments)}

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
        "page_size": _it_glue_page_size(arguments),
    }
    if arguments.get("page_number") is not None:
        result["page_number"] = arguments["page_number"]
    return result


def _autotask_max_records(arguments: Mapping[str, Any]) -> int:
    value = arguments.get("page_size", _DEFAULT_AUTOTASK_MAX_RECORDS)
    if isinstance(value, bool):
        raise ValueError("page_size must be an integer between 1 and 500")
    try:
        maximum = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("page_size must be an integer between 1 and 500") from error
    if not 1 <= maximum <= _MAX_AUTOTASK_MAX_RECORDS:
        raise ValueError("page_size must be between 1 and 500")
    return maximum


def _autotask_after_resource_id(arguments: Mapping[str, Any]) -> int | None:
    value = arguments.get("after_resource_id")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("after_resource_id must be a positive integer")
    try:
        resource_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("after_resource_id must be a positive integer") from error
    if resource_id < 1:
        raise ValueError("after_resource_id must be a positive integer")
    return resource_id


def _autotask_search(
    capability_name: str,
    arguments: Mapping[str, Any],
) -> str:
    explicit = arguments.get("search")
    if explicit is not None:
        raise ValueError(
            "provider-specific Autotask search expressions are not accepted by the "
            "canonical read adapter; use canonical selectors or schema-driven filters"
        )

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

    after_resource_id = _autotask_after_resource_id(arguments)
    if after_resource_id is not None:
        if arguments.get("resource_id") is not None or any(
            item["field"] == "id" for item in clauses
        ):
            raise ValueError(
                "after_resource_id cannot be combined with an exact id selector"
            )
        clauses.append(
            {"op": "gt", "field": "id", "value": after_resource_id}
        )

    for selector, provider_field in _AUTOTASK_SEARCH_FIELDS[capability_name].items():
        value = arguments.get(selector)
        if value is not None and not any(
            item["field"] == provider_field for item in clauses
        ):
            clauses.append({"op": "eq", "field": provider_field, "value": value})

    if not clauses:
        clauses.append({"op": "exist", "field": "id"})

    return json.dumps(
        {
            "MaxRecords": _autotask_max_records(arguments),
            "filter": clauses,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


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


def _minimize_it_glue_search_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep record evidence and bounded pagination facts, not provider filter catalogs.

    IT Glue may include response metadata describing available filters or permitted
    values. Those details are useful to provider tooling but are not needed for a
    technician-facing evidence result and can be much larger than the actual records.
    Canonical search output therefore preserves the JSON:API records, optional
    included records, and only small pagination metadata. Provider links and all other
    metadata are deliberately omitted from the returned evidence package.
    """

    minimized: dict[str, Any] = {}
    if "data" in payload:
        minimized["data"] = payload["data"]

    included = payload.get("included")
    if isinstance(included, list):
        minimized["included"] = included

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        pagination = {
            str(key): value
            for key, value in meta.items()
            if str(key) in _IT_GLUE_SAFE_PAGINATION_META_KEYS
        }
        if pagination:
            minimized["meta"] = pagination

    return minimized


def _minimize_provider_read_output(
    *,
    provider_id: str,
    capability_name: str,
    invocation: InvocationResult,
) -> InvocationResult:
    if provider_id != IT_GLUE_PROVIDER or capability_name not in _IT_GLUE_SEARCH_CAPABILITIES:
        return invocation

    output = dict(invocation.output)
    payload = output.get("data")
    if not isinstance(payload, Mapping):
        return invocation

    output["data"] = _minimize_it_glue_search_payload(payload)
    return InvocationResult(
        output=output,
        artifact_references=invocation.artifact_references,
        attempts=invocation.attempts,
    )


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
        invocation = self.delegate.invoke(
            request=replace(request, arguments=adapted),
            resolution=resolution,
        )
        return _minimize_provider_read_output(
            provider_id=provider_id,
            capability_name=resolution.capability_name,
            invocation=invocation,
        )
