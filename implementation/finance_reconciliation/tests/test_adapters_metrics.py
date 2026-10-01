from decimal import Decimal

import pytest

from finance_reconciliation.adapters import PdfDocumentFacts
from finance_reconciliation.contracts import DocumentKind
from finance_reconciliation.metrics import ReconciliationRunMetrics


def test_pdf_preflight_facts_reject_zero_pages():
    with pytest.raises(ValueError, match="page_count"):
        PdfDocumentFacts(
            document_sha256="a" * 64,
            page_count=0,
            document_kind=DocumentKind.NATIVE_TEXT,
            has_native_text=True,
            has_images=False,
        )


def test_pilot_metrics_measure_automation_and_human_time_saved():
    metrics = ReconciliationRunMetrics(
        workflow_id="recon-2026-09",
        account_id="operating-001",
        pdf_pages=8,
        transactions=100,
        auto_matched=92,
        ambiguous=5,
        unmatched=3,
        human_input_requests=4,
        baseline_human_minutes=Decimal("180"),
        actual_human_review_minutes=Decimal("25"),
        processing_seconds=Decimal("47.2"),
        ocr_pages=1,
    )

    assert metrics.auto_match_rate == Decimal("92.00")
    assert metrics.human_minutes_saved == Decimal("155")


def test_metrics_require_complete_transaction_accounting():
    with pytest.raises(ValueError, match="outcome counts"):
        ReconciliationRunMetrics(
            workflow_id="recon-2026-09",
            account_id="operating-001",
            pdf_pages=8,
            transactions=100,
            auto_matched=92,
            ambiguous=5,
            unmatched=2,
            human_input_requests=4,
            baseline_human_minutes=Decimal("180"),
            actual_human_review_minutes=Decimal("25"),
            processing_seconds=Decimal("47.2"),
        )
