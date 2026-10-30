from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from orchestrator.finance_reconciliation_reporting import (
    ExceptionItem, ReconciliationRun, RunStatus, render_run_summary,
)


def sample(**kwargs):
    data = dict(
        run_id="test-01", account_masked="Fulton ending 7313",
        period="April 2026", recipient_role="assigned-finance-reconciler",
        started_at=datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 10, 16, 12, 1, tzinfo=timezone.utc),
        status=RunStatus.COMPLETED_NO_EXCEPTIONS,
        examined=5, matched=5, exceptions=(),
        steps=("Read statement", "Compared bank and ledger records"),
        accounting_records_changed=False,
    )
    data.update(kwargs)
    return ReconciliationRun(**data)


def test_clean_report_no_approval_requested():
    s = render_run_summary(sample())
    assert "No action required." in s
    assert "Accounting records changed: No" in s
    assert "approval" not in s.lower()
    assert "Delivery status: Not established" in s


def test_solutrix_payment_not_falsely_reconciled_or_approved():
    issue = ExceptionItem("Solutrix #15904", Decimal("826.91"),
                          "Linked QuickBooks payment and funding account not yet verified",
                          "Jason", "Retrieve governed BillPayment proof", False)
    report = render_run_summary(sample(
        status=RunStatus.PARTIAL_REVIEW_REQUIRED,
        examined=1, matched=0, exceptions=(issue,),
        steps=("Reviewed invoice, receipt, bill and bank row",),
    ))
    assert "Partially verified" in report
    assert "No action required." in report
    assert "Outstanding / tracked exceptions:" in report
    assert "Linked QuickBooks payment" in report
    assert "reconciled" not in report.lower()


def test_unresolved_exception_has_explicit_human_action():
    issue = ExceptionItem("TX-004", Decimal("500.00"), "Two competing bank rows",
                          "Assigned reconciler", "Choose supported source record", True)
    report = render_run_summary(sample(
        status=RunStatus.COMPLETED_WITH_EXCEPTIONS,
        examined=3, matched=2, exceptions=(issue,),
    ))
    assert "Assigned reconciler: Choose supported source record" in report
    assert "No action required." not in report


def test_clean_run_cannot_hide_exception():
    issue = ExceptionItem("TX-004", Decimal("500.00"), "Unknown debit",
                          "Jason", "Investigate", False)
    with pytest.raises(ValueError, match="clean completion"):
        render_run_summary(sample(exceptions=(issue,)))


def test_invalid_counts_and_timestamps_fail_closed():
    with pytest.raises(ValueError, match="matched exceeds"):
        render_run_summary(sample(examined=1, matched=3))
    with pytest.raises(ValueError, match="timezone-aware"):
        render_run_summary(sample(ended_at=datetime(2026, 10, 16, 12, 1)))


def test_unauthorized_posting_not_inferred_from_presentation():
    with pytest.raises(ValueError, match="accounting change must"):
        render_run_summary(sample(accounting_records_changed=True))
