from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


class ProcurementControlError(ValueError):
    pass


class ReleaseState(StrEnum):
    ORDERED = "ordered"
    RECEIVED_PENDING_DISPOSITION = "received_pending_disposition"
    READY_FOR_RELEASE = "ready_for_release"
    RELEASED = "released"
    BLOCKED = "blocked"


class BillingAuditState(StrEnum):
    MISSING_CHARGE = "missing_charge"
    TECHNICIAN_DISPOSITION_PENDING = "technician_disposition_pending"
    EXISTING_UNBILLED_CHARGE = "existing_unbilled_charge"
    BILLING_EXCEPTION = "billing_exception"
    INVOICE_RECONCILIATION_EXCEPTION = "invoice_reconciliation_exception"
    RECONCILED = "reconciled"
    ESCALATED = "escalated"


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    ordered_quantity: int
    customer_quantity: int
    aot_stock_quantity: int
    ticket_id: int | None = None
    ticket_number: str | None = None

    def validate(self) -> None:
        if self.ordered_quantity < 1:
            raise ProcurementControlError("ordered quantity must be positive")
        if self.customer_quantity < 0 or self.aot_stock_quantity < 0:
            raise ProcurementControlError("allocation quantities cannot be negative")
        if self.customer_quantity + self.aot_stock_quantity != self.ordered_quantity:
            raise ProcurementControlError(
                "allocation mismatch: ordered quantity must equal customer + AOT stock"
            )
        if self.customer_quantity and (
            not self.ticket_id or not str(self.ticket_number or "").strip()
        ):
            raise ProcurementControlError(
                "customer allocation requires one exact Autotask ticket"
            )


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    received_quantity: int
    release_quantity: int
    customer_quantity: int
    ticket_id: int | None
    billing_disposition: str | None

    def validate(self) -> None:
        if self.release_quantity < 1:
            raise ProcurementControlError("release quantity must be positive")
        if self.received_quantity < self.release_quantity:
            raise ProcurementControlError("stock cannot release before receiving")
        if self.customer_quantity:
            if not self.ticket_id:
                raise ProcurementControlError("customer release requires exact ticket")
            allowed = {
                "charge_created",
                "existing_unbilled_charge",
                "no_charge_contract",
                "no_charge_warranty",
                "no_charge_internal",
            }
            if str(self.billing_disposition or "") not in allowed:
                raise ProcurementControlError(
                    "customer stock release requires explicit billing disposition"
                )


