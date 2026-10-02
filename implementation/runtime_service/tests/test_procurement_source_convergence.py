from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jason_runtime.procurement_teams_flow import (
    ProcurementTeamsFlow,
    SQLiteProcurementSubmissionStore,
    _card,
)


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


class Binder:
    def bind(self, evidence):
        return SimpleNamespace(
            principal_id="person-requester",
            organization_id="aot",
            email_address="requester@teamaot.com",
        )


class Factory:
    def new_correlation_id(self):
        return "corr-source"


class Flow(ProcurementTeamsFlow):
    def _read(self, *, capability, arguments, **kwargs):
        if capability == "service.company.search":
            return {
                "data": {
                    "items": [
                        {
                            "id": 88,
                            "companyName": "Staples",
                            "webAddress": "https://www.staples.com",
                        }
                    ]
                }
            }
        if capability == "service.product.search":
            return {"data": {"items": []}}
        raise AssertionError(capability)


def _flow(tmp_path: Path) -> Flow:
    return Flow(
        identity_binder=Binder(),
        request_factory=Factory(),
        orchestrator=None,
        store=SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3"),
        worker=None,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )


def test_vendor_quote_and_url_use_same_submission_shape_and_card_controls(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_quote",
        "source_reference": "quote:STAPLES-Q-100",
        "source_capture_sha256": "a" * 64,
        "source_captured_at": NOW.isoformat(),
        "vendor": {"name": "Staples"},
        "product": {
            "name": "USB-C Dock",
            "sku": "DOCK-1",
            "unit_cost": "120.00",
        },
    }
    result = flow.handle_vendor_document(
        normalized=normalized,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
    )
    payload = flow.store.get(result["submission_id"])
    assert payload["source_kind"] == "vendor_quote"
    assert payload["source_reference"] == "quote:STAPLES-Q-100"
    assert payload["product"]["cost"] == "120.00"

    card = result["reply"]["card"]
    toggle_ids = {
        item["id"]
        for item in card["body"]
        if item.get("type") == "Input.Toggle"
    }
    assert toggle_ids == {"create_po", "create_client_quote"}
    input_ids = {item.get("id") for item in card["body"]}
    assert {"quantity", "customer_quantity", "aot_stock_quantity", "ticket_number"} <= input_ids


def test_card_source_is_not_a_second_procurement_execution_path(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:INV-200",
        "vendor": {"name": "Staples"},
        "product": {"name": "USB-C Dock", "unit_cost": 120},
    }
    result = flow.handle_vendor_document(
        normalized=normalized,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
    )
    payload = flow.store.get(result["submission_id"])
    # The document branch terminates at the same draft submission consumed by
    # handle_submit/execute_submission; it does not create a separate PO/quote state.
    assert payload["status"] == "draft"
    assert "create_po" not in payload
    assert "create_client_quote" not in payload
