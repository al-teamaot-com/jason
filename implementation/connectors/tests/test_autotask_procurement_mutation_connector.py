from __future__ import annotations

import pytest

from connectors.autotask.procurement_mutation_connector import (
    AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS,
    AutotaskProcurementMutationConnector,
    PROCUREMENT_OPERATION_PREFLIGHT,
)


def test_procurement_connector_uses_separate_secret_and_exact_capability_set() -> None:
    assert AutotaskProcurementMutationConnector.logical_secret == "autotask.procurement.write"
    assert AutotaskProcurementMutationConnector.capabilities == (
        AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS
    )
    assert set(PROCUREMENT_OPERATION_PREFLIGHT) == set(
        AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS
    )


def test_product_create_payload_is_bounded_to_approved_fields() -> None:
    payload = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.product.create",
        {
            "name": "Synthetic Product",
            "isActive": True,
            "isSerialized": False,
            "sku": "SYN-001",
            "unitCost": 10.0,
        },
    )
    assert payload["sku"] == "SYN-001"


    with pytest.raises(PermissionError, match="AUTOTASK_PROCUREMENT_FIELD_NOT_ALLOWED"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.product.create",
            {
                "name": "Synthetic Product",
                "isActive": True,
                "isSerialized": False,
                "unsafeField": "not permitted",
            },
        )


def test_procurement_create_requires_minimum_fields_and_update_requires_id() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.purchase.order.create",
            {"generalMemo": "missing vendor"},
        )

    with pytest.raises(ValueError, match="positive durable id"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.purchase.order.update",
            {"vendorInvoiceNumber": "INV-1"},
        )

    payload = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.purchase.order.update",
        {"id": "42", "vendorInvoiceNumber": "INV-1"},
    )
    assert payload["id"] == 42
