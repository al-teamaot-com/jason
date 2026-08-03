from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import (
    ConnectorContext,
    ConnectorRequest,
)

from jason_cli.runtime import build_autotask_connector


PREFERRED_FIELDS = (
    "id",
    "ticketNumber",
    "invoiceNumber",
    "purchaseOrderNumber",
    "name",
    "title",
    "status",
    "priority",
    "companyID",
    "assignedResourceID",
    "createDate",
    "lastActivityDate",
)


def execute_autotask(
    *,
    capability: str,
    arguments: Mapping[str, Any],
    correlation_id: str,
) -> Mapping[str, Any]:
    connector = build_autotask_connector()

    result = connector.execute(
        ConnectorRequest(
            context=ConnectorContext(
                correlation_id=correlation_id,
                principal_id="jason-cli-user",
                organization_id="team-aot",
                client_id=None,
                capability=capability,
                mode="observe",
            ),
            arguments=arguments,
        )
    )

    return result.data


def read_search_file(path: Path) -> str:
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise ValueError(
            f"Search file is unavailable: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Search file contains invalid JSON: {path}"
        ) from error

    if not isinstance(parsed, Mapping):
        raise ValueError(
            "Search file must contain a JSON object."
        )

    return json.dumps(
        parsed,
        separators=(",", ":"),
    )


def print_json(data: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def _label(field_name: str) -> str:
    labels = {
        "id": "ID",
        "ticketNumber": "Ticket Number",
        "invoiceNumber": "Invoice Number",
        "purchaseOrderNumber": "Purchase Order Number",
        "companyID": "Company ID",
        "assignedResourceID": "Assigned Resource ID",
        "createDate": "Created",
        "lastActivityDate": "Last Activity",
    }

    return labels.get(
        field_name,
        field_name.replace("_", " ").title(),
    )


def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _summary_fields(
    item: Mapping[str, Any],
) -> list[tuple[str, Any]]:
    selected = [
        (field, item[field])
        for field in PREFERRED_FIELDS
        if field in item
    ]

    if selected:
        return selected

    return [
        (field, value)
        for field, value in item.items()
        if isinstance(
            value,
            (str, int, float, bool, type(None)),
        )
    ][:12]


def print_entity(
    entity: str,
    data: Mapping[str, Any],
) -> None:
    item = data.get("item")

    if not isinstance(item, Mapping):
        print(f"{entity}: no item returned.")
        return

    print(f"{entity} record")
    print("=" * (len(entity) + 7))

    for field, value in _summary_fields(item):
        print(f"{_label(field)}: {_display_value(value)}")


def print_query_results(
    entity: str,
    data: Mapping[str, Any],
) -> None:
    items = data.get("items")

    if not isinstance(items, list):
        print(f"{entity}: unexpected query response.")
        return

    print(f"{entity} query results")
    print("=" * (len(entity) + 14))
    print(f"Matches returned: {len(items)}")

    page_details = data.get("pageDetails")
    if isinstance(page_details, Mapping):
        request_count = page_details.get("requestCount")
        if request_count is not None:
            print(f"Requested: {request_count}")

    if not items:
        print()
        print("No matching records found.")
        return

    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue

        print()
        print(f"[{index}]")

        for field, value in _summary_fields(item):
            print(
                f"{_label(field)}: "
                f"{_display_value(value)}"
            )


def print_entity_description(
    entity: str,
    data: Mapping[str, Any],
) -> None:
    info = data.get("info")

    if not isinstance(info, Mapping):
        print(f"{entity}: no entity information returned.")
        return

    print(f"Autotask entity: {entity}")
    print("=" * (len(entity) + 17))

    fields = (
        ("name", "API Name"),
        ("canQuery", "Supports Query"),
        ("canCreate", "Supports Create"),
        ("canUpdate", "Supports Update"),
        ("canDelete", "Supports Delete"),
        (
            "hasUserDefinedFields",
            "Has User-Defined Fields",
        ),
        (
            "supportsWebhookCallouts",
            "Supports Webhooks",
        ),
        (
            "userAccessForQuery",
            "Current Query Access",
        ),
        (
            "userAccessForCreate",
            "Current Create Access",
        ),
        (
            "userAccessForUpdate",
            "Current Update Access",
        ),
        (
            "userAccessForDelete",
            "Current Delete Access",
        ),
    )

    for field, label in fields:
        if field in info:
            print(
                f"{label}: "
                f"{_display_value(info[field])}"
            )


def run_describe(
    entity: str,
    *,
    json_output: bool = False,
) -> int:
    data = execute_autotask(
        capability="autotask.entity.describe",
        arguments={"entity": entity},
        correlation_id=f"cli-autotask-describe-{entity}",
    )

    if json_output:
        print_json(data)
    else:
        print_entity_description(entity, data)

    return 0


def run_get(
    entity: str,
    entity_id: int,
    *,
    json_output: bool = False,
) -> int:
    data = execute_autotask(
        capability="autotask.entity.get",
        arguments={
            "entity": entity,
            "entity_id": entity_id,
        },
        correlation_id=(
            f"cli-autotask-get-{entity}-{entity_id}"
        ),
    )

    if json_output:
        print_json(data)
    else:
        print_entity(entity, data)

    return 0


def run_query(
    entity: str,
    search_file: Path,
    *,
    json_output: bool = False,
) -> int:
    search = read_search_file(search_file)

    data = execute_autotask(
        capability="autotask.entity.query",
        arguments={
            "entity": entity,
            "search": search,
        },
        correlation_id=f"cli-autotask-query-{entity}",
    )

    if json_output:
        print_json(data)
    else:
        print_query_results(entity, data)

    return 0
