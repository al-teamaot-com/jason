from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable


class ProcurementWorkflowError(ValueError):
    pass


class ProcurementState(StrEnum):
    IDENTIFIED = "identified"
    CORRELATING = "correlating"
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


def ticket_confirmation_prompt(candidate: TicketCandidate) -> str:
    evidence = "; ".join(item.strip() for item in candidate.evidence if item.strip())
    suffix = f" Match evidence: {evidence}." if evidence else ""
    return (
        f"This appears to be for {candidate.display}. "
        "Should I associate this purchase with that ticket?"
        + suffix
    )


def ticket_candidate_choices(candidates: Iterable[TicketCandidate]) -> tuple[str, ...]:
    return tuple(candidate.display for candidate in candidates)


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
