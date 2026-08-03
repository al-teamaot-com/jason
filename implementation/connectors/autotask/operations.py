from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class OperationDefinition:
    method: str
    path_template: str
    path_arguments: tuple[str, ...] = ()
    query_argument: str | None = None


AUTOTASK_OPERATIONS: Mapping[str, OperationDefinition] = {
    "autotask.ticket.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/Tickets/{ticket_id}",
        path_arguments=("ticket_id",),
    ),
    "autotask.ticket.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/Tickets/query",
        query_argument="search",
    ),
    "autotask.ticket.notes.list": OperationDefinition(
        method="GET",
        path_template="/V1.0/Tickets/{ticket_id}/Notes",
        path_arguments=("ticket_id",),
    ),
    "autotask.company.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/Companies/{company_id}",
        path_arguments=("company_id",),
    ),
    "autotask.contact.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/Contacts/{contact_id}",
        path_arguments=("contact_id",),
    ),
    "autotask.configuration_item.get": OperationDefinition(
        method="GET",
        path_template=(
            "/V1.0/ConfigurationItems/"
            "{configuration_item_id}"
        ),
        path_arguments=("configuration_item_id",),
    ),
}


def resolve_operation(
    capability: str,
    arguments: Mapping[str, Any],
) -> tuple[str, str, Mapping[str, Any] | None]:
    definition = AUTOTASK_OPERATIONS.get(capability)

    if definition is None:
        raise ValueError(
            f"Unsupported capability: {capability}"
        )

    path_values: dict[str, int] = {}

    for argument_name in definition.path_arguments:
        if argument_name not in arguments:
            raise ValueError(
                f"Required argument is missing: {argument_name}"
            )

        try:
            path_values[argument_name] = int(
                arguments[argument_name]
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Argument must be an integer: {argument_name}"
            ) from error

    path = definition.path_template.format(
        **path_values
    )

    params = None

    if definition.query_argument is not None:
        query = arguments.get(
            definition.query_argument
        )

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A non-empty structured Autotask "
                "search expression is required."
            )

        params = {
            definition.query_argument: query,
        }

    return definition.method, path, params
