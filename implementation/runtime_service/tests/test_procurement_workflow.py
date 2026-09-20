from decimal import Decimal

import pytest

from jason_runtime.procurement_workflow import (
    LineAllocation,
    ProcurementLine,
    ProcurementWorkflowError,
    TicketCandidate,
    approval_summary,
    ticket_candidate_choices,
    ticket_confirmation_prompt,
)


def _ticket() -> TicketCandidate:
    return TicketCandidate(
        ticket_number="T20260920.0123",
        title="Replace Accounting Workstation",
        evidence=("customer matched", "ticket notes reference Dell dock"),
    )


def test_ticket_prompt_always_includes_number_and_title() -> None:
    prompt = ticket_confirmation_prompt(_ticket())
    assert "T20260920.0123 — Replace Accounting Workstation" in prompt
    assert "Match evidence:" in prompt


def test_candidate_choices_use_number_and_title() -> None:
    other = TicketCandidate(
        ticket_number="T20260920.0999",
        title="New Hire Setup",
        evidence=(),
    )
    assert ticket_candidate_choices((_ticket(), other)) == (
        "T20260920.0123 — Replace Accounting Workstation",
        "T20260920.0999 — New Hire Setup",
    )


def test_two_ordered_can_split_one_customer_one_inventory() -> None:
    line = ProcurementLine(
        description="Dell Dock",
        ordered_quantity=2,
        unit_cost=Decimal("185.00"),
        allocations=(
            LineAllocation(
                destination_type="customer",
                quantity=1,
                customer_name="XYZ Company",
                ticket=_ticket(),
                bill_to_ticket=True,
            ),
            LineAllocation(
                destination_type="aot_inventory",
                quantity=1,
                bill_to_ticket=False,
            ),
        ),
    )
    line.validate()
    assert line.billable_quantity == 1
    assert line.inventory_quantity == 1

    summary = approval_summary(
        vendor="Dell",
        customer="XYZ Company",
        line=line,
    )
    assert summary["ordered_quantity"] == 2
    assert summary["billable_quantity"] == 1
    assert summary["aot_inventory_quantity"] == 1
    assert summary["billing_inferred"] is False
    assert summary["approval_required"] is True
    assert summary["allocations"][0]["ticket"] == (
        "T20260920.0123 — Replace Accounting Workstation"
    )


def test_allocation_must_equal_ordered_quantity() -> None:
    line = ProcurementLine(
        description="Dell Dock",
        ordered_quantity=2,
        unit_cost=Decimal("185.00"),
        allocations=(
            LineAllocation(
                destination_type="customer",
                quantity=1,
                customer_name="XYZ Company",
                ticket=_ticket(),
                bill_to_ticket=True,
            ),
        ),
    )
    with pytest.raises(ProcurementWorkflowError, match="allocation mismatch"):
        line.validate()


def test_inventory_cannot_be_billed_to_ticket() -> None:
    allocation = LineAllocation(
        destination_type="aot_inventory",
        quantity=1,
        ticket=_ticket(),
        bill_to_ticket=True,
    )
    with pytest.raises(ProcurementWorkflowError, match="only customer allocation"):
        allocation.validate()


def test_bill_to_ticket_requires_exact_ticket() -> None:
    allocation = LineAllocation(
        destination_type="customer",
        quantity=1,
        customer_name="XYZ Company",
        bill_to_ticket=True,
    )
    with pytest.raises(ProcurementWorkflowError, match="requires an exact ticket"):
        allocation.validate()


def test_ticket_candidate_requires_number_and_title() -> None:
    bad = TicketCandidate(ticket_number="T20260920.0123", title="", evidence=())
    with pytest.raises(ProcurementWorkflowError, match="both ticket number and title"):
        _ = bad.display
