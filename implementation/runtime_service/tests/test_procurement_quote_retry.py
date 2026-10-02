from pathlib import Path

import pytest

from jason_runtime.procurement_teams_flow import (
    ProcurementTeamsFlow,
    SQLiteProcurementSubmissionStore,
)


class Worker:
    def __init__(self, *, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.ids = {
            "service.opportunity.create": 1001,
            "service.quote.location.create": 1002,
            "service.quote.create": 1003,
            "service.quote.item.create": 1004,
        }

    def execute(self, *, capability_name, payload, submission, correlation_id, route_arguments=None):
        self.calls.append((capability_name, dict(payload), dict(route_arguments or {})))
        if capability_name == self.fail_on:
            raise RuntimeError("simulated provider interruption")
        return {"data": {"jasonVerification": {"resourceId": self.ids[capability_name]}}}


def _submission():
    return {
        "submission_id": "proc-retry",
        "status": "submitted",
        "digest": "digest-retry",
        "requester_principal_id": "person-requester",
        "requester_name": "Requester",
        "source_url": "https://vendor.example/item",
        "create_po": False,
        "create_client_quote": True,
        "customer_quantity": 1,
        "aot_stock_quantity": 0,
        "quantity": 1,
        "ticket_id": 123,
        "ticket_number": "T20261002.0001",
        "ticket_company_id": 42,
        "retail_price": "199.00",
        "at_part_number": "PART-1",
        "freight": "0.00",
        "product": {
            "name": "Dock",
            "cost": "120.00",
            "existing_product_id": 456,
        },
        "vendor": {"id": 88},
        "quote_context": {
            "owner_resource_id": 77,
            "company": {
                "address1": "1202 W Little Creek Rd",
                "city": "Norfolk",
                "state": "VA",
                "postalCode": "23505",
            },
        },
    }


def _flow(store, worker):
    return ProcurementTeamsFlow(
        identity_binder=None,
        request_factory=None,
        orchestrator=None,
        store=store,
        worker=worker,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )


def test_client_quote_retry_resumes_from_persisted_readback_checkpoints(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3")
    submission = _submission()
    store.put_new(submission["submission_id"], submission)

    first = Worker(fail_on="service.quote.item.create")
    with pytest.raises(RuntimeError, match="simulated provider interruption"):
        _flow(store, first).execute_submission(submission, owner_approval_id=None)

    checkpoint = store.get(submission["submission_id"])["result"]
    assert checkpoint["opportunity_id"] == 1001
    assert checkpoint["quote_location_id"] == 1002
    assert checkpoint["client_quote_id"] == 1003
    assert checkpoint["quote_item_id"] is None

    second = Worker()
    result = _flow(store, second).execute_submission(submission, owner_approval_id=None)
    assert [call[0] for call in second.calls] == ["service.quote.item.create"]
    assert second.calls[0][2] == {"quoteID": 1003}
    assert "client quote 1003" in result["summary"]
    persisted = store.get(submission["submission_id"])["result"]
    assert persisted["client_quote_id"] == 1003
    assert persisted["quote_item_id"] == 1004


class VendorWorker:
    def __init__(self, *, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.ids = {
            "service.vendor.create": 700,
            "service.product.create": 701,
            "service.product.vendor.create": 702,
        }

    def execute(self, *, capability_name, payload, submission, correlation_id, route_arguments=None):
        self.calls.append((capability_name, dict(payload), dict(route_arguments or {})))
        if capability_name == self.fail_on:
            raise RuntimeError("simulated provider interruption")
        return {"data": {"jasonVerification": {"resourceId": self.ids[capability_name]}}}


def _missing_vendor_submission():
    return {
        "submission_id": "proc-vendor-retry",
        "status": "submitted",
        "digest": "digest-vendor-retry",
        "requester_principal_id": "person-requester",
        "requester_name": "Requester",
        "source_url": "https://www.newegg.com/p/example",
        "create_po": False,
        "create_client_quote": False,
        "customer_quantity": 0,
        "aot_stock_quantity": 1,
        "quantity": 1,
        "ticket_id": None,
        "ticket_number": None,
        "ticket_company_id": None,
        "retail_price": "29.95",
        "at_part_number": "USBC-TVGA",
        "freight": "0.00",
        "product": {
            "name": "Plugable USB C to VGA Adapter",
            "cost": "19.95",
            "mpn": "USBC-TVGA",
            "existing_product_id": None,
        },
        "vendor": {
            "id": None,
            "name": "Plugable Technologies",
            "needs_create": True,
            "source": {"name": "Plugable Technologies"},
        },
        "quote_context": {},
    }


def test_missing_vendor_retry_reuses_persisted_vendor_before_product(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "vendor-retry.sqlite3")
    submission = _missing_vendor_submission()
    store.put_new(submission["submission_id"], submission)

    first = VendorWorker(fail_on="service.product.create")
    with pytest.raises(RuntimeError, match="simulated provider interruption"):
        _flow(store, first).execute_submission(submission, owner_approval_id=None)

    assert [call[0] for call in first.calls] == [
        "service.vendor.create",
        "service.product.create",
    ]
    checkpoint = store.get(submission["submission_id"])["result"]
    assert checkpoint["vendor_id"] == 700
    assert checkpoint["created_vendor"] is True

    second = VendorWorker()
    result = _flow(store, second).execute_submission(submission, owner_approval_id=None)
    assert [call[0] for call in second.calls] == [
        "service.product.create",
        "service.product.vendor.create",
    ]
    assert second.calls[0][1]["defaultVendorID"] == 700
    assert second.calls[1][1]["vendorID"] == 700
    assert "Catalog product 701" in result["summary"]
