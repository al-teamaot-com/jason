from pathlib import Path

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
            "reply": {
                "text": "Review the standard Jason procurement card.",
                "cards": [
                    {"type": "AdaptiveCard", "version": "1.4", "body": []},
                    {"type": "AdaptiveCard", "version": "1.4", "body": []},
                ],
            },
        }

    def handle_submit(self, **kwargs):
        self.submit_call = kwargs
        return {
            "status": "completed",
            "submission_id": kwargs["submission_id"],
            "reply": {"text": "Submitted; owner approval was sent."},
        }


def _wire(monkeypatch, flow):
    monkeypatch.setattr(
        server,
        "_authenticated_microsoft_transport_identity",
        lambda: ("tenant-a", "object-a"),
    )
    monkeypatch.setattr(server, "_runtime_procurement_flow", lambda: flow)
    monkeypatch.setattr(
        server,
        "_send_procurement_review_to_teams",
        lambda **kwargs: ("teams-msg-1", "teams-msg-2"),
    )


def test_process_procurement_invoice_routes_to_canonical_flow_and_teams(monkeypatch):
    flow = FakeFlow()
    _wire(monkeypatch, flow)

    result = server.process_procurement_invoice(
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

    assert result == {
        "status": "completed",
        "submission_id": "proc-123",
        "review_delivery": "jason_teams",
        "review_message_ids": ["teams-msg-1", "teams-msg-2"],
        "reply": {
            "text": (
                "Invoice received. Jason sent the standard procurement review "
                "card to Microsoft Teams. Follow the card; the workflow and "
                "approval path are fixed by AOT policy."
            )
        },
    }
    normalized = flow.draft_call["normalized"]
    assert normalized["source_kind"] == "vendor_invoice"
    assert normalized["vendor"]["name"] == "National AZON Inc."
    assert normalized["invoice_number"] == "PSI393904"
    assert normalized["invoice_total"] == "207.59"
    assert normalized["vendor_order_reference"] == "DS-1382-09302026"
    assert flow.draft_call["microsoft_tenant_id"] == "tenant-a"
    assert flow.draft_call["microsoft_object_id"] == "object-a"


def test_process_procurement_invoice_rejects_summary_without_lines(monkeypatch):
    flow = FakeFlow()
    _wire(monkeypatch, flow)

    result = server.process_procurement_invoice(
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


def test_non_owner_raw_procurement_mutation_is_rejected(monkeypatch):
    monkeypatch.setattr(
        server,
        "_authenticated_write_identity",
        lambda: ("person-arnold", "aot", "entra-oauth-bearer", None),
    )
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-al"}))

    result = server.execute_governed_capability(
        capability="service.purchase.order.create",
        arguments={"vendor_id": 759},
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "procurement_canonical_workflow_required"
    assert "process_procurement_invoice" in result["instruction"]


def test_submit_helper_is_not_mcp_exposed():
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "@mcp.tool()\ndef submit_procurement_draft(" not in source
    assert "@mcp.tool()\ndef process_procurement_invoice(" in source
