"""Conservative deterministic one-to-one matching primitives.

Ambiguity fails closed. AI-generated likelihood is intentionally not an
authoritative matching rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Iterable

from .contracts import (
    FinanceAccountConfig,
    LedgerEntry,
    MatchState,
    StatementExtraction,
    StatementTransaction,
)


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[A-Z0-9]+", value.upper()))


def _within_days(left: date, right: date, tolerance: int) -> bool:
    return abs((left - right).days) <= tolerance


@dataclass(frozen=True, slots=True)
class ReconciliationMatch:
    statement_transaction_id: str
    state: MatchState
    rule_id: str | None
    ledger_entry_id: str | None
    candidate_ledger_entry_ids: tuple[str, ...] = ()


def _base_candidates(
    transaction: StatementTransaction,
    ledger_entries: Iterable[LedgerEntry],
    *,
    tolerance_days: int,
    used: set[str],
) -> list[LedgerEntry]:
    return [
        entry
        for entry in ledger_entries
        if entry.entry_id not in used
        and entry.effect is transaction.effect
        and entry.amount == transaction.amount
        and _within_days(entry.posted_date, transaction.posted_date, tolerance_days)
    ]


def match_statement_to_ledger(
    extraction: StatementExtraction,
    ledger_entries: Iterable[LedgerEntry],
    config: FinanceAccountConfig,
) -> tuple[ReconciliationMatch, ...]:
    if extraction.account_id != config.account_id:
        raise ValueError("statement account_id does not match account configuration")

    ledger = tuple(ledger_entries)
    used: set[str] = set()
    results: list[ReconciliationMatch] = []

    for transaction in sorted(
        extraction.transactions,
        key=lambda item: (item.posted_date, item.transaction_id),
    ):
        base = _base_candidates(
            transaction,
            ledger,
            tolerance_days=config.date_tolerance_days,
            used=used,
        )

        if transaction.reference and transaction.reference.strip():
            reference = transaction.reference.strip().casefold()
            exact_reference = [
                entry
                for entry in base
                if entry.reference and entry.reference.strip().casefold() == reference
            ]
            if len(exact_reference) == 1:
                entry = exact_reference[0]
                used.add(entry.entry_id)
                results.append(
                    ReconciliationMatch(
                        statement_transaction_id=transaction.transaction_id,
                        state=MatchState.MATCHED,
                        rule_id="reference_amount_effect_date_window_v1",
                        ledger_entry_id=entry.entry_id,
                        candidate_ledger_entry_ids=(entry.entry_id,),
                    )
                )
                continue
            if len(exact_reference) > 1:
                results.append(
                    ReconciliationMatch(
                        statement_transaction_id=transaction.transaction_id,
                        state=MatchState.AMBIGUOUS,
                        rule_id="reference_amount_effect_date_window_v1",
                        ledger_entry_id=None,
                        candidate_ledger_entry_ids=tuple(
                            sorted(entry.entry_id for entry in exact_reference)
                        ),
                    )
                )
                continue

        statement_name = _normalize_text(
            transaction.normalized_payee or transaction.description
        )
        exact_description = [
            entry for entry in base if _normalize_text(entry.description) == statement_name
        ]
        if len(exact_description) == 1:
            entry = exact_description[0]
            used.add(entry.entry_id)
            results.append(
                ReconciliationMatch(
                    statement_transaction_id=transaction.transaction_id,
                    state=MatchState.MATCHED,
                    rule_id="amount_effect_date_window_normalized_description_v1",
                    ledger_entry_id=entry.entry_id,
                    candidate_ledger_entry_ids=(entry.entry_id,),
                )
            )
        elif len(exact_description) > 1:
            results.append(
                ReconciliationMatch(
                    statement_transaction_id=transaction.transaction_id,
                    state=MatchState.AMBIGUOUS,
                    rule_id="amount_effect_date_window_normalized_description_v1",
                    ledger_entry_id=None,
                    candidate_ledger_entry_ids=tuple(
                        sorted(entry.entry_id for entry in exact_description)
                    ),
                )
            )
        else:
            results.append(
                ReconciliationMatch(
                    statement_transaction_id=transaction.transaction_id,
                    state=MatchState.UNMATCHED,
                    rule_id=None,
                    ledger_entry_id=None,
                    candidate_ledger_entry_ids=(),
                )
            )

    return tuple(results)