def add_business_days(start: date, days: int) -> date:
    if days < 0:
        raise ProcurementControlError("business-day interval cannot be negative")
    current = start
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def evidence_digest(evidence: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(dict(evidence), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(slots=True)
class SQLiteBillingLeakageStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hardware_billing_audit (
                    case_key TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    ticket_id INTEGER NOT NULL,
                    ticket_number TEXT NOT NULL,
                    product_id INTEGER,
                    expected_quantity TEXT NOT NULL,
                    expected_unit_price TEXT,
                    charge_id INTEGER,
                    invoice_id INTEGER,
                    billing_item_id INTEGER,
                    evidence_digest TEXT NOT NULL,
                    first_detected_at TEXT NOT NULL,
                    disposition_due_date TEXT,
                    technician_disposition TEXT,
                    technician_disposition_at TEXT,
                    last_notified_state TEXT,
                    last_notified_digest TEXT,
                    last_notified_at TEXT,
                    escalated_at TEXT,
                    technician_identity_id TEXT,
                    procurement_submission_id TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(hardware_billing_audit)"
                ).fetchall()
            }
            if "technician_identity_id" not in columns:
                connection.execute(
                    "ALTER TABLE hardware_billing_audit ADD COLUMN technician_identity_id TEXT"
                )
            if "procurement_submission_id" not in columns:
                connection.execute(
                    "ALTER TABLE hardware_billing_audit ADD COLUMN procurement_submission_id TEXT"
                )

    def get(self, case_key: str) -> dict[str, Any] | None:
        with sqlite3.connect(str(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM hardware_billing_audit WHERE case_key=?", (case_key,)
            ).fetchone()
        return None if row is None else dict(row)

    def upsert_observation(
        self,
        *,
        case_key: str,
        state: BillingAuditState,
        ticket_id: int,
        ticket_number: str,
        product_id: int | None,
        expected_quantity: Decimal,
        expected_unit_price: Decimal | None,
        charge_id: int | None,
        invoice_id: int | None,
        billing_item_id: int | None,
        evidence: Mapping[str, Any],
        observed_at: datetime,
        technician_identity_id: str | None = None,
        procurement_submission_id: str | None = None,
    ) -> dict[str, Any]:
        digest = evidence_digest(evidence)
        now = observed_at.astimezone(timezone.utc).isoformat()
        existing = self.get(case_key)
        first = existing["first_detected_at"] if existing else now
        due = (
            existing.get("disposition_due_date")
            if existing
            else add_business_days(observed_at.date(), 2).isoformat()
        )
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                """
                INSERT INTO hardware_billing_audit(
                    case_key,state,ticket_id,ticket_number,product_id,
                    expected_quantity,expected_unit_price,charge_id,invoice_id,
                    billing_item_id,evidence_digest,first_detected_at,
                    disposition_due_date,technician_identity_id,
                    procurement_submission_id,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(case_key) DO UPDATE SET
                    state=excluded.state,ticket_id=excluded.ticket_id,
                    ticket_number=excluded.ticket_number,product_id=excluded.product_id,
                    expected_quantity=excluded.expected_quantity,
                    expected_unit_price=excluded.expected_unit_price,
                    charge_id=excluded.charge_id,invoice_id=excluded.invoice_id,
                    billing_item_id=excluded.billing_item_id,
                    evidence_digest=excluded.evidence_digest,
                    technician_identity_id=COALESCE(
                        excluded.technician_identity_id,
                        hardware_billing_audit.technician_identity_id
                    ),
                    procurement_submission_id=COALESCE(
                        excluded.procurement_submission_id,
                        hardware_billing_audit.procurement_submission_id
                    ),
                    updated_at=excluded.updated_at
                """,
                (
                    case_key, state.value, ticket_id, ticket_number, product_id,
                    str(expected_quantity),
                    None if expected_unit_price is None else str(expected_unit_price),
                    charge_id, invoice_id, billing_item_id, digest, first, due,
                    technician_identity_id, procurement_submission_id, now,
                ),
            )
        return self.get(case_key) or {}

    @staticmethod
    def notification_needed(case: Mapping[str, Any]) -> bool:
        return not (
            case.get("last_notified_state") == case.get("state")
            and case.get("last_notified_digest") == case.get("evidence_digest")
        )

    def mark_notified(self, case_key: str, *, notified_at: datetime) -> None:
        case = self.get(case_key)
        if not case:
            raise ProcurementControlError("billing audit case not found")
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                """
                UPDATE hardware_billing_audit SET
                    last_notified_state=?,last_notified_digest=?,
                    last_notified_at=?,updated_at=? WHERE case_key=?
                """,
                (
                    case["state"], case["evidence_digest"],
                    notified_at.astimezone(timezone.utc).isoformat(),
                    notified_at.astimezone(timezone.utc).isoformat(), case_key,
                ),
            )

    def set_technician_disposition(
        self,
        case_key: str,
        *,
        disposition: str,
        at: datetime,
        technician_identity_id: str | None = None,
    ) -> None:
        allowed = {"charge_needed", "not_billable", "already_handled"}
        if disposition not in allowed:
            raise ProcurementControlError("unsupported technician disposition")
        case = self.get(case_key)
        if not case:
            raise ProcurementControlError("billing audit case not found")
        expected = str(case.get("technician_identity_id") or "").strip()
        observed = str(technician_identity_id or "").strip()
        if expected and observed != expected:
            raise PermissionError("billing disposition belongs to another technician")
        with sqlite3.connect(str(self.path)) as connection:
            cursor = connection.execute(
                """
                UPDATE hardware_billing_audit SET
                    technician_disposition=?,technician_disposition_at=?,updated_at=?
                WHERE case_key=?
                """,
                (
                    disposition, at.astimezone(timezone.utc).isoformat(),
                    at.astimezone(timezone.utc).isoformat(), case_key,
                ),
            )
            if cursor.rowcount != 1:
                raise ProcurementControlError("billing audit case not found")

    def due_for_lori_escalation(self, *, today: date) -> tuple[dict[str, Any], ...]:
        with sqlite3.connect(str(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM hardware_billing_audit
                WHERE state IN ('missing_charge','technician_disposition_pending')
                  AND technician_disposition IS NULL
                  AND escalated_at IS NULL
                  AND disposition_due_date <= ?
                ORDER BY disposition_due_date, case_key
                """,
                (today.isoformat(),),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def mark_escalated(self, case_key: str, *, at: datetime) -> None:
        stamp = at.astimezone(timezone.utc).isoformat()
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                """
                UPDATE hardware_billing_audit
                SET state='escalated',escalated_at=?,updated_at=?
                WHERE case_key=?
                """,
                (stamp, stamp, case_key),
            )


@dataclass(frozen=True, slots=True)
class BillingExpectation:
    ticket_id: int
    ticket_number: str
    product_id: int
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class BillingReconciliation:
    state: BillingAuditState
    charge_id: int | None = None
    invoice_id: int | None = None
    billing_item_id: int | None = None
    reason: str = ""


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def reconcile_hardware_billing(
    expectation: BillingExpectation,
    *,
    ticket_charges: tuple[Mapping[str, Any], ...],
    billing_items: tuple[Mapping[str, Any], ...],
) -> BillingReconciliation:
    """Deterministically reconcile one expected hardware charge to posted billing.

    Missing ticket charge, existing-but-unbilled charge, posted-but-not-invoiced
    charge, invoice line mismatch, and exact reconciliation remain distinct states.
    """
    exact_charges = [
        charge
        for charge in ticket_charges
        if int(charge.get("ticketID") or 0) == expectation.ticket_id
        and int(charge.get("productID") or 0) == expectation.product_id
    ]
    if not exact_charges:
        return BillingReconciliation(
            BillingAuditState.TECHNICIAN_DISPOSITION_PENDING,
            reason="expected customer hardware has no matching ticket charge",
        )
    if len(exact_charges) != 1:
        return BillingReconciliation(
            BillingAuditState.BILLING_EXCEPTION,
            reason="multiple matching ticket charges require review",
        )

    charge = exact_charges[0]
    charge_id = int(charge["id"])
    if Decimal(str(charge.get("unitQuantity") or "0")) != expectation.quantity:
        return BillingReconciliation(
            BillingAuditState.BILLING_EXCEPTION,
            charge_id=charge_id,
            reason="ticket charge quantity does not match customer allocation",
        )
    if _money(charge.get("unitPrice")) != _money(expectation.unit_price):
        return BillingReconciliation(
            BillingAuditState.BILLING_EXCEPTION,
            charge_id=charge_id,
            reason="ticket charge sell price does not match approved retail price",
        )

    is_billed = bool(charge.get("isBilled"))
    if not is_billed:
        return BillingReconciliation(
            BillingAuditState.EXISTING_UNBILLED_CHARGE,
            charge_id=charge_id,
            reason="matching ticket charge exists but is not yet billed",
        )

    exact_items = [
        item
        for item in billing_items
        if int(item.get("ticketChargeID") or 0) == charge_id
    ]
    if not exact_items:
        return BillingReconciliation(
            BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
            charge_id=charge_id,
            reason="ticket charge is billed but no posted billing item references it",
        )
    if len(exact_items) != 1:
        return BillingReconciliation(
            BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
            charge_id=charge_id,
            reason="multiple posted billing items reference one ticket charge",
        )

    item = exact_items[0]
    invoice_id = item.get("invoiceID")
    if invoice_id in (None, 0, "0", ""):
        return BillingReconciliation(
            BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
            charge_id=charge_id,
            billing_item_id=int(item["id"]),
            reason="posted billing item has not been associated with a customer invoice",
        )
    if Decimal(str(item.get("quantity") or "0")) != expectation.quantity:
        return BillingReconciliation(
            BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
            charge_id=charge_id,
            invoice_id=int(invoice_id),
            billing_item_id=int(item["id"]),
            reason="invoice billing-item quantity does not match customer allocation",
        )
    if _money(item.get("rate")) != _money(expectation.unit_price):
        return BillingReconciliation(
            BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
            charge_id=charge_id,
            invoice_id=int(invoice_id),
            billing_item_id=int(item["id"]),
            reason="invoice billing-item rate does not match approved retail price",
        )
    return BillingReconciliation(
        BillingAuditState.RECONCILED,
        charge_id=charge_id,
        invoice_id=int(invoice_id),
        billing_item_id=int(item["id"]),
        reason="exact ticket charge and customer invoice billing item verified",
    )


def technician_disposition_card(case: Mapping[str, Any]) -> dict[str, Any]:
    """Concise Teams card used only when a human billing disposition is needed."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "Hardware billing check",
                "weight": "Bolder",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Ticket", "value": str(case["ticket_number"])},
                    {
                        "title": "Expected",
                        "value": str(case["expected_quantity"]) + " item(s)",
                    },
                    {
                        "title": "State",
                        "value": str(case["state"]).replace("_", " "),
                    },
                ],
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Charge needed",
                "data": {
                    "kind": "hardware.billing.disposition",
                    "case_key": str(case["case_key"]),
                    "disposition": "charge_needed",
                },
            },
            {
                "type": "Action.Submit",
                "title": "Not billable",
                "data": {
                    "kind": "hardware.billing.disposition",
                    "case_key": str(case["case_key"]),
                    "disposition": "not_billable",
                },
            },
            {
                "type": "Action.Submit",
                "title": "Already handled",
                "data": {
                    "kind": "hardware.billing.disposition",
                    "case_key": str(case["case_key"]),
                    "disposition": "already_handled",
                },
            },
        ],
    }


