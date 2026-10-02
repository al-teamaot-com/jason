from datetime import datetime, timezone
from decimal import Decimal

import pytest

from jason_runtime.procurement_workflow import (
    BillingTreatment,
    LineAllocation,
    ProcurementItemClass,
    ProcurementLine,
    ProcurementSubmission,
    ProcurementWorkflowError,
    ProductSource,
    SubmittedProcurementLine,
    TicketCandidate,
    VendorFieldCheck,
    VendorResolution,
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


def _verified_vendor() -> VendorResolution:
    return VendorResolution(
        vendor_name="Staples",
        autotask_vendor_id=1234,
        match_evidence=("website domain staples.com", "vendor name matched"),
        field_checks=(
            VendorFieldCheck("website", "https://www.staples.com", "https://www.staples.com", "match"),
            VendorFieldCheck("phone", "1-800-333-3330", "1-800-333-3330", "match"),
            VendorFieldCheck("address", "500 Staples Dr", None, "autotask_missing"),
        ),
    )


def _it_line(cost: str = "900.00") -> SubmittedProcurementLine:
    return SubmittedProcurementLine(
        line=ProcurementLine(
            description="Lenovo ThinkPad",
            ordered_quantity=1,
            unit_cost=Decimal(cost),
            allocations=(
                LineAllocation(
                    destination_type="customer",
                    quantity=1,
                    customer_name="XYZ Company",
                    ticket=_ticket(),
                    bill_to_ticket=True,
                ),
            ),
        ),
        item_class=ProcurementItemClass.IT,
        billing_treatment=BillingTreatment.CHARGE_TICKET,
        retail_unit_price=Decimal("1199.00"),
        at_part_number="LAP-ThinkPad 10012026",
        source=ProductSource(
            source_type="website_url",
            source_reference="https://www.staples.com/example-laptop",
            captured_at=datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc),
        ),
    )


def test_ticket_prompt_always_includes_number_and_title() -> None:
    prompt = ticket_confirmation_prompt(_ticket())
    assert "T20260920.0123 — Replace Accounting Workstation" in prompt
    assert "Match evidence:" in prompt


