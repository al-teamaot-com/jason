from pathlib import Path

import pytest

from jason_runtime.procurement_teams_flow import (
    ProcurementFlowError,
    ProcurementTeamsFlow,
    SQLiteProcurementSubmissionStore,
)


class RecordingWorker:
    def __init__(self, *, fail_on_item_number=None):
        self.calls = []
        self.fail_on_item_number = fail_on_item_number
        self.item_calls = 0

    def execute(
        self,
        *,
        capability_name,
        payload,
        submission,
        correlation_id,
        route_arguments=None,
    ):
        self.calls.append((capability_name, dict(payload)))
        if capability_name == "service.purchase.order.item.create":
            self.item_calls += 1
            if self.item_calls == self.fail_on_item_number:
                raise RuntimeError("simulated second-line interruption")
            resource_id = 500 + self.item_calls
        elif capability_name == "service.purchase.order.create":
            resource_id = 500
        else:
            resource_id = 500
        return {
            "data": {
                "jasonVerification": {
                    "resourceId": resource_id,
                }
            }
        }


def _flow(tmp_path: Path, worker: RecordingWorker):
    store = SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3")
    flow = ProcurementTeamsFlow(
        identity_binder=None,
        request_factory=None,
        orchestrator=None,
        store=store,
        worker=worker,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
        inventory_location_id=1,
    )
    return store, flow


def _submission(*, lines, total, tax="0.00", fees="0.00", source_count=None):
    return {
        "submission_id": "proc-multiline-test",
        "status": "approval_required",
        "digest": "digest-multiline",
        "requester_principal_id": "person-owner",
        "requester_name": "Al Davis",
        "source_url": "invoice:TEST-100",
        "create_po": True,
        "create_client_quote": False,
        "customer_quantity": 2,
        "aot_stock_quantity": 0,
        "quantity": 2,
        "ticket_id": None,
        "ticket_number": None,
        "ticket_company_id": 1221,
        "retail_price": "109.00",
        "at_part_number": "PART-1",
        "freight": "35.37",
        "tax": tax,
        "fees": fees,
        "total_commitment": total,
        "product": {
            "name": "Primary Product",
            "cost": "86.11",
            "existing_product_id": 29682946,
        },
        "vendor": {
            "id": 759,
            "name": "National AZON",
        },
        "po_lines": lines,
        "source_item_count": (
            source_count if source_count is not None else len(lines)
        ),
        "quote_context": {},
    }


def _line(
    line_id,
    *,
    product_id,
    qty,
    cost,
    customer=0,
    stock=0,
    disposition="purchase_order_item",
    description=None,
):
    return {
        "line_id": line_id,
        "description": description or line_id,
        "quantity": qty,
        "unit_cost": cost,
        "product_id": product_id,
        "customer_quantity": customer,
        "aot_stock_quantity": stock,
        "disposition": disposition,
    }


