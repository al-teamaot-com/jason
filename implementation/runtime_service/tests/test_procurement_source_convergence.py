import pytest

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jason_runtime.procurement_teams_flow import (
    PROCUREMENT_WRITE_CAPABILITIES,
    ProcurementFlowError,
    ProcurementTeamsFlow,
    SQLiteProcurementSubmissionStore,
    _card,
    _cards,
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


class MissingVendorFlow(ProcurementTeamsFlow):
    def _read(self, *, capability, arguments, **kwargs):
        if capability == "service.company.search":
            return {"data": {"items": []}}
        if capability == "service.product.search":
            return {"data": {"items": []}}
        raise AssertionError(capability)


def test_missing_vendor_becomes_explicit_creation_proposal(tmp_path):
    flow = MissingVendorFlow(
        identity_binder=Binder(),
        request_factory=Factory(),
        orchestrator=None,
        store=SQLiteProcurementSubmissionStore(tmp_path / "missing-vendor.sqlite3"),
        worker=None,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )
    normalized = {
        "source_kind": "vendor_quote",
        "source_reference": "quote:NEW-VENDOR",
        "vendor": {"name": "Plugable Technologies"},
        "product": {
            "name": "USB-C to VGA Adapter",
            "mpn": "USBC-TVGA",
            "unit_cost": "19.95",
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
    assert payload["vendor"]["id"] is None
    assert payload["vendor"]["needs_create"] is True
    assert "creation proposed" in payload["vendor"]["verification_summary"]
    assert "create the Vendor record first" in result["reply"]["text"]



class RequesterResourceFlow(ProcurementTeamsFlow):
    def _read(self, *, capability, arguments, **kwargs):
        assert capability == "service.resource.search"
        assert arguments["email"] == "al@teamaot.com"
        return {
            "data": {
                "items": [
                    {
                        "id": 29682885,
                        "email": "al@teamaot.com",
                        "firstName": "Al",
                        "lastName": "Davis",
                        "isActive": True,
                    },
                    {
                        "id": 29682902,
                        "email": "al@teamaot.com",
                        "firstName": "DarkWeb",
                        "lastName": "API",
                        "isActive": False,
                    },
                ]
            }
        }


def test_requester_resource_ignores_inactive_email_duplicates(tmp_path):
    flow = RequesterResourceFlow(
        identity_binder=Binder(),
        request_factory=Factory(),
        orchestrator=None,
        store=SQLiteProcurementSubmissionStore(tmp_path / "resource.sqlite3"),
        worker=None,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )
    resource = flow._requester_resource(
        email="al@teamaot.com",
        principal=SimpleNamespace(principal_id="person-requester"),
        evidence=SimpleNamespace(),
        correlation_id="corr-resource",
    )
    assert resource["id"] == 29682885
    assert resource["isActive"] is True



def test_procurement_worker_authority_includes_vendor_creation():
    assert "service.vendor.create" in PROCUREMENT_WRITE_CAPABILITIES


def test_vendor_api_source_converges_on_same_draft_with_high_confidence(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_api",
        "source_reference": "api:vendor/item/USBC-TVGA",
        "source_capture_sha256": "b" * 64,
        "source_captured_at": NOW.isoformat(),
        "source_acquisition": "vendor_api",
        "source_confidence": "vendor_api",
        "source_evidence_mode": "authenticated_vendor_api",
        "vendor": {"name": "Staples"},
        "product": {
            "name": "USB-C VGA Adapter",
            "mpn": "USBC-TVGA",
            "sku": "VENDOR-123",
            "upc": "819927012221",
            "unit_cost": "19.95",
        },
    }
    result = flow.handle_normalized_source(
        normalized=normalized,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
    )
    payload = flow.store.get(result["submission_id"])
    assert payload["status"] == "draft"
    assert payload["source_kind"] == "vendor_api"
    assert payload["source_acquisition"] == "vendor_api"
    assert payload["source_confidence"] == "vendor_api"
    assert payload["source_confidence_score"] == 100
    assert payload["source_evidence_mode"] == "authenticated_vendor_api"
    assert payload["product"]["mpn"] == "USBC-TVGA"
    assert payload["product"]["upc"] == "819927012221"


def test_structured_file_source_converges_without_parallel_execution_path(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_csv",
        "source_reference": "csv:vendor-feed-20261002.csv#row=42",
        "source_capture_sha256": "c" * 64,
        "source_captured_at": NOW.isoformat(),
        "source_acquisition": "structured_file",
        "source_confidence": "structured_file",
        "source_evidence_mode": "csv_row",
        "vendor": {"name": "Staples"},
        "product": {
            "name": "USB-C Dock",
            "mpn": "DOCK-MPN-1",
            "sku": "ROW-42",
            "unit_cost": "120.00",
        },
    }
    result = flow.handle_normalized_source(
        normalized=normalized,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
    )
    payload = flow.store.get(result["submission_id"])
    assert payload["status"] == "draft"
    assert payload["source_kind"] == "vendor_csv"
    assert payload["source_acquisition"] == "structured_file"
    assert payload["source_confidence"] == "structured_file"
    assert payload["source_confidence_score"] == 90
    assert "create_po" not in payload
    assert "create_client_quote" not in payload


def test_document_defaults_preserve_existing_quote_invoice_behavior(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:INV-201",
        "vendor": {"name": "Staples"},
        "product": {"name": "USB-C Dock", "unit_cost": "120.00"},
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
    assert payload["source_acquisition"] == "document_extraction"
    assert payload["source_confidence"] == "document_verified"
    assert payload["source_confidence_score"] == 85
    assert payload["source_evidence_mode"] == "document_normalized"


class TicketUrlFlow(ProcurementTeamsFlow):
    def _read(self, *, capability, arguments, **kwargs):
        if capability == "service.ticket.search":
            assert arguments["ticket_number"] == "T20191013.0001"
            return {
                "data": {
                    "items": [
                        {
                            "id": 8870,
                            "ticketNumber": "T20191013.0001",
                            "companyID": 1158,
                            "title": "test ticket",
                        }
                    ]
                }
            }
        if capability == "procurement.web.product.read":
            return {
                "products": [
                    {
                        "name": "Plugable USB C to VGA Adapter",
                        "mpn": "USBC-TVGA",
                        "sku": "9SIA2XBBKZ0313",
                        "price": "19.95",
                        "seller": "Plugable Technologies",
                    }
                ],
                "organizations": [{"name": "Plugable Technologies"}],
                "final_url": "https://www.newegg.com/p/2VF-0046-00012",
                "content_sha256": "d" * 64,
                "captured_at": NOW.isoformat(),
                "evidence_mode": "rendered_commerce_fallback",
                "source_host": "www.newegg.com",
            }
        if capability == "service.company.search":
            return {"data": {"items": []}}
        if capability == "service.product.search":
            return {"data": {"items": []}}
        raise AssertionError(capability)


def test_url_ticket_hint_is_verified_and_prefilled_in_card(tmp_path):
    flow = TicketUrlFlow(
        identity_binder=Binder(),
        request_factory=Factory(),
        orchestrator=None,
        store=SQLiteProcurementSubmissionStore(tmp_path / "ticket-url.sqlite3"),
        worker=None,
        approval_service=None,
        approval_sender=None,
        owner_ids=(),
    )
    result = flow.handle_url(
        url="https://www.newegg.com/p/2VF-0046-00012",
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
        ticket_number_hint="T20191013.0001",
    )
    payload = flow.store.get(result["submission_id"])
    assert payload["ticket_number_hint"] == "T20191013.0001"
    ticket_input = next(
        item for item in result["reply"]["card"]["body"]
        if item.get("id") == "ticket_number"
    )
    assert ticket_input["value"] == "T20191013.0001"

def test_multi_line_invoice_renders_part_cards_plus_one_po_card(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:42838110-00",
        "invoice_number": "42838110-00",
        "vendor_order_reference": "1405-092826",
        "payment_status": "paid_credit_card",
        "invoice_total": "208.65",
        "vendor": {"name": "Staples"},
        "lines": [
            {
                "name": "TK6357 Black Toner",
                "sku": "KYOTK6357",
                "mpn": "TK6357",
                "unit_cost": "91.25",
                "quantity": 2,
            },
            {
                "name": "WT8500 Waste Container",
                "sku": "KYOWT8500",
                "mpn": "WT8500",
                "unit_cost": "14.15",
                "quantity": 1,
            },
        ],
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
    assert len(payload["parts"]) == 2
    assert payload["invoice_number"] == "42838110-00"
    cards = result["reply"]["cards"]
    assert len(cards) == 3
    assert cards[0]["body"][0]["style"] == "accent"
    assert cards[1]["body"][0]["style"] == "accent"
    assert cards[2]["body"][0]["style"] == "emphasis"
    assert cards[2]["body"][0]["items"][0]["text"].startswith("🟪 PURCHASE ORDER")


def test_part_card_save_only_updates_jason_draft_state(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:INV-DRYRUN",
        "vendor": {"name": "Staples"},
        "product": {
            "name": "TK6357 Black Toner",
            "sku": "KYOTK6357",
            "mpn": "TK6357",
            "unit_cost": "91.25",
            "quantity": 2,
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
    saved = flow.handle_submit(
        submission_id=result["submission_id"],
        selections={
            "card_stage": "part",
            "part_index": "0",
            "at_part_number": "TK6357",
            "item_class": "copy_print",
            "retail_price": "123.00",
            "quantity": "2",
            "customer_quantity": "0",
            "aot_stock_quantity": "2",
            "billing_treatment": "no_charge_internal",
        },
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        channel_response_id="msg-save",
        submitted_at=NOW,
    )
    payload = flow.store.get(result["submission_id"])
    assert payload["status"] == "draft"
    assert payload["part_resolutions"]["0"]["at_part_number"] == "TK6357"
    assert payload["part_resolutions"]["0"]["item_class"] == "copy_print"
    assert saved["reply"]["text"].endswith("No provider write was performed.")


def test_multi_part_po_process_fails_closed_during_teams_acceptance(tmp_path):
    flow = _flow(tmp_path)
    normalized = {
        "source_kind": "vendor_invoice",
        "source_reference": "invoice:INV-MULTI",
        "vendor": {"name": "Staples"},
        "lines": [
            {"name": "Part A", "sku": "A", "unit_cost": "10.00"},
            {"name": "Part B", "sku": "B", "unit_cost": "20.00"},
        ],
    }
    result = flow.handle_vendor_document(
        normalized=normalized,
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conv",
        message_id="msg",
        occurred_at=NOW,
    )
    for index, part in enumerate(("A", "B")):
        flow.handle_submit(
            submission_id=result["submission_id"],
            selections={
                "card_stage": "part",
                "part_index": str(index),
                "at_part_number": part,
                "item_class": "copy_print",
                "retail_price": "30.00",
                "quantity": "1",
                "customer_quantity": "0",
                "aot_stock_quantity": "1",
                "billing_treatment": "no_charge_internal",
            },
            microsoft_tenant_id="tenant",
            microsoft_object_id="object",
            conversation_id="conv",
            channel_response_id=f"msg-save-{index}",
            submitted_at=NOW,
        )

    with pytest.raises(
        ProcurementFlowError,
        match="Multi-part PO execution is intentionally blocked",
    ):
        flow.handle_submit(
            submission_id=result["submission_id"],
            selections={
                "card_stage": "po",
                "create_po": "true",
                "create_client_quote": "false",
                "ticket_number": "",
                "freight": "0",
                "tax": "0",
                "fees": "0",
            },
            microsoft_tenant_id="tenant",
            microsoft_object_id="object",
            conversation_id="conv",
            channel_response_id="msg-po",
            submitted_at=NOW,
        )
        )
