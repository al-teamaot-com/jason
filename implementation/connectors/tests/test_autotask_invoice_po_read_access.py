"""Invoice/PO provider-read regression gates (offline, no provider mutation).

Provider entity queryability is distinct from permission for the effective
Autotask integration user; a registered Jason read route cannot override None.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectors.autotask.read_coverage_inventory import assess_coverage
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import (
    SERVICE_INVOICE_SEARCH,
    SERVICE_INVOICE_READ,
    SERVICE_BILLING_ITEM_SEARCH,
    SERVICE_BILLING_ITEM_READ,
    SERVICE_PURCHASE_ORDER_SEARCH,
    SERVICE_PURCHASE_ORDER_READ,
    SERVICE_PURCHASE_ORDER_ITEM_SEARCH,
)

EVIDENCE = Path(__file__).resolve().parents[3] / "docs/operations/Autotask-Live-Schema-Observations-20261027.json"


@pytest.mark.parametrize("entity", ["Invoices", "BillingItems"])
def test_denied_financial_provider_read_never_becomes_route_approval(entity):
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    report = assess_coverage(
        provider_entity_information={entity: evidence["entities"][entity]},
        active_capabilities={
            SERVICE_INVOICE_SEARCH, SERVICE_INVOICE_READ,
            SERVICE_BILLING_ITEM_SEARCH, SERVICE_BILLING_ITEM_READ,
            "service.entity.search", "service.entity.read",
        },
    )
    row = next(row for row in report["rows"] if row["entity"] == entity)
    assert row["provider_can_query"] is True
    assert row["provider_user_query_access"] == "None"
    assert row["assessment"] == "provider_user_query_denied"
    assert row["live_record_read_verified"] is False
    assert row["disclosure_negative_tests_verified"] is False


@pytest.mark.parametrize("capability,entity,field,value", [
    (SERVICE_INVOICE_SEARCH, "Invoices", "invoiceNumber", "INV-4"),
    (SERVICE_BILLING_ITEM_SEARCH, "BillingItems", "invoiceID", 4),
    (SERVICE_PURCHASE_ORDER_SEARCH, "PurchaseOrders", "purchaseOrderNumber", "PO-4"),
    (SERVICE_PURCHASE_ORDER_ITEM_SEARCH, "PurchaseOrderItems", "orderID", 4),
])
def test_financial_reads_keep_exact_provider_filters(capability, entity, field, value):
    selectors = {
        SERVICE_INVOICE_SEARCH: {"invoice_number": value},
        SERVICE_BILLING_ITEM_SEARCH: {"invoice_id": value},
        SERVICE_PURCHASE_ORDER_SEARCH: {"purchase_order_number": value},
        SERVICE_PURCHASE_ORDER_ITEM_SEARCH: {"purchase_order_id": value},
    }
    result = adapt_autotask_arguments(capability, {**selectors[capability], "page_size": 2})
    assert result["entity"] == entity
    query = json.loads(result["search"])
    assert query["MaxRecords"] == 2
    assert query["filter"] == [{"op": "eq", "field": field, "value": value}]


@pytest.mark.parametrize("capability,entity", [
    (SERVICE_INVOICE_READ, "Invoices"),
    (SERVICE_BILLING_ITEM_READ, "BillingItems"),
    (SERVICE_PURCHASE_ORDER_READ, "PurchaseOrders"),
])
def test_financial_exact_record_reads_remain_entity_bound(capability, entity):
    assert adapt_autotask_arguments(capability, {"resource_id": 4}) == {
        "entity": entity, "entity_id": 4,
    }


def test_po_query_permissions_do_not_imply_financial_write_permission():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["entities"]["PurchaseOrders"]["userAccessForQuery"] == "All"
    assert evidence["entities"]["Invoices"]["userAccessForQuery"] == "None"
    assert evidence["entities"]["BillingItems"]["userAccessForQuery"] == "None"