def test_multiline_po_writes_every_resolved_product_before_submit(tmp_path):
    lines = [
        _line("line-1", product_id=101, qty=2, cost="10.00", customer=2),
        _line("line-2", product_id=102, qty=1, cost="5.00", stock=1),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(lines=lines, total="60.37")
    store.put_new(submission["submission_id"], submission)

    result = flow.execute_submission(submission, owner_approval_id="approval-1")

    capabilities = [call[0] for call in worker.calls]
    assert capabilities == [
        "service.purchase.order.create",
        "service.purchase.order.item.create",
        "service.purchase.order.item.create",
        "service.purchase.order.update",
    ]
    assert worker.calls[1][1]["productID"] == 101
    assert worker.calls[2][1]["productID"] == 102
    assert worker.calls[3][1] == {"id": 500, "status": 2}

    persisted = store.get(submission["submission_id"])
    assert persisted["status"] == "ordered"
    assert persisted["result"]["po_line_plan_verified"] is True
    assert persisted["result"]["purchase_order_item_ids"] == {
        "line-1": 501,
        "line-2": 502,
    }
    assert "PO 500" in result["summary"]


def test_source_count_mismatch_fails_before_any_provider_write(tmp_path):
    lines = [
        _line("line-1", product_id=101, qty=1, cost="10.00", stock=1),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(
        lines=lines,
        total="45.37",
        source_count=2,
    )
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(
        ProcurementFlowError,
        match="does not represent every source item",
    ):
        flow.execute_submission(submission, owner_approval_id="approval-1")

    assert worker.calls == []


def test_unresolved_paid_line_fails_before_po_creation(tmp_path):
    lines = [
        _line("line-1", product_id=None, qty=1, cost="10.00", stock=1),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(lines=lines, total="45.37")
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(
        ProcurementFlowError,
        match="not resolved to an Autotask product",
    ):
        flow.execute_submission(submission, owner_approval_id="approval-1")

    assert worker.calls == []


def test_total_mismatch_fails_before_po_creation(tmp_path):
    lines = [
        _line("line-1", product_id=101, qty=1, cost="10.00", stock=1),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(lines=lines, total="99.99")
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(
        ProcurementFlowError,
        match="does not reconcile",
    ):
        flow.execute_submission(submission, owner_approval_id="approval-1")

    assert worker.calls == []


@pytest.mark.parametrize(
    ("tax", "fees", "message"),
    [
        ("1.00", "0.00", "nonzero tax"),
        ("0.00", "1.00", "nonzero fees"),
    ],
)
def test_unmapped_tax_or_fees_fail_closed_before_po_creation(
    tmp_path,
    tax,
    fees,
    message,
):
    lines = [
        _line("line-1", product_id=101, qty=1, cost="10.00", stock=1),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    total = str(10 + 35.37 + float(tax) + float(fees))
    submission = _submission(
        lines=lines,
        total=total,
        tax=tax,
        fees=fees,
    )
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(ProcurementFlowError, match=message):
        flow.execute_submission(submission, owner_approval_id="approval-1")

    assert worker.calls == []


def test_zero_cost_informational_line_is_preserved_in_po_memo(tmp_path):
    lines = [
        _line("paper", product_id=101, qty=2, cost="86.11", customer=2),
        _line(
            "free-roll-holder",
            product_id=None,
            qty=1,
            cost="0.00",
            stock=1,
            disposition="informational_no_charge",
            description="CIRH235 / 1153C006AA RH2-35 Roll Holder",
        ),
    ]
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(lines=lines, total="207.59")
    store.put_new(submission["submission_id"], submission)

    flow.execute_submission(submission, owner_approval_id="approval-1")

    capabilities = [call[0] for call in worker.calls]
    assert capabilities == [
        "service.purchase.order.create",
        "service.purchase.order.item.create",
        "service.purchase.order.update",
    ]
    po_payload = worker.calls[0][1]
    assert "free-roll-holder" in po_payload["generalMemo"]
    assert "RH2-35 Roll Holder" in po_payload["generalMemo"]
    assert po_payload["freight"] == 35.37


def test_partial_multiline_retry_does_not_duplicate_first_po_item(tmp_path):
    lines = [
        _line("line-1", product_id=101, qty=1, cost="10.00", stock=1),
        _line("line-2", product_id=102, qty=1, cost="5.00", stock=1),
    ]
    first_worker = RecordingWorker(fail_on_item_number=2)
    store, first_flow = _flow(tmp_path, first_worker)
    submission = _submission(lines=lines, total="50.37")
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(RuntimeError, match="second-line interruption"):
        first_flow.execute_submission_with_retry_state(
            submission,
            owner_approval_id="approval-1",
        )

    checkpoint = store.get(submission["submission_id"])
    assert checkpoint["status"] == "failed_retryable"
    assert checkpoint["result"]["purchase_order_id"] == 500
    assert checkpoint["result"]["purchase_order_item_ids"] == {
        "line-1": 501,
    }
    assert checkpoint["result"]["purchase_order_submitted"] is False

    second_worker = RecordingWorker()
    second_flow = ProcurementTeamsFlow(
        identity_binder=None,
        request_factory=None,
        orchestrator=None,
        store=store,
        worker=second_worker,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
        inventory_location_id=1,
    )
    current = store.get(submission["submission_id"])
    second_flow.execute_submission_with_retry_state(
        current,
        owner_approval_id="approval-1",
    )

    capabilities = [call[0] for call in second_worker.calls]
    assert capabilities == [
        "service.purchase.order.item.create",
        "service.purchase.order.update",
    ]
    assert second_worker.calls[0][1]["productID"] == 102
    persisted = store.get(submission["submission_id"])
    assert persisted["result"]["purchase_order_item_ids"] == {
        "line-1": 501,
        "line-2": 501,
    }
    assert persisted["result"]["purchase_order_submitted"] is True


def test_legacy_multiline_declaration_without_line_plan_fails_closed(tmp_path):
    worker = RecordingWorker()
    store, flow = _flow(tmp_path, worker)
    submission = _submission(
        lines=[_line("line-1", product_id=101, qty=1, cost="10.00", stock=1)],
        total="45.37",
    )
    submission.pop("po_lines")
    submission["source_item_count"] = 2
    store.put_new(submission["submission_id"], submission)

    with pytest.raises(
        ProcurementFlowError,
        match="no approved PO line plan",
    ):
        flow.execute_submission(submission, owner_approval_id="approval-1")

    assert worker.calls == []
