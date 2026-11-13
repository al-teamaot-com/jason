"""Bounded invoice financial fidelity through the same Jason PO workflow.

No direct Autotask access. All provider-facing paths are fakes and must fail
before any mutation when source math or source-specified quantities change.
"""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from jason_runtime.procurement_invoice_fidelity import (
    InvoiceFidelityError,
    summarize_vendor_invoice,
    validate_invoice_submission,
)
from jason_runtime.procurement_teams_flow import (
    ProcurementFlowError,
    ProcurementTeamsFlow,
    SQLiteProcurementSubmissionStore,
)

NOW = datetime(2026, 10, 29, 14, 30, tzinfo=timezone.utc)


def _invoice(*, total="205.00", freight="5.00", tax="0", fees="0", qty=2):
    return {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:TEST-205",
        "vendor": {"name": "Staples"},
        "invoice_total": total,
        "freight": freight,
        "tax": tax,
        "fees": fees,
        "lines": [{"name": "USB-C dock", "sku": "DOCK-A",
                   "quantity": qty, "unit_cost": "100.00"}],
    }


class Binder:
    def bind(self, evidence):
        return SimpleNamespace(
            principal_id="aot-requester",
            organization_id="aot",
            email_address="requester@teamaot.com",
        )


class Factory:
    def new_correlation_id(self):
        return "corr-invoice-fidelity"


class DraftFlow(ProcurementTeamsFlow):
    def _read(self, *, capability, **kwargs):
        if capability == "service.company.search":
            return {"data": {"items": [{"id": 88, "companyName": "Staples"}]}}
        if capability == "service.product.search":
            return {"data": {"items": [{"id": 42, "name": "USB-C dock", "sku": "DOCK-A"}]}}
        raise AssertionError("Unexpected provider read before invoice validation: " + capability)


def _flow(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "invoice-fidelity.sqlite3")
    flow = DraftFlow(
        identity_binder=Binder(),
        request_factory=Factory(),
        orchestrator=None,
        store=store,
        worker=None,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )
    return store, flow


def _ingest(flow, source):
    return flow.handle_vendor_document(
        normalized=source,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conversation",
        message_id="message",
        occurred_at=NOW,
    )


def _choices(*, quantity="2", freight="5", tax="0", fees="0"):
    return {
        "create_po": "true",
        "create_client_quote": "false",
        "at_part_number": "DOCK-A",
        "item_class": "it",
        "retail_price": "135.00",
        "quantity": quantity,
        "customer_quantity": "0",
        "aot_stock_quantity": quantity,
        "billing_treatment": "no_charge_internal",
        "freight": freight,
        "tax": tax,
        "fees": fees,
    }


def _submit(flow, submission_id, **kwargs):
    return flow.handle_submit(
        submission_id=submission_id,
        selections=_choices(**kwargs),
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conversation",
        channel_response_id="submission-message",
        submitted_at=NOW,
    )


def test_invoice_source_math_exact_cents_and_shipping():
    source = _invoice(total="230.50", freight="15.00", tax="10.00", fees="5.50")
    proof = summarize_vendor_invoice(source, source["lines"])
    assert proof == {
        "status": "matched",
        "source_total": "230.50",
        "line_total": "200.00",
        "calculated_total": "230.50",
        "difference": "0.00",
    }


def test_missing_invoice_total_is_unverified_not_zero_or_matched():
    source = _invoice(total="")
    assert summarize_vendor_invoice(source, source["lines"]) == {}
    assert summarize_vendor_invoice({**source, "source_kind": "vendor_quote"}, source["lines"]) == {}


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-3.00", "1.001", "invalid"])
def test_invalid_source_invoice_total_is_rejected(bad):
    source = _invoice(total=bad)
    with pytest.raises(InvoiceFidelityError):
        summarize_vendor_invoice(source, source["lines"])


