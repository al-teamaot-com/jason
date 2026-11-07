"""Read-only statement arithmetic preflight; never substitutes for ledger verification."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from orchestrator.accounting_reconciliation import ReconciliationLine


@dataclass(frozen=True, slots=True)
class StatementIntegrity:
    account: str
    opening: Decimal
    closing: Decimal
    computed_closing: Decimal
    inflows: Decimal
    outflows: Decimal
    transaction_count: int
    valid: bool


def validate_statement(
    *, account: str, opening: Decimal, closing: Decimal,
    entries: Sequence[ReconciliationLine], expected_count: int | None = None,
) -> StatementIntegrity:
    if not account or not isinstance(account, str):
        raise ValueError("Statement account required")
    if len(entries) > 20000:
        raise ValueError("Statement entry limit exceeded")
    for value in (opening, closing):
        if not isinstance(value, Decimal) or not value.is_finite() or value.as_tuple().exponent < -2:
            raise ValueError("Statement balances require finite cent-precision Decimal")
    if expected_count is not None and (type(expected_count) is not int or expected_count < 0):
        raise ValueError("Expected count must be a nonnegative integer")
    if any(row.source != "statement" or row.account != account for row in entries):
        raise ValueError("Mixed account or non-statement input")
    if len({row.entry_id for row in entries}) != len(entries):
        raise ValueError("Duplicate statement entry IDs")
    inflows = sum((row.signed_amount for row in entries if row.signed_amount > 0), Decimal("0"))
    outflows = -sum((row.signed_amount for row in entries if row.signed_amount < 0), Decimal("0"))
    computed = opening + inflows - outflows
    return StatementIntegrity(
        account, opening, closing, computed, inflows, outflows, len(entries),
        computed == closing and (expected_count is None or expected_count == len(entries)),
    )
