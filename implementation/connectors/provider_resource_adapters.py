from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.resource_gateway import ResourceOperation, ResourceQuery


@dataclass(frozen=True)
class ConnectorInvocation:
    capability: str
    arguments: Mapping[str, Any]


def _require_filter(query: ResourceQuery, name: str) -> Any:
    filters = query.filters or {}
    if name not in filters:
        raise ValueError(f"Required resource filter is missing: {name}")
    return filters[name]


def translate_it_glue_resource(query: ResourceQuery) -> ConnectorInvocation:
    if query.provider != "it_glue":
        raise ValueError("IT Glue adapter received a query for another provider")

    if query.resource_type == "entity":
        entity = _require_filter(query, "entity")
        if query.operation is ResourceOperation.GET:
            return ConnectorInvocation(
                capability="it_glue.entity.get",
                arguments={
                    "entity": entity,
                    "entity_id": query.resource_id,
                },
            )
        if query.operation is ResourceOperation.QUERY:
            filters = dict(query.filters or {})
            filters.pop("entity", None)
            arguments: dict[str, Any] = {
                "entity": entity,
                "filters": filters,
            }
            if query.page_size is not None:
                arguments["page_size"] = query.page_size
            return ConnectorInvocation(
                capability="it_glue.entity.query",
                arguments=arguments,
            )

    if query.resource_type == "document" and query.operation is ResourceOperation.GET:
        return ConnectorInvocation(
            capability="it_glue.document.get",
            arguments={"document_id": query.resource_id},
        )

    if query.resource_type == "relationship" and query.operation in {
        ResourceOperation.QUERY,
        ResourceOperation.RELATIONSHIPS,
    }:
        return ConnectorInvocation(
            capability="it_glue.relationships.list",
            arguments={
                "resource_type": _require_filter(query, "resource_type"),
                "resource_id": _require_filter(query, "resource_id"),
            },
        )

    raise ValueError(
        f"No IT Glue resource translation exists for "
        f"{query.resource_type}.{query.operation.value}"
    )


def translate_datto_rmm_resource(query: ResourceQuery) -> ConnectorInvocation:
    if query.provider != "datto_rmm":
        raise ValueError("Datto RMM adapter received a query for another provider")

    if query.resource_type == "device":
        if query.operation is ResourceOperation.GET:
            return ConnectorInvocation(
                capability="datto_rmm.device.get",
                arguments={"device_uid": query.resource_id},
            )
        if query.operation is ResourceOperation.QUERY:
            filters = query.filters or {}
            return ConnectorInvocation(
                capability="datto_rmm.device.search",
                arguments={"search": filters.get("search", "")},
            )

    if query.resource_type == "alert" and query.operation is ResourceOperation.QUERY:
        filters = query.filters or {}
        return ConnectorInvocation(
            capability="datto_rmm.alerts.list",
            arguments={"site_uid": filters.get("site_uid")},
        )

    if query.resource_type == "patch_state" and query.operation is ResourceOperation.GET:
        return ConnectorInvocation(
            capability="datto_rmm.patch_status.get",
            arguments={"device_uid": query.resource_id},
        )

    if query.resource_type == "job" and query.operation is ResourceOperation.QUERY:
        return ConnectorInvocation(
            capability="datto_rmm.component_results.list",
            arguments={"device_uid": _require_filter(query, "device_uid")},
        )

    raise ValueError(
        f"No Datto RMM resource translation exists for "
        f"{query.resource_type}.{query.operation.value}"
    )
