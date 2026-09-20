from __future__ import annotations

import pytest

from connectors.autotask.operations import (
    AUTOTASK_OPERATIONS,
    resolve_operation,
    resolve_operation_request,
)


@pytest.mark.parametrize(
    (
        "capability",
        "arguments",
        "expected_method",
        "expected_path",
        "expected_params",
    ),
    [
        (
            "autotask.ticket.get",
            {"ticket_id": "134952"},
            "GET",
            "/V1.0/Tickets/134952",
            None,
        ),
        (
            "autotask.ticket.notes.list",
            {"ticket_id": 134952},
            "GET",
            "/V1.0/Tickets/134952/Notes",
            None,
        ),
        (
            "autotask.company.get",
            {"company_id": 42},
            "GET",
            "/V1.0/Companies/42",
            None,
        ),
        (
            "autotask.contact.get",
            {"contact_id": 73},
            "GET",
            "/V1.0/Contacts/73",
            None,
        ),
        (
            "autotask.configuration.get",
            {"configuration_item_id": 88},
            "GET",
            "/V1.0/ConfigurationItems/88",
            None,
        ),
        (
            "autotask.ticket.search",
            {"search": '{"MaxRecords":10}'},
            "GET",
            "/V1.0/Tickets/query",
            {"search": '{"MaxRecords":10}'},
        ),
    ],
)
def test_resolves_registered_operation(
    capability,
    arguments,
    expected_method,
    expected_path,
    expected_params,
) -> None:
    assert resolve_operation(
        capability,
        arguments,
    ) == (
        expected_method,
        expected_path,
        expected_params,
    )


def test_registry_matches_connector_capabilities_and_dormant_mutations() -> None:
    assert set(AUTOTASK_OPERATIONS) == {
        "autotask.entity.describe",
        "autotask.entity.get",
        "autotask.entity.query",
        "autotask.ticket.get",
        "autotask.ticket.search",
        "autotask.ticket.count",
        "autotask.ticket.notes.list",
        "autotask.notification_history.search",
        "autotask.ticket.create",
        "autotask.ticket.update",
        "autotask.ticket.note.create",
        "autotask.ticket.note.update",
        "autotask.product.create",
        "autotask.product.update",
        "autotask.product.vendor.create",
        "autotask.product.vendor.update",
        "autotask.service.create",
        "autotask.service.update",
        "autotask.service.bundle.create",
        "autotask.service.bundle.update",
        "autotask.purchase.order.create",
        "autotask.purchase.order.update",
        "autotask.purchase.order.item.create",
        "autotask.purchase.order.item.update",
        "autotask.purchase.order.item.receiving.create",
        "autotask.company.get",
        "autotask.company.search",
        "autotask.contact.get",
        "autotask.contact.search",
        "autotask.configuration.get",
        "autotask.configuration.search",
        "autotask.contract.search",
        "autotask.project.search",
    }


def test_rejects_unknown_operation() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported capability",
    ):
        resolve_operation(
            "autotask.invoice.delete",
            {},
        )


def test_rejects_missing_path_argument() -> None:
    with pytest.raises(
        ValueError,
        match="ticket_id",
    ):
        resolve_operation(
            "autotask.ticket.get",
            {},
        )


def test_rejects_invalid_path_argument() -> None:
    with pytest.raises(
        ValueError,
        match="must be an integer",
    ):
        resolve_operation(
            "autotask.ticket.get",
            {"ticket_id": "not-a-number"},
        )


@pytest.mark.parametrize(
    "query",
    [
        None,
        "",
        "   ",
        123,
    ],
)
def test_rejects_invalid_search_expression(
    query,
) -> None:
    with pytest.raises(
        ValueError,
        match="non-empty structured",
    ):
        resolve_operation(
            "autotask.ticket.search",
            {"search": query},
        )


