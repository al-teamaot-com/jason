from datetime import date, timedelta
from decimal import Decimal

import pytest

from orchestrator.accounting_reconciliation import ReconciliationLine, reconcile


def line(source, id, amount="12.50", day=10, ref="ref-1", account="checking"):
    return ReconciliationLine(source, account, id, date(2026, 10, day), Decimal(amount), ref)


def test_unique_exact_match_is_read_only_deterministic():
    decision = reconcile([line("statement", "s1")], [line("ledger", "l1")])
    assert len(decision) == 1
    assert decision[0].status == "matched"
    assert decision[0].ledger_id == "l1"


def test_different_account_cannot_match():
    result = reconcile([line("statement", "s1")], [line("ledger", "l1", account="credit")])
    assert {x.status for x in result} == {"missing_ledger_entry", "missing_statement_entry"}


def test_same_amount_multiple_ledger_entries_stays_ambiguous():
    result = reconcile([line("statement", "s1")], [
        line("ledger", "l1"), line("ledger", "l2")
    ])
    assert result[0].status == "ambiguous_match"


def test_unique_reference_disambiguates():
    result = reconcile([line("statement", "s1", ref="check-1")], [
        line("ledger", "l1", ref="check-1"),
        line("ledger", "l2", ref="check-2"),
    ])
    assert result[0].status == "matched"
    assert result[0].ledger_id == "l1"


def test_duplicate_statement_claims_cannot_create_second_match():
    result = reconcile([line("statement", "s1"), line("statement", "s2")], [
        line("ledger", "l1"),
    ])
    assert sum(x.status == "matched" for x in result) == 0


def test_signed_amount_never_crosses_direction():
    result = reconcile([line("statement", "s1", amount="-12.50")], [
        line("ledger", "l1", amount="12.50")
    ])
    assert result[0].status == "missing_ledger_entry"


def test_date_tolerance_is_bounded():
    result = reconcile([line("statement", "s1", day=10)], [
        line("ledger", "l1", day=15)
    ])
    assert result[0].status == "missing_ledger_entry"
    with pytest.raises(ValueError):
        reconcile([], [], date_tolerance_days=100)


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        reconcile([line("statement", "s1"), line("statement", "s1")], [])


def test_floating_point_and_fractional_cent_rejected():
    with pytest.raises(ValueError):
        ReconciliationLine("statement", "checking", "x", date.today(), 12.5)
    with pytest.raises(ValueError):
        ReconciliationLine("statement", "checking", "x", date.today(), Decimal("1.001"))


def test_conflicting_explicit_reference_never_matches():
    result = reconcile([line("statement", "s1", ref="check-1")], [
        line("ledger", "l1", ref="check-2")
    ])
    assert result[0].status == "missing_ledger_entry"
