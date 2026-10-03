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




def test_vendor_create_is_bounded_to_vendor_company_and_aot_defaults() -> None:
    payload = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.vendor.create",
        {
            "companyName": "Synthetic Vendor",
            "webAddress": "https://vendor.example",
        },
    )
    assert payload["companyType"] == 7
    assert "ownerResourceID" not in payload
    assert payload["territoryID"] == 29682778
    assert payload["companyCategoryID"] == 1
    assert payload["currencyID"] == 1
    assert payload["purchaseOrderTemplateID"] == 102
    assert payload["isActive"] is True
    assert payload["phone"] == "0"

    with pytest.raises(PermissionError, match="AUTOTASK_PROCUREMENT_FIELD_NOT_ALLOWED"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.vendor.create",
            {
                "companyName": "Synthetic Vendor",
                "companyType": 1,
            },
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

def test_ticket_charge_create_requires_catalog_reference_and_bounded_fields() -> None:
    with pytest.raises(ValueError, match="productID or billingCodeID"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.ticket.charge.create",
            {
                "ticketID": 123,
                "costType": 1,
                "datePurchased": "2026-09-20T12:00:00Z",
                "name": "Dock",
                "unitQuantity": 1,
            },
        )

    payload = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.ticket.charge.create",
        {
            "ticketID": 123,
            "productID": 45,
            "costType": 1,
            "datePurchased": "2026-09-20T12:00:00Z",
            "name": "Dock",
            "unitQuantity": 1,
            "unitCost": 100,
            "unitPrice": 150,
            "isBillableToCompany": True,
        },
    )
    assert payload["ticketID"] == 123
    assert payload["productID"] == 45
    assert payload["unitQuantity"] == 1

    with pytest.raises(PermissionError, match="AUTOTASK_PROCUREMENT_FIELD_NOT_ALLOWED"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.ticket.charge.update",
            {"id": 456, "ticketID": 999, "unitQuantity": 1},
        )


def test_client_quote_create_payloads_require_native_autotask_fields() -> None:
    opportunity = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.opportunity.create",
        {
            "amount": 1199,
            "cost": 900,
            "companyID": 123,
            "ownerResourceID": 456,
            "probability": 50,
            "projectedCloseDate": "2026-11-01T12:00:00Z",
            "stage": 29682772,
            "startDate": "2026-10-02T12:00:00Z",
            "status": 1,
            "title": "Ticket quote",
            "useQuoteTotals": True,
        },
    )
    assert opportunity["stage"] == 29682772

    quote = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.quote.create",
        {
            "billToLocationID": 1,
            "effectiveDate": "2026-10-02T12:00:00Z",
            "expirationDate": "2026-11-01T12:00:00Z",
            "name": "Ticket quote",
            "opportunityID": 2,
            "shipToLocationID": 1,
            "soldToLocationID": 1,
        },
    )
    assert quote["opportunityID"] == 2

    quote_item = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.quote.item.create",
        {
            "productID": 77,
            "name": "Dock",
            "isOptional": False,
            "lineDiscount": 0,
            "percentageDiscount": 0,
            "periodType": 5,
            "quantity": 1,
            "quoteItemType": 1,
            "unitDiscount": 0,
            "unitPrice": 199,
        },
    )
    assert quote_item["productID"] == 77


def test_quote_item_create_fails_closed_without_discount_and_type_controls() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        AutotaskProcurementMutationConnector._validated_payload(
            "autotask.quote.item.create",
            {
                "productID": 77,
                "name": "Dock",
                "quantity": 1,
                "quoteItemType": 1,
            },
        )
