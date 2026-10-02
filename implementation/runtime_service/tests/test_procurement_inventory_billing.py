from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from jason_runtime.procurement_inventory_billing import (
    AllocationPlan,
    BillingAuditState,
    ProcurementControlError,
    ReleaseGate,
    SQLiteBillingLeakageStore,
    add_business_days,
)


def test_mixed_customer_and_aot_allocation_requires_exact_math_and_ticket():
    AllocationPlan(
        ordered_quantity=4,
        customer_quantity=3,
        aot_stock_quantity=1,
        ticket_id=123,
        ticket_number="T20261002.0001",
    ).validate()

    with pytest.raises(ProcurementControlError, match="allocation mismatch"):
        AllocationPlan(4, 2, 1, 123, "T20261002.0001").validate()

    with pytest.raises(ProcurementControlError, match="exact Autotask ticket"):
        AllocationPlan(2, 1, 1).validate()


def test_receiving_and_release_are_separate_and_billing_disposition_is_required():
    with pytest.raises(ProcurementControlError, match="before receiving"):
        ReleaseGate(0, 1, 1, 123, "charge_created").validate()

    with pytest.raises(ProcurementControlError, match="billing disposition"):
        ReleaseGate(1, 1, 1, 123, None).validate()

    ReleaseGate(1, 1, 1, 123, "existing_unbilled_charge").validate()
    ReleaseGate(1, 1, 0, None, None).validate()


def test_two_business_day_escalation_skips_weekend():
    assert add_business_days(date(2026, 10, 2), 2) == date(2026, 10, 6)


def test_billing_audit_persists_state_suppresses_duplicates_and_separates_unbilled(tmp_path):
    store = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    observed = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
    case = store.upsert_observation(
        case_key="ticket:123:product:456",
        state=BillingAuditState.MISSING_CHARGE,
        ticket_id=123,
        ticket_number="T20261002.0001",
        product_id=456,
        expected_quantity=Decimal("1"),
        expected_unit_price=Decimal("999.00"),
        charge_id=None,
        invoice_id=None,
        billing_item_id=None,
        evidence={"ticket": 123, "product": 456, "qty": 1},
        observed_at=observed,
    )
    assert store.notification_needed(case)
    assert case["disposition_due_date"] == "2026-10-06"

    store.mark_notified(case["case_key"], notified_at=observed)
    assert not store.notification_needed(store.get(case["case_key"]))

    unbilled = store.upsert_observation(
        case_key=case["case_key"],
        state=BillingAuditState.EXISTING_UNBILLED_CHARGE,
        ticket_id=123,
        ticket_number="T20261002.0001",
        product_id=456,
        expected_quantity=Decimal("1"),
        expected_unit_price=Decimal("999.00"),
        charge_id=789,
        invoice_id=None,
        billing_item_id=None,
        evidence={"ticket": 123, "charge": 789, "is_billed": False},
        observed_at=observed,
    )
    assert unbilled["state"] == "existing_unbilled_charge"
    assert store.notification_needed(unbilled)


def test_unanswered_missing_charge_escalates_to_lori_after_two_business_days(tmp_path):
    store = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    store.upsert_observation(
        case_key="case-1",
        state=BillingAuditState.TECHNICIAN_DISPOSITION_PENDING,
        ticket_id=123,
        ticket_number="T20261002.0001",
        product_id=456,
        expected_quantity=Decimal("1"),
        expected_unit_price=Decimal("999.00"),
        charge_id=None,
        invoice_id=None,
        billing_item_id=None,
        evidence={"missing": True},
        observed_at=datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc),
    )
    assert store.due_for_lori_escalation(today=date(2026, 10, 5)) == ()
    due = store.due_for_lori_escalation(today=date(2026, 10, 6))
    assert len(due) == 1
    assert due[0]["case_key"] == "case-1"


