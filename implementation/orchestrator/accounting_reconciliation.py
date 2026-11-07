"""Deterministic, read-only statement-to-ledger reconciliation foundation.

Inputs must be separately normalized and authorized by governed provider reads.
No payment, ledger, invoice, or bank-side mutation is possible from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Sequence


@dataclass(frozen=True)
class ReconciliationLine:
    source: str
    account: str
    entry_id: str
    posted_on: date
    signed_amount: Decimal
    reference: str = ""

    def __post_init__(self) -> None:
        if self.source not in {"statement", "ledger"}:
            raise ValueError("Source must be statement or ledger")
        if not self.account or not self.entry_id or not isinstance(self.posted_on, date):
            raise ValueError("Account, stable entry identity, and date are required")
        if isinstance(self.signed_amount, bool) or not isinstance(self.signed_amount, Decimal):
            raise ValueError("Amounts must be Decimal")
        if not self.signed_amount.is_finite() or self.signed_amount == 0:
            raise ValueError("Amount must be a finite nonzero signed decimal")
        if self.signed_amount.as_tuple().exponent < -2:
            raise ValueError("Statement amounts must have no more than two decimal places")


@dataclass(frozen=True)
class ReconciliationDecision:
    status: str
    statement_id: str
    ledger_id: str | None
    explanation: str


def reconcile(
    statement: Sequence[ReconciliationLine],
    ledger: Sequence[ReconciliationLine],
    *,
    date_tolerance_days: int = 3,
) -> tuple[ReconciliationDecision, ...]:
    """Match only uniquely supported one-to-one entries, never choose ambiguously."""
    if type(date_tolerance_days) is not int or not 0 <= date_tolerance_days <= 10:
        raise ValueError("Bounded date tolerance must be 0-10 days")
    rows = list(statement) + list(ledger)
    if len(rows) > 20000:
        raise ValueError("Reconciliation input exceeds bound")
    if any(row.source != "statement" for row in statement):
        raise ValueError("Statement source mismatch")
    if any(row.source != "ledger" for row in ledger):
        raise ValueError("Ledger source mismatch")
    keys = [(row.source, row.account, row.entry_id) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate source entry identity is not a safe reconciliation input")
    results: list[ReconciliationDecision] = []
    available = set(range(len(ledger)))
    for item in statement:
        candidates = [
            idx for idx in available
            if ledger[idx].account == item.account
            and ledger[idx].signed_amount == item.signed_amount
            and abs((ledger[idx].posted_on - item.posted_on).days) <= date_tolerance_days
            and (not item.reference.strip() or not ledger[idx].reference.strip() or item.reference.strip().casefold() == ledger[idx].reference.strip().casefold())
        ]
        ref = item.reference.strip().casefold()
        if ref:
            exact_ref = [idx for idx in candidates if ledger[idx].reference.strip().casefold() == ref]
            if exact_ref:
                candidates = exact_ref
        if len(candidates) == 1:
            idx = candidates[0]
            # Do not greedily consume an amount/date match if another statement
            # row could claim the same ledger entry.
            other_claimants = [
                other for other in statement
                if other is not item and other.account == ledger[idx].account
                and other.signed_amount == ledger[idx].signed_amount
                and abs((other.posted_on - ledger[idx].posted_on).days) <= date_tolerance_days
                and (
                    not ref
                    or not other.reference.strip()
                    or other.reference.strip().casefold() == ledger[idx].reference.strip().casefold()
                )
            ]
            if other_claimants:
                results.append(ReconciliationDecision("ambiguous_match", item.entry_id, None,
                                                      "Multiple statement entries could consume this ledger entry"))
            else:
                available.remove(idx)
                results.append(ReconciliationDecision("matched", item.entry_id,
                                                      ledger[idx].entry_id, "Unique account, amount, date and reference evidence"))
        elif candidates:
            results.append(ReconciliationDecision("ambiguous_match", item.entry_id, None,
                                                  "More than one ledger candidate remains"))
        else:
            results.append(ReconciliationDecision("missing_ledger_entry", item.entry_id, None,
                                                  "No matching ledger entry within approved tolerance"))
    for idx in sorted(available):
        results.append(ReconciliationDecision("missing_statement_entry", "",
                                              ledger[idx].entry_id,
                                              "Ledger entry has no uniquely matched statement row"))
    return tuple(results)