def test_candidate_choices_use_number_title_and_inventory_option() -> None:
    other = TicketCandidate(
        ticket_number="T20260920.0999",
        title="New Hire Setup",
        evidence=(),
    )
    assert ticket_candidate_choices((_ticket(), other)) == (
        "T20260920.0123 — Replace Accounting Workstation",
        "T20260920.0999 — New Hire Setup",
        "No Ticket — AOT Inventory",
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
    with pytest.raises(ProcurementWorkflowError, match="cannot carry a customer ticket"):
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


def test_vendor_requires_exact_autotask_vendor_company_id() -> None:
    with pytest.raises(ProcurementWorkflowError, match="vendor company id"):
        VendorResolution("Staples", 0).validate()


def test_vendor_mismatch_fails_closed() -> None:
    vendor = VendorResolution(
        vendor_name="Staples",
        autotask_vendor_id=1234,
        field_checks=(
            VendorFieldCheck(
                "address",
                "500 Staples Dr",
                "Old Address",
                "mismatch",
            ),
        ),
    )
    with pytest.raises(ProcurementWorkflowError, match="vendor master-data mismatch"):
        vendor.validate()


def test_vendor_can_continue_when_autotask_is_missing_a_source_field() -> None:
    vendor = _verified_vendor()
    vendor.validate()
    assert vendor.fields_confirmed == ("website", "phone")
    assert vendor.fields_missing_in_autotask == ("address",)


def test_aot_spending_authority_must_use_company_zero_contact() -> None:
    submission = ProcurementSubmission(
        requester_name="Adam Navrat",
        requester_contact_id=30684918,
        requester_company_id=1156,
        spending_limit=Decimal("1375.42"),
        vendor=_verified_vendor(),
        lines=(_it_line(),),
    )
    with pytest.raises(ProcurementWorkflowError, match="companyID=0"):
        submission.validate()


@pytest.mark.parametrize(
    ("udf_limit", "commitment", "requires_approval"),
    (
        ("0.00", "0.01", True),
        ("250.00", "250.00", False),
        ("250.00", "250.01", True),
        ("1732.45", "1732.45", False),
        ("1732.45", "1732.46", True),
    ),
)
def test_spend_authority_uses_current_autotask_udf_value(
    udf_limit: str,
    commitment: str,
    requires_approval: bool,
) -> None:
    total = Decimal(commitment)
    submission = ProcurementSubmission(
        requester_name="Adam Navrat",
        requester_contact_id=30684918,
        requester_company_id=0,
        spending_limit=Decimal(udf_limit),
        vendor=_verified_vendor(),
        lines=(_it_line(str(total)),),
    )
    assert submission.total_commitment == total
    assert submission.requires_owner_approval is requires_approval


def test_customer_bound_it_must_be_billed_to_exact_ticket() -> None:
    bad = SubmittedProcurementLine(
        line=ProcurementLine(
            description="Laptop",
            ordered_quantity=1,
            unit_cost=Decimal("900"),
            allocations=(
                LineAllocation(
                    destination_type="customer",
                    quantity=1,
                    customer_name="XYZ Company",
                    ticket=_ticket(),
                    bill_to_ticket=False,
                ),
            ),
        ),
        item_class=ProcurementItemClass.IT,
        billing_treatment=BillingTreatment.CHARGE_TICKET,
        retail_unit_price=Decimal("1199"),
    )
    with pytest.raises(ProcurementWorkflowError, match="exact billable ticket"):
        bad.validate()


def test_copy_print_supports_contract_no_charge_reason() -> None:
    line = SubmittedProcurementLine(
        line=ProcurementLine(
            description="Black toner",
            ordered_quantity=1,
            unit_cost=Decimal("65"),
            allocations=(
                LineAllocation(
                    destination_type="customer",
                    quantity=1,
                    customer_name="XYZ Company",
                    ticket=_ticket(),
                    bill_to_ticket=False,
                ),
            ),
        ),
        item_class=ProcurementItemClass.COPY_PRINT,
        billing_treatment=BillingTreatment.NO_CHARGE_CONTRACT,
        retail_unit_price=None,
    )
    line.validate()


def test_digest_changes_when_material_selection_changes() -> None:
    base = ProcurementSubmission(
        requester_name="Adam Navrat",
        requester_contact_id=30684918,
        requester_company_id=0,
        spending_limit=Decimal("1375.42"),
        vendor=_verified_vendor(),
        lines=(_it_line("900.00"),),
    )
    changed = ProcurementSubmission(
        requester_name="Adam Navrat",
        requester_contact_id=30684918,
        requester_company_id=0,
        spending_limit=Decimal("1375.42"),
        vendor=_verified_vendor(),
        lines=(_it_line("901.00"),),
    )
    assert base.canonical_digest != changed.canonical_digest


def test_product_source_supports_permanent_procurement_source_hierarchy() -> None:
    source = ProductSource(
        source_type="vendor_api",
        source_reference="api:vendor/item/123",
        captured_at=datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc),
        acquisition_method="vendor_api",
        confidence="vendor_api",
        capture_sha256="d" * 64,
    )
    source.validate()

    structured = ProductSource(
        source_type="vendor_csv",
        source_reference="csv:feed.csv#row=3",
        captured_at=datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc),
        acquisition_method="structured_file",
        confidence="structured_file",
    )
    structured.validate()


def test_product_source_rejects_unknown_acquisition_method() -> None:
    source = ProductSource(
        source_type="website_url",
        source_reference="https://vendor.example/item",
        captured_at=datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc),
        acquisition_method="vendor_magic",
        confidence="manual",
    )
    with pytest.raises(ProcurementWorkflowError, match="acquisition method"):
        source.validate()