@pytest.mark.parametrize(
    (
        "capability",
        "arguments",
        "expected_path",
        "expected_params",
    ),
    [
        (
            "autotask.entity.describe",
            {"entity": "Invoices"},
            "/V1.0/Invoices/entityInformation",
            None,
        ),
        (
            "autotask.entity.get",
            {
                "entity": "PurchaseOrders",
                "entity_id": "42",
            },
            "/V1.0/PurchaseOrders/42",
            None,
        ),
        (
            "autotask.entity.query",
            {
                "entity": "Companies",
                "search": '{"MaxRecords":10}',
            },
            "/V1.0/Companies/query",
            {"search": '{"MaxRecords":10}'},
        ),
    ],
)
def test_resolves_generic_entity_operation(
    capability,
    arguments,
    expected_path,
    expected_params,
) -> None:
    method, path, params = resolve_operation(
        capability,
        arguments,
    )

    assert method == "GET"
    assert path == expected_path
    assert params == expected_params


def test_rejects_unapproved_entity() -> None:
    with pytest.raises(
        ValueError,
        match="not approved",
    ):
        resolve_operation(
            "autotask.entity.query",
            {
                "entity": "SecretInternalEntity",
                "search": '{"MaxRecords":10}',
            },
        )


def test_generic_get_requires_numeric_entity_id() -> None:
    with pytest.raises(
        ValueError,
        match="must be an integer",
    ):
        resolve_operation(
            "autotask.entity.get",
            {
                "entity": "Invoices",
                "entity_id": "not-an-id",
            },
        )


@pytest.mark.parametrize(
    ("capability", "method", "path"),
    [
        ("autotask.ticket.create", "POST", "/V1.0/Tickets"),
        ("autotask.ticket.update", "PATCH", "/V1.0/Tickets"),
        (
            "autotask.ticket.note.create",
            "POST",
            "/V1.0/Tickets/12345/Notes",
        ),
        (
            "autotask.ticket.note.update",
            "PATCH",
            "/V1.0/Tickets/12345/Notes",
        ),
        ("autotask.product.create", "POST", "/V1.0/Products"),
        ("autotask.product.update", "PATCH", "/V1.0/Products"),
        ("autotask.product.vendor.create", "POST", "/V1.0/ProductVendors"),
        ("autotask.product.vendor.update", "PATCH", "/V1.0/ProductVendors"),
        ("autotask.service.create", "POST", "/V1.0/Services"),
        ("autotask.service.update", "PATCH", "/V1.0/Services"),
        ("autotask.service.bundle.create", "POST", "/V1.0/ServiceBundles"),
        ("autotask.service.bundle.update", "PATCH", "/V1.0/ServiceBundles"),
        ("autotask.purchase.order.create", "POST", "/V1.0/PurchaseOrders"),
        ("autotask.purchase.order.update", "PATCH", "/V1.0/PurchaseOrders"),
        (
            "autotask.purchase.order.item.create",
            "POST",
            "/V1.0/PurchaseOrderItems",
        ),
        (
            "autotask.purchase.order.item.update",
            "PATCH",
            "/V1.0/PurchaseOrderItems",
        ),
    ],
)
def test_compiles_only_registered_mutation_routes(capability, method, path) -> None:
    payload = {"title": "Synthetic"}
    if capability.startswith("autotask.ticket.note."):
        payload["ticketID"] = 12345
    if capability.endswith("update"):
        payload["id"] = 12345

    actual_method, actual_path, params, body = resolve_operation_request(
        capability,
        {"payload": payload},
    )

    assert actual_method == method
    assert actual_path == path
    assert params is None
    assert body == payload


def test_read_wrapper_refuses_to_discard_mutation_body() -> None:
    with pytest.raises(
        ValueError,
        match="requires resolve_operation_request",
    ):
        resolve_operation(
            "autotask.ticket.create",
            {"payload": {"companyID": 999, "title": "Synthetic"}},
        )


def test_update_requires_positive_durable_id() -> None:
    with pytest.raises(ValueError, match="positive numeric id"):
        resolve_operation_request(
            "autotask.ticket.update",
            {"payload": {"status": 5}},
        )


def test_ticket_and_ticketnote_delete_remain_unregistered() -> None:
    assert "autotask.ticket.delete" not in AUTOTASK_OPERATIONS
    assert "autotask.ticket.note.delete" not in AUTOTASK_OPERATIONS
