from __future__ import annotations

import pytest

from connectors.autotask.operations import (
    AUTOTASK_OPERATIONS,
    resolve_operation,
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
            "autotask.configuration_item.get",
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


def test_registry_matches_connector_capabilities() -> None:
    assert set(AUTOTASK_OPERATIONS) == {
        "autotask.entity.describe",
        "autotask.entity.get",
        "autotask.entity.query",
        "autotask.ticket.get",
        "autotask.ticket.search",
        "autotask.ticket.notes.list",
        "autotask.company.get",
        "autotask.contact.get",
        "autotask.configuration_item.get",
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
