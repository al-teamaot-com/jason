from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class OperationDefinition:
    method: str
    path_template: str
    path_arguments: tuple[str, ...] = ()
    query_argument: str | None = None
    json_argument: str | None = None
    require_positive_body_id: bool = False


APPROVED_AUTOTASK_ENTITIES = frozenset(
    {
        "Tickets",
        "Companies",
        "Contacts",
        "ConfigurationItems",
        "Invoices",
        "PurchaseOrders",
        "PurchaseOrderItems",
        "PurchaseOrderItemReceiving",
        "Products",
        "ProductVendors",
        "Services",
        "ServiceBundles",
        "Projects",
        "Contracts",
        "Resources",
        "Opportunities",
        "NotificationHistory",
        "TicketCharges",
    }
)


AUTOTASK_OPERATIONS: Mapping[str, OperationDefinition] = {
    "autotask.entity.describe": OperationDefinition(
        method="GET",
        path_template="/V1.0/{entity}/entityInformation",
        path_arguments=("entity",),
    ),
    "autotask.entity.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/{entity}/{entity_id}",
        path_arguments=("entity", "entity_id"),
    ),
    "autotask.entity.query": OperationDefinition(
        method="GET",
        path_template="/V1.0/{entity}/query",
        path_arguments=("entity",),
        query_argument="search",
    ),
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
    "autotask.ticket.count": OperationDefinition(
        method="GET",
        path_template="/V1.0/Tickets/query/count",
        query_argument="search",
    ),
    "autotask.ticket.notes.list": OperationDefinition(
        method="GET",
        path_template="/V1.0/Tickets/{ticket_id}/Notes",
        path_arguments=("ticket_id",),
    ),
    "autotask.notification_history.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/NotificationHistory/query",
        query_argument="search",
    ),
    "autotask.ticket.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/Tickets",
        json_argument="payload",
    ),
    "autotask.ticket.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/Tickets",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.ticket.note.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/Tickets/{ticketID}/Notes",
        path_arguments=("ticketID",),
        json_argument="payload",
    ),
    "autotask.ticket.note.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/Tickets/{ticketID}/Notes",
        path_arguments=("ticketID",),
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.ticket.charge.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/Tickets/{ticketID}/Charges",
        path_arguments=("ticketID",),
        json_argument="payload",
    ),
    "autotask.ticket.charge.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/Tickets/{ticketID}/Charges",
        path_arguments=("ticketID",),
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.product.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/Products",
        json_argument="payload",
    ),
    "autotask.product.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/Products",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.product.vendor.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/ProductVendors",
        json_argument="payload",
    ),
    "autotask.product.vendor.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/ProductVendors",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.service.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/Services",
        json_argument="payload",
    ),
    "autotask.service.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/Services",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.service.bundle.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/ServiceBundles",
        json_argument="payload",
    ),
    "autotask.service.bundle.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/ServiceBundles",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.purchase.order.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/PurchaseOrders",
        json_argument="payload",
    ),
    "autotask.purchase.order.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/PurchaseOrders",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.purchase.order.item.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/PurchaseOrderItems",
        json_argument="payload",
    ),
    "autotask.purchase.order.item.update": OperationDefinition(
        method="PATCH",
        path_template="/V1.0/PurchaseOrderItems",
        json_argument="payload",
        require_positive_body_id=True,
    ),
    "autotask.purchase.order.item.receiving.create": OperationDefinition(
        method="POST",
        path_template="/V1.0/PurchaseOrderItemReceiving",
        json_argument="payload",
    ),
    "autotask.company.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/Companies/{company_id}",
        path_arguments=("company_id",),
    ),
    "autotask.company.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/Companies/query",
        query_argument="search",
    ),
    "autotask.contact.get": OperationDefinition(
        method="GET",
        path_template="/V1.0/Contacts/{contact_id}",
        path_arguments=("contact_id",),
    ),
    "autotask.contact.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/Contacts/query",
        query_argument="search",
    ),
    "autotask.configuration.get": OperationDefinition(
        method="GET",
        path_template=(
            "/V1.0/ConfigurationItems/"
            "{configuration_item_id}"
        ),
        path_arguments=("configuration_item_id",),
    ),
    "autotask.configuration.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/ConfigurationItems/query",
        query_argument="search",
    ),
    "autotask.contract.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/Contracts/query",
        query_argument="search",
    ),
    "autotask.project.search": OperationDefinition(
        method="GET",
        path_template="/V1.0/Projects/query",
        query_argument="search",
    ),
}


def _path_values(
    definition: OperationDefinition,
    arguments: Mapping[str, Any],
) -> dict[str, str | int]:
    values: dict[str, str | int] = {}

    for argument_name in definition.path_arguments:
        value_source = arguments

        if argument_name not in arguments:
            payload = arguments.get("payload")
            if (
                isinstance(payload, Mapping)
                and argument_name in payload
            ):
                value_source = payload
            else:
                raise ValueError(
                    f"Required argument is missing: {argument_name}"
                )

        if argument_name == "entity":
            entity = value_source[argument_name]

            if (
                not isinstance(entity, str)
                or entity not in APPROVED_AUTOTASK_ENTITIES
            ):
                raise ValueError(
                    f"Autotask entity is not approved: {entity!r}"
                )

            values[argument_name] = entity
            continue

        try:
            value = int(value_source[argument_name])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Argument must be an integer: {argument_name}"
            ) from error

        if value < 1:
            raise ValueError(
                f"Argument must be a positive integer: {argument_name}"
            )
        values[argument_name] = value

    return values


def resolve_operation_request(
    capability: str,
    arguments: Mapping[str, Any],
) -> tuple[
    str,
    str,
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
]:
    """Compile one bounded Autotask provider request.

    This compiler intentionally exposes only explicitly registered operations.
    Write bodies are passed as structured mappings rather than arbitrary URLs or
    raw request fragments. Update bodies must include a positive durable id.
    """

    definition = AUTOTASK_OPERATIONS.get(capability)

    if definition is None:
        raise ValueError(
            f"Unsupported capability: {capability}"
        )

    path = definition.path_template.format(
        **_path_values(definition, arguments)
    )

    params = None
    if definition.query_argument is not None:
        query = arguments.get(definition.query_argument)

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A non-empty structured Autotask "
                "search expression is required."
            )

        params = {definition.query_argument: query}

    body: Mapping[str, Any] | None = None
    if definition.json_argument is not None:
        raw_body = arguments.get(definition.json_argument)
        if not isinstance(raw_body, Mapping) or not raw_body:
            raise ValueError(
                "A non-empty structured Autotask payload is required."
            )
        body = dict(raw_body)

        if definition.require_positive_body_id:
            raw_id = body.get("id")
            if isinstance(raw_id, bool):
                raise ValueError(
                    "Autotask update payload requires a positive numeric id."
                )
            try:
                durable_id = int(raw_id)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "Autotask update payload requires a positive numeric id."
                ) from error
            if durable_id < 1:
                raise ValueError(
                    "Autotask update payload requires a positive numeric id."
                )
            body["id"] = durable_id

    return definition.method, path, params, body


def resolve_operation(
    capability: str,
    arguments: Mapping[str, Any],
) -> tuple[str, str, Mapping[str, Any] | None]:
    """Backward-compatible read compiler used by existing callers/tests.

    Mutation operations must use ``resolve_operation_request`` so the structured
    JSON body cannot be silently discarded.
    """

    method, path, params, body = resolve_operation_request(
        capability,
        arguments,
    )
    if body is not None:
        raise ValueError(
            "Mutation operation requires resolve_operation_request."
        )
    return method, path, params
