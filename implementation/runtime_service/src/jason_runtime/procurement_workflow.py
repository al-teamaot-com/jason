from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable


class ProcurementWorkflowError(ValueError):
    pass


class ProcurementState(StrEnum):
    IDENTIFIED = "identified"
    CORRELATING = "correlating"
    VENDOR_REQUIRED = "vendor_required"
    VENDOR_REVIEW = "vendor_review"
    ALLOCATION_REQUIRED = "allocation_required"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    ORDERED = "ordered"
    CONFIRMED = "confirmed"
    WAITING_DELIVERY = "waiting_delivery"
    PARTIALLY_SHIPPED = "partially_shipped"
    SHIPPED = "shipped"
    DELIVERED_PENDING_RECEIPT = "delivered_pending_receipt"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    BILLING_PENDING = "billing_pending"
    RECONCILED = "reconciled"
    COMPLETE = "complete"
    IDENTIFICATION_BLOCKED = "identification_blocked"
    DUPLICATE_REVIEW = "duplicate_review"
    BACKORDERED = "backordered"
    EXCEPTION_REVIEW = "exception_review"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class ProcurementItemClass(StrEnum):
    IT = "it"
    COPY_PRINT = "copy_print"
    OTHER = "other"


class BillingTreatment(StrEnum):
    CHARGE_TICKET = "charge_ticket"
    NO_CHARGE_CONTRACT = "no_charge_contract"
    NO_CHARGE_WARRANTY = "no_charge_warranty"
    NO_CHARGE_INTERNAL = "no_charge_internal"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class TicketCandidate:
    ticket_number: str
    title: str
    evidence: tuple[str, ...]

    @property
    def display(self) -> str:
        number = self.ticket_number.strip()
        title = self.title.strip()
        if not number or not title:
            raise ProcurementWorkflowError(
                "ticket candidate requires both ticket number and title"
            )
        return f"{number} — {title}"


@dataclass(frozen=True, slots=True)
class VendorFieldCheck:
    field: str
    source_value: str | None
    autotask_value: str | None
    status: str

    def validate(self) -> None:
        field = self.field.strip()
        status = self.status.strip().casefold()
        if not field:
            raise ProcurementWorkflowError("vendor verification field is required")
        if status not in {"match", "source_missing", "autotask_missing", "mismatch"}:
            raise ProcurementWorkflowError("unsupported vendor verification status")
        if status == "match":
            if not (self.source_value or "").strip() or not (self.autotask_value or "").strip():
                raise ProcurementWorkflowError(
                    "matching vendor fields require both source and Autotask values"
                )
        if status == "mismatch":
            if not (self.source_value or "").strip() or not (self.autotask_value or "").strip():
                raise ProcurementWorkflowError(
                    "vendor mismatch requires both source and Autotask values"
                )


@dataclass(frozen=True, slots=True)
class VendorResolution:
    vendor_name: str
    autotask_vendor_id: int
    match_evidence: tuple[str, ...] = ()
    field_checks: tuple[VendorFieldCheck, ...] = ()

    def validate(self) -> None:
        if not self.vendor_name.strip():
            raise ProcurementWorkflowError("vendor name is required")
        if self.autotask_vendor_id < 1:
            raise ProcurementWorkflowError(
                "exact Autotask vendor company id is required before procurement"
            )
        for check in self.field_checks:
            check.validate()
        mismatches = tuple(
            check.field
            for check in self.field_checks
            if check.status.strip().casefold() == "mismatch"
        )
        if mismatches:
            raise ProcurementWorkflowError(
                "vendor master-data mismatch requires review: " + ", ".join(mismatches)
            )

    @property
    def fields_confirmed(self) -> tuple[str, ...]:
        return tuple(
            check.field
            for check in self.field_checks
            if check.status.strip().casefold() == "match"
        )

    @property
    def fields_missing_in_autotask(self) -> tuple[str, ...]:
        return tuple(
            check.field
            for check in self.field_checks
            if check.status.strip().casefold() == "autotask_missing"
        )