def test_mismatch_shown_in_card_without_provider_write(tmp_path):
    store, flow = _flow(tmp_path)
    result = _ingest(flow, _invoice(total="206.00"))
    saved = store.get(result["submission_id"])
    assert saved["status"] == "draft"
    assert saved["invoice_reconciliation"]["status"] == "mismatch"
    facts = result["reply"]["cards"][-1]["body"][1]["facts"]
    assert any(f["title"] == "Invoice reconciliation" and "MISMATCH" in f["value"]
               for f in facts)
    assert any(f["title"] == "Unexplained difference" and f["value"] == "$1.00"
               for f in facts)
    with pytest.raises(ProcurementFlowError, match="Source invoice total"):
        _submit(flow, result["submission_id"])
    assert store.get(result["submission_id"])["status"] == "draft"


def test_invoice_amounts_populate_review_card_and_first_quantity(tmp_path):
    store, flow = _flow(tmp_path)
    result = _ingest(
        flow,
        _invoice(total="230.50", freight="15.00", tax="10.00", fees="5.50"),
    )
    saved = store.get(result["submission_id"])
    assert saved["invoice_reconciliation"]["status"] == "matched"
    assert saved["parts"][0]["quantity"] == 2
    po_card = result["reply"]["cards"][-1]
    inputs = {item.get("id"): item for item in po_card["body"] if item.get("id")}
    assert inputs["freight"]["value"] == 15
    assert inputs["tax"]["value"] == 10
    assert inputs["fees"]["value"] == 5.5
    facts = po_card["body"][1]["facts"]
    assert any(f["title"] == "Invoice reconciliation" and f["value"] == "Matched"
               for f in facts)


def test_source_invoice_quantity_cannot_be_changed_at_submission(tmp_path):
    store, flow = _flow(tmp_path)
    result = _ingest(flow, _invoice())
    with pytest.raises(ProcurementFlowError, match="Selected quantity differs"):
        _submit(flow, result["submission_id"], quantity="1")
    assert store.get(result["submission_id"])["status"] == "draft"


def test_source_invoice_freight_cannot_be_omitted_at_submission(tmp_path):
    store, flow = _flow(tmp_path)
    result = _ingest(flow, _invoice())
    with pytest.raises(ProcurementFlowError, match="Selected freight differs"):
        _submit(flow, result["submission_id"], freight="0")
    assert store.get(result["submission_id"])["status"] == "draft"


def test_nonzero_tax_is_blocked_before_authority_or_provider_write(tmp_path):
    store, flow = _flow(tmp_path)
    result = _ingest(
        flow,
        _invoice(total="215.00", freight="5.00", tax="10.00"),
    )
    with pytest.raises(ProcurementFlowError, match="cannot yet preserve nonzero tax/fees"):
        _submit(flow, result["submission_id"], tax="10")
    assert store.get(result["submission_id"])["status"] == "draft"


def test_invoice_preflight_consistent_does_not_grant_purchasing_authority(tmp_path):
    _, flow = _flow(tmp_path)
    result = _ingest(flow, _invoice())
    saved = flow.store.get(result["submission_id"])
    validate_invoice_submission(
        saved, quantity=2, freight=Decimal("5"), tax=Decimal("0"), fees=Decimal("0"),
    )
    assert saved["status"] == "draft"
    assert "create_po" not in saved
    assert "requester_contact_id" not in saved


def test_multi_line_invoice_cannot_be_approved_as_one_line():
    source = _invoice(total="300.00", freight="0")
    source["lines"].append({"name": "Second device", "quantity": 1, "unit_cost": "100.00"})
    proof = summarize_vendor_invoice(source, source["lines"])
    assert proof["status"] == "matched"
    with pytest.raises(InvoiceFidelityError, match="Multi-line"):
        validate_invoice_submission(
            {**source, "parts": [{"cost": "100.00", "quantity": 2},
                                 {"cost": "100.00", "quantity": 1}],
             "invoice_reconciliation": proof},
            quantity=2, freight=Decimal("0"), tax=Decimal("0"), fees=Decimal("0"),
        )


class MutationRecorder:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("Provider write should never occur")