def test_billing_reconciliation_distinguishes_missing_unbilled_invoice_exception_and_exact():
    from jason_runtime.procurement_inventory_billing import (
        BillingExpectation,
        reconcile_hardware_billing,
    )

    expected = BillingExpectation(
        ticket_id=123,
        ticket_number="T20261002.0001",
        product_id=456,
        quantity=Decimal("2"),
        unit_price=Decimal("199.00"),
    )
    missing = reconcile_hardware_billing(
        expected, ticket_charges=(), billing_items=()
    )
    assert missing.state is BillingAuditState.TECHNICIAN_DISPOSITION_PENDING

    charge = {
        "id": 789,
        "ticketID": 123,
        "productID": 456,
        "unitQuantity": 2,
        "unitPrice": 199,
        "isBilled": False,
    }
    unbilled = reconcile_hardware_billing(
        expected, ticket_charges=(charge,), billing_items=()
    )
    assert unbilled.state is BillingAuditState.EXISTING_UNBILLED_CHARGE

    billed = {**charge, "isBilled": True}
    no_line = reconcile_hardware_billing(
        expected, ticket_charges=(billed,), billing_items=()
    )
    assert no_line.state is BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION

    line = {
        "id": 900,
        "ticketChargeID": 789,
        "invoiceID": 901,
        "quantity": 2,
        "rate": 199,
    }
    exact = reconcile_hardware_billing(
        expected, ticket_charges=(billed,), billing_items=(line,)
    )
    assert exact.state is BillingAuditState.RECONCILED
    assert exact.invoice_id == 901
    assert exact.billing_item_id == 900


def test_technician_card_is_concise_and_has_three_dispositions():
    from jason_runtime.procurement_inventory_billing import technician_disposition_card

    card = technician_disposition_card(
        {
            "case_key": "case-1",
            "ticket_number": "T20261002.0001",
            "expected_quantity": "1",
            "state": "technician_disposition_pending",
        }
    )
    assert len(card["body"]) == 2
    assert [action["title"] for action in card["actions"]] == [
        "Charge needed",
        "Not billable",
        "Already handled",
    ]


def test_billing_disposition_is_identity_bound(tmp_path):
    from types import SimpleNamespace
    from jason_runtime.procurement_inventory_billing import HardwareBillingDispositionFlow

    store = SQLiteBillingLeakageStore(tmp_path / "audit.sqlite3")
    observed = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
    store.upsert_observation(
        case_key="case-bound",
        state=BillingAuditState.TECHNICIAN_DISPOSITION_PENDING,
        ticket_id=123,
        ticket_number="T20261002.0001",
        product_id=456,
        expected_quantity=Decimal("1"),
        expected_unit_price=Decimal("199"),
        charge_id=None,
        invoice_id=None,
        billing_item_id=None,
        evidence={"missing": True},
        observed_at=observed,
        technician_identity_id="person-tech",
    )

    class Bindings:
        def __init__(self, who):
            self.who = who

        def find(self, **kwargs):
            return SimpleNamespace(status="active", jason_identity_id=self.who)

    wrong = HardwareBillingDispositionFlow(
        bindings=Bindings("person-other"), store=store
    )
    with pytest.raises(PermissionError, match="another technician"):
        wrong.handle(
            case_key="case-bound",
            disposition="not_billable",
            microsoft_tenant_id="tenant",
            microsoft_object_id="other",
            conversation_id="conv",
            channel_response_id="msg",
            decided_at=observed,
        )

    right = HardwareBillingDispositionFlow(
        bindings=Bindings("person-tech"), store=store
    )
    result = right.handle(
        case_key="case-bound",
        disposition="not_billable",
        microsoft_tenant_id="tenant",
        microsoft_object_id="tech",
        conversation_id="conv",
        channel_response_id="msg",
        decided_at=observed,
    )
    assert result["status"] == "completed"
    assert store.get("case-bound")["technician_disposition"] == "not_billable"