@dataclass(frozen=True, slots=True)
class ProductSource:
    source_type: str
    source_reference: str
    captured_at: datetime

    def validate(self) -> None:
        source_type = self.source_type.strip().casefold()
        if source_type not in {"vendor_document", "website_url", "autotask_catalog"}:
            raise ProcurementWorkflowError("unsupported procurement source type")
        if not self.source_reference.strip():
            raise ProcurementWorkflowError("procurement source reference is required")
        if self.captured_at.tzinfo is None:
            raise ProcurementWorkflowError("source capture timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LineAllocation:
    destination_type: str
    quantity: int
    customer_name: str | None = None
    ticket: TicketCandidate | None = None
    bill_to_ticket: bool = False

    def validate(self) -> None:
        if self.quantity < 1:
            raise ProcurementWorkflowError("allocation quantity must be positive")
        destination = self.destination_type.strip().casefold()
        if destination not in {"customer", "aot_inventory", "other"}:
            raise ProcurementWorkflowError("unsupported allocation destination")
        if destination == "aot_inventory" and self.ticket is not None:
            raise ProcurementWorkflowError(
                "AOT inventory allocation cannot carry a customer ticket"
            )
        if self.bill_to_ticket:
            if destination != "customer":
                raise ProcurementWorkflowError(
                    "only customer allocation can be billed to a ticket"
                )
            if self.ticket is None:
                raise ProcurementWorkflowError(
                    "bill-to-ticket allocation requires an exact ticket"
                )


@dataclass(frozen=True, slots=True)
class ProcurementLine:
    description: str
    ordered_quantity: int
    unit_cost: Decimal
    allocations: tuple[LineAllocation, ...]

    def validate(self) -> None:
        if not self.description.strip():
            raise ProcurementWorkflowError("line description is required")
        if self.ordered_quantity < 1:
            raise ProcurementWorkflowError("ordered quantity must be positive")
        if self.unit_cost < 0:
            raise ProcurementWorkflowError("unit cost cannot be negative")
        for allocation in self.allocations:
            allocation.validate()
        allocated = sum(allocation.quantity for allocation in self.allocations)
        if allocated != self.ordered_quantity:
            raise ProcurementWorkflowError(
                f"allocation mismatch: ordered={self.ordered_quantity}, allocated={allocated}"
            )

    @property
    def billable_quantity(self) -> int:
        self.validate()
        return sum(
            allocation.quantity
            for allocation in self.allocations
            if allocation.bill_to_ticket
        )

    @property
    def inventory_quantity(self) -> int:
        self.validate()
        return sum(
            allocation.quantity
            for allocation in self.allocations
            if allocation.destination_type.strip().casefold() == "aot_inventory"
        )


@dataclass(frozen=True, slots=True)
class SubmittedProcurementLine:
    line: ProcurementLine
    item_class: ProcurementItemClass
    billing_treatment: BillingTreatment
    retail_unit_price: Decimal | None
    at_part_number: str | None = None
    source: ProductSource | None = None

    def validate(self) -> None:
        self.line.validate()
        if self.retail_unit_price is not None and self.retail_unit_price < 0:
            raise ProcurementWorkflowError("retail unit price cannot be negative")
        if self.source is not None:
            self.source.validate()

        customer_allocations = tuple(
            allocation
            for allocation in self.line.allocations
            if allocation.destination_type.strip().casefold() == "customer"
        )

        if self.item_class is ProcurementItemClass.IT:
            if (
                self.billing_treatment is not BillingTreatment.CHARGE_TICKET
                and customer_allocations
            ):
                raise ProcurementWorkflowError(
                    "customer-bound IT items must use charge_ticket billing treatment"
                )
            for allocation in customer_allocations:
                if allocation.ticket is None or not allocation.bill_to_ticket:
                    raise ProcurementWorkflowError(
                        "customer-bound IT items require an exact billable ticket"
                    )

        if self.item_class is not ProcurementItemClass.COPY_PRINT:
            if self.billing_treatment in {
                BillingTreatment.NO_CHARGE_CONTRACT,
                BillingTreatment.NO_CHARGE_WARRANTY,
            }:
                raise ProcurementWorkflowError(
                    "contract/warranty no-charge treatments are reserved for copy/print"
                )

        if self.billing_treatment is BillingTreatment.CHARGE_TICKET:
            if not customer_allocations:
                raise ProcurementWorkflowError(
                    "charge_ticket billing treatment requires a customer allocation"
                )
            if self.retail_unit_price is None:
                raise ProcurementWorkflowError(
                    "charge_ticket billing treatment requires an approved retail price"
                )

    @property
    def extended_cost(self) -> Decimal:
        self.validate()
        return self.line.unit_cost * self.line.ordered_quantity


@dataclass(frozen=True, slots=True)
class ProcurementSubmission:
    requester_name: str
    requester_contact_id: int
    requester_company_id: int
    spending_limit: Decimal
    vendor: VendorResolution
    lines: tuple[SubmittedProcurementLine, ...]
    freight: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    submitted_at: datetime | None = None

    def validate(self) -> None:
        if not self.requester_name.strip():
            raise ProcurementWorkflowError("requester name is required")
        if self.requester_contact_id < 1:
            raise ProcurementWorkflowError("requester Autotask contact id is required")
        if self.requester_company_id != 0:
            raise ProcurementWorkflowError(
                "delegated AOT spending authority must come from a companyID=0 contact"
            )
        if self.spending_limit < 0:
            raise ProcurementWorkflowError("spending limit cannot be negative")
        self.vendor.validate()
        if not self.lines:
            raise ProcurementWorkflowError(
                "procurement submission requires at least one line"
            )
        for line in self.lines:
            line.validate()
        for label, value in (
            ("freight", self.freight),
            ("tax", self.tax),
            ("fees", self.fees),
        ):
            if value < 0:
                raise ProcurementWorkflowError(f"{label} cannot be negative")
        if self.submitted_at is not None and self.submitted_at.tzinfo is None:
            raise ProcurementWorkflowError("submitted_at must be timezone-aware")

    @property
    def subtotal(self) -> Decimal:
        self.validate()
        return sum((line.extended_cost for line in self.lines), Decimal("0"))

    @property
    def total_commitment(self) -> Decimal:
        self.validate()
        return self.subtotal + self.freight + self.tax + self.fees

    @property
    def requires_owner_approval(self) -> bool:
        self.validate()
        return self.total_commitment > self.spending_limit

    @property
    def canonical_digest(self) -> str:
        self.validate()
        payload = {
            "requester_name": self.requester_name.strip(),
            "requester_contact_id": self.requester_contact_id,
            "requester_company_id": self.requester_company_id,
            "spending_limit": str(self.spending_limit),
            "vendor": {
                "name": self.vendor.vendor_name.strip(),
                "autotask_vendor_id": self.vendor.autotask_vendor_id,
                "verified_fields": [
                    {
                        "field": check.field.strip(),
                        "source_value": check.source_value,
                        "autotask_value": check.autotask_value,
                        "status": check.status.strip().casefold(),
                    }
                    for check in self.vendor.field_checks
                ],
            },
            "lines": [
                {
                    "description": submitted.line.description.strip(),
                    "ordered_quantity": submitted.line.ordered_quantity,
                    "unit_cost": str(submitted.line.unit_cost),
                    "item_class": submitted.item_class.value,
                    "billing_treatment": submitted.billing_treatment.value,
                    "retail_unit_price": (
                        str(submitted.retail_unit_price)
                        if submitted.retail_unit_price is not None
                        else None
                    ),
                    "at_part_number": (
                        submitted.at_part_number.strip()
                        if submitted.at_part_number
                        else None
                    ),
                    "source": (
                        {
                            "type": submitted.source.source_type.strip(),
                            "reference": submitted.source.source_reference.strip(),
                            "captured_at": submitted.source.captured_at
                            .astimezone(timezone.utc)
                            .isoformat(),
                        }
                        if submitted.source is not None
                        else None
                    ),
                    "allocations": [
                        {
                            "destination_type": allocation.destination_type
                            .strip()
                            .casefold(),
                            "quantity": allocation.quantity,
                            "customer_name": allocation.customer_name,
                            "ticket": (
                                allocation.ticket.display
                                if allocation.ticket is not None
                                else None
                            ),
                            "bill_to_ticket": allocation.bill_to_ticket,
                        }
                        for allocation in submitted.line.allocations
                    ],
                }
                for submitted in self.lines
            ],
            "freight": str(self.freight),
            "tax": str(self.tax),
            "fees": str(self.fees),
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


def ticket_confirmation_prompt(candidate: TicketCandidate) -> str:
    evidence = "; ".join(item.strip() for item in candidate.evidence if item.strip())
    suffix = f" Match evidence: {evidence}." if evidence else ""
    return (
        f"This appears to be for {candidate.display}. "
        "Should I associate this purchase with that ticket?"
        + suffix
    )


def ticket_candidate_choices(
    candidates: Iterable[TicketCandidate],
) -> tuple[str, ...]:
    choices = tuple(candidate.display for candidate in candidates)
    return choices + ("No Ticket — AOT Inventory",)


def approval_summary(
    *,
    vendor: str,
    customer: str | None,
    line: ProcurementLine,
) -> dict[str, object]:
    line.validate()
    allocations: list[dict[str, object]] = []
    for allocation in line.allocations:
        allocations.append(
            {
                "destination_type": allocation.destination_type,
                "quantity": allocation.quantity,
                "customer_name": allocation.customer_name,
                "ticket": allocation.ticket.display if allocation.ticket else None,
                "bill_to_ticket": allocation.bill_to_ticket,
            }
        )
    return {
        "vendor": vendor.strip(),
        "customer": customer.strip() if customer else None,
        "description": line.description.strip(),
        "ordered_quantity": line.ordered_quantity,
        "unit_cost": str(line.unit_cost),
        "allocations": allocations,
        "billable_quantity": line.billable_quantity,
        "aot_inventory_quantity": line.inventory_quantity,
        "approval_required": True,
        "billing_inferred": False,
    }
