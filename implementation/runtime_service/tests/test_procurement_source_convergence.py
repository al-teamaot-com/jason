from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jason_runtime.procurement_teams_flow import (
    PROCUREMENT_WRITE_CAPABILITIES,
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
