"""Deterministic statement extraction validation.

Financial acceptance is based on arithmetic proof and provenance checks, never
on model/OCR confidence alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .contracts import BalanceEffect, StatementExtraction


_CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class StatementValidationResult:
    valid: bool
    calculated_closing_balance: Decimal
    closing_balance_difference: Decimal
    calculated_increase_total: Decimal
    calculated_decrease_total: Decimal
    reasons: tuple[str, ...]


def validate_statement(extraction: StatementExtraction) -> StatementValidationResult:
    reasons: list[str] = []
    ids: set[str] = set()
    increase_total = Decimal("0")
    decrease_total = Decimal("0")

    for transaction in extraction.transactions:
        if transaction.transaction_id in ids:
            reasons.append(f"duplicate_transaction_id:{transaction.transaction_id}")
        ids.add(transaction.transaction_id)

        if transaction.source.document_sha256.lower() != extraction.source_document_sha256.lower():
            reasons.append(f"source_hash_mismatch:{transaction.transaction_id}")
        if transaction.source.page_number > extraction.header.page_count:
            reasons.append(f"source_page_out_of_range:{transaction.transaction_id}")

        if transaction.effect is BalanceEffect.INCREASE:
            increase_total += transaction.amount
        else:
            decrease_total += transaction.amount

    increase_total = _money(increase_total)
    decrease_total = _money(decrease_total)
    calculated_closing = _money(
        extraction.header.opening_balance + increase_total - decrease_total
    )
    difference = _money(calculated_closing - extraction.header.closing_balance)

    if difference != Decimal("0.00"):
        reasons.append(f"closing_balance_mismatch:{difference}")

    if extraction.header.declared_increase_total is not None:
        declared = _money(extraction.header.declared_increase_total)
        if increase_total != declared:
            reasons.append(
                f"declared_increase_total_mismatch:{_money(increase_total - declared)}"
            )

    if extraction.header.declared_decrease_total is not None:
        declared = _money(extraction.header.declared_decrease_total)
        if decrease_total != declared:
            reasons.append(
                f"declared_decrease_total_mismatch:{_money(decrease_total - declared)}"
            )

    return StatementValidationResult(
        valid=not reasons,
        calculated_closing_balance=calculated_closing,
        closing_balance_difference=difference,
        calculated_increase_total=increase_total,
        calculated_decrease_total=decrease_total,
        reasons=tuple(reasons),
    )
