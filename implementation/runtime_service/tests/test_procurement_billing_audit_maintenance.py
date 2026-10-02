from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from jason_runtime.procurement_billing_audit_maintenance import HardwareBillingAuditMaintenance
from jason_runtime.procurement_inventory_billing import (
    BillingAuditState,
    SQLiteBillingLeakageStore,
)
from jason_runtime.procurement_teams_flow import SQLiteProcurementSubmissionStore


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


class Bindings:
    def find_active_by_email(self, *, email_address):
        if email_address.casefold() == "tech@teamaot.com":
            return SimpleNamespace(
                jason_identity_id="person-tech",
                microsoft_object_id="aad-tech",
                microsoft_tenant_id="tenant-aot",
                status="active",
            )
        if email_address.casefold() == "lori@teamaot.com":
            return SimpleNamespace(
                jason_identity_id="person-lori",
                microsoft_object_id="aad-lori",
                microsoft_tenant_id="tenant-aot",
                status="active",
            )
        return None

    def find_active_by_jason_identity(self, *, jason_identity_id):
        if jason_identity_id == "person-tech":
            return self.find_active_by_email(email_address="tech@teamaot.com")
        return None


class Notifications:
    def __init__(self):
        self.bindings = Bindings()
        self.tech = []
        self.lori_messages = []

    def technician(self, **kwargs):
        self.tech.append(kwargs)
        return "msg-tech"

    def lori(self, *, text):
        self.lori_messages.append(text)
        return "msg-lori"


class Reads:
    def __init__(self, *, charge=None, billing_item=None, invoice=None):
        self.charge = charge
        self.billing_item = billing_item
        self.invoice = invoice
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.charge.search":
            return {"data": {"items": [] if self.charge is None else [self.charge]}}
        if capability == "service.billing.item.search":
            return {
                "data": {
                    "items": [] if self.billing_item is None else [self.billing_item]
                }
            }
        if capability == "service.invoice.read":
            return {"data": {"item": self.invoice}} if self.invoice else {"data": {}}
        if capability == "service.ticket.read":
            return {"data": {"item": {"id": 123, "assignedResourceID": 77}}}
        if capability == "service.resource.read":
            return {"data": {"item": {"id": 77, "email": "tech@teamaot.com"}}}
        raise AssertionError(capability)


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": {"jasonVerification": {"resourceId": 999}}}


def _submission_store(tmp_path: Path) -> SQLiteProcurementSubmissionStore:
    store = SQLiteProcurementSubmissionStore(tmp_path / "proc.sqlite3")
    payload = {
        "submission_id": "proc-1",
        "status": "received_pending_disposition",
        "digest": "digest-1",
        "requester_principal_id": "person-requester",
        "quantity": 2,
        "customer_quantity": 1,
        "aot_stock_quantity": 1,
        "received_quantity": 2,
        "released_quantity": 0,
        "release_state": "received_pending_disposition",
        "billing_treatment": "charge_ticket",
        "billing_disposition": "pending_receipt",
        "ticket_id": 123,
        "ticket_number": "T20261002.0001",
        "ticket_company_id": 42,
        "retail_price": "199.00",
        "product": {"name": "Dock", "cost": "120.00"},
        "result": {"product_id": 456},
    }
    store.put_new("proc-1", payload)
    return store


def test_missing_charge_notifies_assigned_technician_once_and_escalates_once(tmp_path):
    submissions = _submission_store(tmp_path)
    cases = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    notifications = Notifications()
    maintenance = HardwareBillingAuditMaintenance(
        submissions=submissions,
        cases=cases,
        reads=Reads(),
        notifications=notifications,
        actions=Actions(),
        now=lambda: NOW,
    )

    first = maintenance.run_once(now=NOW)
    assert first["technician_pending"] == 1
    assert first["technician_notified"] == 1
    assert len(notifications.tech) == 1
    case = cases.get("submission:proc-1:ticket:123:product:456")
    assert case["technician_identity_id"] == "person-tech"
    assert case["disposition_due_date"] == "2026-10-06"

    second = maintenance.run_once(now=NOW)
    assert second["technician_notified"] == 0
    assert len(notifications.tech) == 1

    tuesday = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)
    escalated = maintenance.run_once(now=tuesday)
    assert escalated["lori_escalated"] == 1
    assert len(notifications.lori_messages) == 1

    maintenance.run_once(now=tuesday)
    assert len(notifications.lori_messages) == 1


def test_existing_unbilled_charge_is_separate_and_authorizes_release_gate(tmp_path):
    submissions = _submission_store(tmp_path)
    cases = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    charge = {
        "id": 800,
        "ticketID": 123,
        "productID": 456,
        "unitQuantity": 1,
        "unitPrice": 199,
        "isBilled": False,
    }
    maintenance = HardwareBillingAuditMaintenance(
        submissions=submissions,
        cases=cases,
        reads=Reads(charge=charge),
        notifications=Notifications(),
        actions=Actions(),
    )
    summary = maintenance.run_once(now=NOW)
    assert summary["unbilled"] == 1
    updated = submissions.get("proc-1")
    assert updated["billing_disposition"] == "existing_unbilled_charge"
    assert updated["release_state"] == "ready_for_release"
    case = cases.get("submission:proc-1:ticket:123:product:456")
    assert case["state"] == BillingAuditState.EXISTING_UNBILLED_CHARGE.value


def test_exact_invoice_line_reconciles_and_validates_invoice_company(tmp_path):
    submissions = _submission_store(tmp_path)
    cases = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    charge = {
        "id": 800,
        "ticketID": 123,
        "productID": 456,
        "unitQuantity": 1,
        "unitPrice": 199,
        "isBilled": True,
    }
    line = {
        "id": 801,
        "ticketChargeID": 800,
        "invoiceID": 900,
        "quantity": 1,
        "rate": 199,
    }
    invoice = {
        "id": 900,
        "companyID": 42,
        "invoiceNumber": "INV-900",
        "invoiceDateTime": "2026-10-02T13:00:00Z",
        "status": 1,
    }
    maintenance = HardwareBillingAuditMaintenance(
        submissions=submissions,
        cases=cases,
        reads=Reads(charge=charge, billing_item=line, invoice=invoice),
        notifications=Notifications(),
        actions=Actions(),
    )
    summary = maintenance.run_once(now=NOW)
    assert summary["reconciled"] == 1
    updated = submissions.get("proc-1")
    assert updated["billing_disposition"] == "charge_created"
    assert updated["release_state"] == "ready_for_release"

    invoice["companyID"] = 99
    summary = maintenance.run_once(now=NOW)
    assert summary["invoice_exception"] == 1


def test_charge_needed_disposition_creates_exact_ticket_charge_once_per_observed_state(tmp_path):
    submissions = _submission_store(tmp_path)
    cases = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    actions = Actions()
    maintenance = HardwareBillingAuditMaintenance(
        submissions=submissions,
        cases=cases,
        reads=Reads(),
        notifications=Notifications(),
        actions=actions,
    )
    maintenance.run_once(now=NOW)
    key = "submission:proc-1:ticket:123:product:456"
    cases.set_technician_disposition(
        key,
        disposition="charge_needed",
        at=NOW,
        technician_identity_id="person-tech",
    )
    summary = maintenance.run_once(now=NOW)
    assert summary["charge_created"] == 1
    assert len(actions.calls) == 1
    payload = actions.calls[0]["payload"]
    assert payload["ticketID"] == 123
    assert payload["productID"] == 456
    assert payload["unitQuantity"] == 1
    assert payload["unitPrice"] == 199.0
    assert submissions.get("proc-1")["billing_disposition"] == "charge_created"