@pytest.mark.parametrize("field", ["tax", "fees"])
def test_legacy_single_line_po_cannot_silently_drop_financial_charges(tmp_path, field):
    store = SQLiteProcurementSubmissionStore(tmp_path / (field + ".sqlite3"))
    worker = MutationRecorder()
    flow = ProcurementTeamsFlow(
        identity_binder=None, request_factory=None, orchestrator=None,
        store=store, worker=worker, approval_service=None, approval_sender=None,
        owner_ids=(),
    )
    submission = {
        "submission_id": "legacy-" + field,
        "status": "submitted",
        "digest": "pinned",
        "create_po": True,
        "spending_limit": "100.00",
        "total_commitment": "21.00",
        field: "1.00",
    }
    store.put_new(submission["submission_id"], submission)
    with pytest.raises(ProcurementFlowError, match="nonzero " + field):
        flow.execute_submission(submission, owner_approval_id=None)
    assert worker.calls == []


class ExistingInvoicePOFlow(DraftFlow):
    """A governed exact vendor invoice lookup with a matching Autotask PO."""

    def _read(self, *, capability, arguments, **kwargs):
        if capability == "service.purchase.order.search":
            assert arguments == {
                "vendor_invoice_number": "INV-205",
                "vendor_id": 88,
                "page_size": 20,
            }
            return {"data": {"items": [
                {"id": 4567, "vendorID": 88, "vendorInvoiceNumber": "INV-205"},
            ]}}
        return super()._read(capability=capability, arguments=arguments, **kwargs)


def test_existing_invoice_po_is_blocked_before_new_po_or_approval(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "po-collision.sqlite3")
    flow = ExistingInvoicePOFlow(
        identity_binder=Binder(), request_factory=Factory(), orchestrator=None,
        store=store, worker=MutationRecorder(), approval_service=None,
        approval_sender=None, owner_ids=(),
    )
    source = {**_invoice(), "invoice_number": "INV-205"}
    result = _ingest(flow, source)
    with pytest.raises(ProcurementFlowError, match="ID 4567.*existing PO"):
        _submit(flow, result["submission_id"])
    assert store.get(result["submission_id"])["status"] == "draft"
    assert flow.worker.calls == []


def test_vendor_invoice_reference_must_be_bounded_before_mutation():
    from jason_runtime.procurement_teams_flow import _vendor_invoice_reference

    assert _vendor_invoice_reference({
        "source_kind": "vendor_invoice", "invoice_number": " INV-205 "
    }) == "INV-205"
    assert _vendor_invoice_reference({
        "source_kind": "vendor_quote", "invoice_number": "INV-205"
    }) is None
    for bad in ("x" * 51, "INV-205\nBAD", "INV-205\tBAD"):
        with pytest.raises(ProcurementFlowError, match="Vendor invoice number"):
            _vendor_invoice_reference({
                "source_kind": "vendor_invoice", "invoice_number": bad
            })


class VerifiedPOWorker:
    def __init__(self):
        self.calls = []

    def execute(self, *, capability_name, payload, **kwargs):
        self.calls.append((capability_name, dict(payload)))
        return {
            "data": {"jasonVerification": {
                "resourceId": 500 if capability_name != "service.purchase.order.item.create"
                else 501,
            }}
        }


