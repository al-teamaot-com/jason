from __future__ import annotations

import json
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


def _autotask_search(filters: Mapping[str, Any]) -> str:
    clauses = [
        {"op": "eq", "field": str(field), "value": value}
        for field, value in filters.items()
        if str(field).strip()
    ]
    return json.dumps(
        {"filter": clauses},
        separators=(",", ":"),
        sort_keys=True,
    )


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


def translate_autotask_resource(query: ResourceQuery) -> ConnectorInvocation:
    if query.provider != "autotask":
        raise ValueError("Autotask adapter received a query for another provider")

    if query.resource_type == "entity":
        entity = _require_filter(query, "entity")
        if query.operation is ResourceOperation.DESCRIBE:
            return ConnectorInvocation(
                capability="autotask.entity.describe",
                arguments={"entity": entity},
            )
        if query.operation is ResourceOperation.GET:
            return ConnectorInvocation(
                capability="autotask.entity.get",
                arguments={
                    "entity": entity,
                    "entity_id": query.resource_id,
                },
            )
        if query.operation is ResourceOperation.QUERY:
            filters = dict(query.filters or {})
            filters.pop("entity", None)
            return ConnectorInvocation(
                capability="autotask.entity.query",
                arguments={
                    "entity": entity,
                    "search": _autotask_search(filters),
                },
            )

    if query.resource_type == "ticket_note" and query.operation in {
        ResourceOperation.GET,
        ResourceOperation.QUERY,
    }:
        ticket_id = query.resource_id or _require_filter(query, "ticket_id")
        return ConnectorInvocation(
            capability="autotask.ticket.notes.list",
            arguments={"ticket_id": ticket_id},
        )

    raise ValueError(
        f"No Autotask resource translation exists for "
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
            arguments: dict[str, Any] = {"page": 1}
            hostname = (
                filters.get("hostname")
                or filters.get("name")
                or filters.get("search")
            )
            site = filters.get("site") or filters.get("site_name")
            if hostname is not None and str(hostname).strip():
                arguments["hostname"] = str(hostname).strip()
            if site is not None and str(site).strip():
                arguments["site"] = str(site).strip()
            if query.page_size is not None:
                # Discovery must preserve at least two candidates so ambiguity is
                # observable. The provider connector enforces the same invariant.
                arguments["max"] = max(int(query.page_size), 2)
            return ConnectorInvocation(
                capability="datto_rmm.device.search",
                arguments=arguments,
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
