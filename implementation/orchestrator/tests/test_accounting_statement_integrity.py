from datetime import date
from decimal import Decimal
import pytest
from orchestrator.accounting_reconciliation import ReconciliationLine
from orchestrator.accounting_statement_integrity import validate_statement


def entry(ident, value, account="pnc", source="statement"):
    return ReconciliationLine(source, account, ident, date(2026, 4, 3), Decimal(value))


def test_valid_statement_totals_and_count():
    result = validate_statement(account="pnc", opening=Decimal("100.00"), closing=Decimal("120.00"),
                                entries=[entry("1", "50.00"), entry("2", "-30.00")], expected_count=2)
    assert result.valid and result.inflows == Decimal("50.00") and result.outflows == Decimal("30.00")


def test_mismatched_balance_fails_without_guessing():
    assert not validate_statement(account="pnc", opening=Decimal("100"), closing=Decimal("99"),
                                  entries=[entry("1", "50")]).valid


def test_wrong_count_fails():
    assert not validate_statement(account="pnc", opening=Decimal("0"), closing=Decimal("50"),
                                  entries=[entry("1", "50")], expected_count=2).valid


@pytest.mark.parametrize("entries", [
    [entry("a", "1"), entry("a", "2")],
    [entry("a", "1", account="other")],
    [entry("a", "1", source="ledger")],
])
def test_invalid_statement_rows_fail_closed(entries):
    with pytest.raises(ValueError):
        validate_statement(account="pnc", opening=Decimal("0"), closing=Decimal("1"), entries=entries)


def test_invalid_balance_precision_rejected():
    with pytest.raises(ValueError):
        validate_statement(account="pnc", opening=Decimal("0.001"), closing=Decimal("1"), entries=[])