def test_new_po_persists_vendor_invoice_number_using_governed_mutation_path(tmp_path):
    store = SQLiteProcurementSubmissionStore(tmp_path / "po-number.sqlite3")
    worker = VerifiedPOWorker()
    flow = ProcurementTeamsFlow(
        identity_binder=None, request_factory=None, orchestrator=None,
        store=store, worker=worker, approval_service=None, approval_sender=None,
        owner_ids=(),
    )
    submission = {
        "submission_id": "po-new-invoice",
        "digest": "source-pinned",
        "status": "submitted",
        "source_kind": "vendor_invoice",
        "invoice_number": "INV-205",
        "source_url": "invoice:INV-205",
        "requester_name": "AOT Technician",
        "requester_principal_id": "aot-requester",
        "requester_email": "requester@teamaot.com",
        "requester_microsoft_object_id": "ms-object",
        "create_po": True,
        "create_client_quote": False,
        "spending_limit": "1000.00",
        "effective_spending_threshold": "1000.00",
        "total_commitment": "205.00",
        "freight": "5.00", "tax": "0.00", "fees": "0.00",
        "quantity": 2, "customer_quantity": 2, "aot_stock_quantity": 0,
        "ticket_id": 7681, "ticket_number": "T20261029.0001",
        "ticket_company_id": 1158,
        "product": {"name": "USB-C dock", "cost": "100.00", "existing_product_id": 42},
        "vendor": {"name": "Staples", "id": 88},
        "po_lines": [{
            "line_id": "invoice-1", "description": "USB-C dock", "product_id": 42,
            "quantity": 2, "unit_cost": "100.00", "customer_quantity": 2,
            "aot_stock_quantity": 0,
        }],
        "source_item_count": 1,
    }
    store.put_new(submission["submission_id"], submission)
    result = flow.execute_submission(submission, owner_approval_id=None)
    assert result["result"]["purchase_order_id"] == 500
    assert worker.calls[0][0] == "service.purchase.order.create"
    assert worker.calls[0][1]["vendorInvoiceNumber"] == "INV-205"
    assert worker.calls[0][1]["externalPONumber"] == "T20261029.0001"
    assert worker.calls[0][1]["purchaseForCompanyID"] == 1158
    assert [cap for cap, _ in worker.calls] == [
        "service.purchase.order.create",
        "service.purchase.order.item.create",
        "service.purchase.order.update",
    ]


def test_client_estimate_and_purchase_cannot_be_committed_in_same_step(tmp_path):
    store, flow = _flow(tmp_path)
    quote = {
        "source_kind": "vendor_quote",
        "source_reference": "quote:STAPLES-QUOTE",
        "vendor": {"name": "Staples"},
        "product": {"name": "USB-C dock", "sku": "DOCK-A", "unit_cost": "100.00"},
    }
    result = _ingest(flow, quote)
    selections = _choices()
    selections["create_client_quote"] = "true"
    with pytest.raises(ProcurementFlowError, match="obtain client acceptance"):
        flow.handle_submit(
            submission_id=result["submission_id"], selections=selections,
            microsoft_tenant_id="tenant", microsoft_object_id="object",
            conversation_id="conversation", channel_response_id="submit-quote",
            submitted_at=NOW,
        )
    assert store.get(result["submission_id"])["status"] == "draft"


def test_invoice_with_more_than_100_lines_fails_without_storing_draft(tmp_path):
    store, flow = _flow(tmp_path)
    source = _invoice(total="")
    source["lines"] = [{"name": "Test", "unit_cost": "1.00"}] * 101
    with pytest.raises(ProcurementFlowError, match="exceeds the supported 100"):
        _ingest(flow, source)
    assert store.list_all() == ()


def test_execution_callback_rechecks_invoice_source_before_any_provider_write(tmp_path):
    source = _invoice(total="206.00")
    proof = summarize_vendor_invoice(source, source["lines"])
    store = SQLiteProcurementSubmissionStore(tmp_path / "tampered-approval.sqlite3")
    worker = MutationRecorder()
    flow = ProcurementTeamsFlow(
        identity_binder=None, request_factory=None, orchestrator=None,
        store=store, worker=worker, approval_service=None, approval_sender=None,
        owner_ids=(),
    )
    submission = {
        "submission_id": "callback-mismatch",
        "digest": "immutable-approval-digest",
        "status": "submitted",
        "create_po": True,
        "spending_limit": "1000.00",
        "total_commitment": "205.00",
        "effective_spending_threshold": "1000.00",
        "quantity": 2,
        "freight": "5.00", "tax": "0.00", "fees": "0.00",
        "parts": [{"cost": "100.00", "quantity": 2}],
        "invoice_reconciliation": proof,
    }
    store.put_new(submission["submission_id"], submission)
    with pytest.raises(ProcurementFlowError, match="no longer reconciles"):
        flow.execute_submission(submission, owner_approval_id=None)
    assert worker.calls == []
