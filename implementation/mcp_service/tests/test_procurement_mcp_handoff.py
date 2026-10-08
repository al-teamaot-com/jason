from types import SimpleNamespace

from jason_mcp import server


class FakeFlow:
    def __init__(self):
        self.draft_call = None
        self.submit_call = None

    def handle_vendor_document(self, **kwargs):
        self.draft_call = kwargs
        return {
            "status": "completed",
            "submission_id": "proc-123",
            "reply": {"text": "Draft ready"},
        }

    def handle_submit(self, **kwargs):
        self.submit_call = kwargs
        return {
            "status": "completed",
            "submission_id": kwargs["submission_id"],
            "reply": {"text": "Submitted; owner approval was sent."},
        }


def _wire(monkeypatch, flow):
    monkeypatch.setattr(server, "_authenticated_microsoft_transport_identity", lambda: ("tenant-a", "object-a"))
    monkeypatch.setattr(server, "_runtime_procurement_flow", lambda: flow)


def test_create_procurement_invoice_draft_routes_to_canonical_flow(monkeypatch):
    flow = FakeFlow()
    _wire(monkeypatch, flow)

    result = server.create_procurement_invoice_draft(
        vendor_name="National AZON Inc.",
        invoice_number="PSI393904",
        source_reference="NationalAZON-PSI393904.pdf",
        lines=[
            {
                "name": "Print supply",
                "quantity": 1,
                "unit_cost": "207.59",
                "billing_frequency": "one_time",
            }
        ],
        invoice_total="207.59",
        vendor_order_reference="DS-1382-09302026",
        ship_to="DPR Construction",
    )

    assert result["status"] == "completed"
    assert result["submission_id"] == "proc-123"
    normalized = flow.draft_call["normalized"]
    assert normalized["source_kind"] == "vendor_invoice"
    assert normalized["vendor"]["name"] == "National AZON Inc."
    assert normalized["invoice_number"] == "PSI393904"
    assert normalized["invoice_total"] == "207.59"
    assert normalized["vendor_order_reference"] == "DS-1382-09302026"
    assert flow.draft_call["microsoft_tenant_id"] == "tenant-a"
    assert flow.draft_call["microsoft_object_id"] == "object-a"


def test_submit_procurement_draft_uses_canonical_approval_flow(monkeypatch):
    flow = FakeFlow()
    _wire(monkeypatch, flow)

    result = server.submit_procurement_draft(
        submission_id="proc-123",
        selections={
            "create_po": "true",
            "create_client_quote": "false",
            "at_part_number": "AZON-TEST",
            "item_class": "other",
            "retail_price": "207.59",
            "quantity": "1",
            "customer_quantity": "0",
            "aot_stock_quantity": "1",
            "billing_treatment": "no_charge_internal",
            "freight": "0",
            "tax": "0",
            "fees": "0",
        },
    )

    assert result["status"] == "completed"
    assert "owner approval was sent" in result["reply"]["text"]
    assert flow.submit_call["submission_id"] == "proc-123"
    assert flow.submit_call["microsoft_tenant_id"] == "tenant-a"
    assert flow.submit_call["microsoft_object_id"] == "object-a"
    assert flow.submit_call["selections"]["create_po"] == "true"


def test_create_procurement_invoice_draft_rejects_summary_without_lines(monkeypatch):
    flow = FakeFlow()
    _wire(monkeypatch, flow)

    result = server.create_procurement_invoice_draft(
        vendor_name="National AZON Inc.",
        invoice_number="PSI393904",
        source_reference="NationalAZON-PSI393904.pdf",
        lines=[],
    )

    assert result == {
        "status": "rejected",
        "error_code": "procurement_invoice_lines_required",
    }
    assert flow.draft_call is None
