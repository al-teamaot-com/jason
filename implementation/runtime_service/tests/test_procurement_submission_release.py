from datetime import datetime, timezone

import pytest

from jason_runtime.procurement_teams_flow import (
    ProcurementFlowError,
    SQLiteProcurementSubmissionStore,
)


def _submission():
    return {
        "submission_id": "procsub-test",
        "status": "ordered",
        "quantity": 2,
        "customer_quantity": 1,
        "aot_stock_quantity": 1,
        "ticket_id": 123,
        "ticket_number": "T20261002.0001",
        "billing_treatment": "charge_ticket",
        "billing_disposition": "pending_receipt",
        "release_state": "ordered",
    }


def test_receiving_does_not_release_customer_stock(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3")
    store.put_new("procsub-test", _submission())
    received = store.record_receipt("procsub-test", received_quantity=2)
    assert received["received_quantity"] == 2
    assert received["release_state"] == "received_pending_disposition"
    assert received.get("released_quantity", 0) == 0

    with pytest.raises(ProcurementFlowError, match="billing disposition"):
        store.release_stock("procsub-test", release_quantity=1)

    ready = store.record_billing_disposition(
        "procsub-test", disposition="existing_unbilled_charge"
    )
    assert ready["release_state"] == "ready_for_release"

    released = store.release_stock("procsub-test", release_quantity=1)
    assert released["release_state"] == "released"
    assert released["released_quantity"] == 1


def test_aot_stock_receipt_does_not_require_customer_billing(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3")
    payload = {
        **_submission(),
        "submission_id": "stock-only",
        "quantity": 2,
        "customer_quantity": 0,
        "aot_stock_quantity": 2,
        "ticket_id": None,
        "ticket_number": None,
        "billing_disposition": "no_customer_allocation",
    }
    store.put_new("stock-only", payload)
    received = store.record_receipt("stock-only", received_quantity=2)
    assert received["release_state"] == "ready_for_release"
    assert received["status"] == "received"