def lori_escalation_text(cases: tuple[Mapping[str, Any], ...]) -> str:
    if not cases:
        raise ProcurementControlError("no billing cases are due for escalation")
    tickets = ", ".join(str(case["ticket_number"]) for case in cases[:10])
    suffix = "" if len(cases) <= 10 else f" (+{len(cases) - 10} more)"
    return (
        "Hardware billing follow-up: "
        + str(len(cases))
        + " case(s) have had no technician disposition for two business days: "
        + tickets
        + suffix
        + "."
    )


@dataclass
class HardwareBillingDispositionFlow:
    bindings: Any
    store: SQLiteBillingLeakageStore
    procurement_submissions: Any | None = None

    def handle(
        self,
        *,
        case_key: str,
        disposition: str,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        channel_response_id: str,
        decided_at: datetime,
    ) -> Mapping[str, Any]:
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError("technician Microsoft identity is not bound")
        case = self.store.get(case_key)
        if case is None:
            raise LookupError("hardware billing case not found")
        self.store.set_technician_disposition(
            case_key,
            disposition=disposition,
            at=decided_at,
            technician_identity_id=str(binding.jason_identity_id),
        )
        submission_id = str(case.get("procurement_submission_id") or "").strip()
        reply = "Billing disposition recorded."
        if submission_id and self.procurement_submissions is not None:
            if disposition == "not_billable":
                submission = self.procurement_submissions.get(submission_id)
                if submission is not None:
                    treatment = str(submission.get("billing_treatment") or "")
                    no_charge = (
                        treatment
                        if treatment in {
                            "no_charge_contract",
                            "no_charge_warranty",
                            "no_charge_internal",
                        }
                        else "no_charge_internal"
                    )
                    self.procurement_submissions.record_billing_disposition(
                        submission_id, disposition=no_charge
                    )
                    reply = "Not-billable disposition recorded; release gate updated."
            elif disposition == "already_handled":
                current = self.procurement_submissions.get(submission_id)
                if current is not None and current.get("billing_disposition"):
                    reply = "Already-handled disposition recorded; existing billing state preserved."
            elif disposition == "charge_needed":
                reply = "Charge-needed disposition recorded for governed billing follow-up."
        return {
            "status": "completed",
            "case_key": case_key,
            "reply": {"text": reply},
        }
