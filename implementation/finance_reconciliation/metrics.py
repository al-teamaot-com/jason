"""Pilot metrics for operational value and future hardware justification."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


_PERCENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ReconciliationRunMetrics:
    workflow_id: str
    account_id: str
    pdf_pages: int
    transactions: int
    auto_matched: int
    ambiguous: int
    unmatched: int
    human_input_requests: int
    baseline_human_minutes: Decimal
    actual_human_review_minutes: Decimal
    processing_seconds: Decimal
    ocr_pages: int = 0

    def __post_init__(self) -> None:
        if not self.workflow_id.strip() or not self.account_id.strip():
            raise ValueError("workflow_id and account_id are required")
        counts = (
            self.pdf_pages,
            self.transactions,
            self.auto_matched,
            self.ambiguous,
            self.unmatched,
            self.human_input_requests,
            self.ocr_pages,
        )
        if any(value < 0 for value in counts):
            raise ValueError("metric counts cannot be negative")
        if self.auto_matched + self.ambiguous + self.unmatched != self.transactions:
            raise ValueError("transaction outcome counts must equal transactions")
        if self.baseline_human_minutes < 0 or self.actual_human_review_minutes < 0:
            raise ValueError("human time metrics cannot be negative")
        if self.processing_seconds < 0:
            raise ValueError("processing_seconds cannot be negative")
        if self.ocr_pages > self.pdf_pages:
            raise ValueError("ocr_pages cannot exceed pdf_pages")

    @property
    def auto_match_rate(self) -> Decimal:
        if self.transactions == 0:
            return Decimal("0.00")
        return (
            Decimal(self.auto_matched) / Decimal(self.transactions) * Decimal("100")
        ).quantize(_PERCENT, rounding=ROUND_HALF_UP)

    @property
    def human_minutes_saved(self) -> Decimal:
        saved = self.baseline_human_minutes - self.actual_human_review_minutes
        return max(saved, Decimal("0"))
