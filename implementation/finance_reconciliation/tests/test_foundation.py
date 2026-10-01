from datetime import date
from decimal import Decimal

import pytest

from finance_reconciliation.account_registry import FinanceAccountRegistry
from finance_reconciliation.contracts import (
    AccountStatus,
    AccountType,
    BalanceEffect,
    DocumentKind,
    FinanceAccountConfig,
    LedgerEntry,
    MatchState,
    SourceLocation,
    StatementExtraction,
    StatementHeader,
    StatementTransaction,
)
from finance_reconciliation.human_input import (
    build_visual_ambiguity_request,
    reroute_human_input_request,
)
from finance_reconciliation.matching import match_statement_to_ledger
from finance_reconciliation.validation import validate_statement


HASH = "a" * 64


def account(account_id="operating-001", masked="****1234", status=AccountStatus.PILOT):
    return FinanceAccountConfig(
        account_id=account_id,
        display_name=f"Test {account_id}",
        institution="Example Bank",
        account_type=AccountType.BANK_CHECKING,
        masked_identifier=masked,
        parser_profile="example-bank-v1",
        statement_cadence="monthly",
        source_intake_location="sharepoint://finance/inbox",
        output_workbook="sharepoint://finance/reconciliation.xlsx",
        output_target="Operating!Transactions",
        reviewer="lori@example.invalid",
        status=status,
        date_tolerance_days=3,
    )


def transaction(tx_id, day, description, amount, effect, *, reference=None, page=1):
    return StatementTransaction(
        transaction_id=tx_id,
        posted_date=date(2026, 9, day),
        description=description,
        amount=Decimal(amount),
        effect=effect,
        reference=reference,
        source=SourceLocation(document_sha256=HASH, page_number=page),
    )


def extraction(transactions, *, closing="1150.00", declared_increase=None, declared_decrease=None):
    return StatementExtraction(
        account_id="operating-001",
        source_document_sha256=HASH,
        document_kind=DocumentKind.NATIVE_TEXT,
        header=StatementHeader(
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            opening_balance=Decimal("1000.00"),
            closing_balance=Decimal(closing),
            page_count=3,
            declared_increase_total=(
                Decimal(declared_increase) if declared_increase is not None else None
            ),
            declared_decrease_total=(
                Decimal(declared_decrease) if declared_decrease is not None else None
            ),
        ),
        transactions=tuple(transactions),
    )


def test_account_registry_adds_and_removes_accounts_by_configuration():
    first = account()
    second = FinanceAccountConfig(
        **{
            **first.__dict__,
            "account_id": "card-001",
            "display_name": "Test Card",
            "masked_identifier": "****9876",
            "account_type": AccountType.CREDIT_CARD,
            "status": AccountStatus.ACTIVE,
        }
    )
    registry = FinanceAccountRegistry.from_records([first, second])
    assert [item.account_id for item in registry.enabled_accounts()] == [
        "card-001",
        "operating-001",
    ]

    retired = account(status=AccountStatus.RETIRED)
    registry = FinanceAccountRegistry.from_records([retired, second])
    assert registry.resolve("operating-001") is None
    assert registry.resolve("card-001") is not None


def test_account_identifier_must_remain_masked():
    with pytest.raises(ValueError, match="at most four digits"):
        account(masked="123456789")


def test_statement_math_proves_valid_extraction():
    statement = extraction(
        [
            transaction("t1", 5, "Deposit", "200.00", BalanceEffect.INCREASE),
            transaction("t2", 8, "Vendor", "50.00", BalanceEffect.DECREASE),
        ],
        declared_increase="200.00",
        declared_decrease="50.00",
    )
    result = validate_statement(statement)
    assert result.valid is True
    assert result.calculated_closing_balance == Decimal("1150.00")
    assert result.closing_balance_difference == Decimal("0.00")


def test_statement_math_fails_closed_on_missing_or_bad_value():
    statement = extraction(
        [
            transaction("t1", 5, "Deposit", "200.00", BalanceEffect.INCREASE),
            transaction("t2", 8, "Vendor", "40.00", BalanceEffect.DECREASE),
        ]
    )
    result = validate_statement(statement)
    assert result.valid is False
    assert "closing_balance_mismatch:10.00" in result.reasons


def test_declared_totals_are_independent_validation_evidence():
    statement = extraction(
        [
            transaction("t1", 5, "Deposit", "200.00", BalanceEffect.INCREASE),
            transaction("t2", 8, "Vendor", "50.00", BalanceEffect.DECREASE),
        ],
        declared_increase="250.00",
        declared_decrease="50.00",
    )
    result = validate_statement(statement)
    assert result.valid is False
    assert "declared_increase_total_mismatch:-50.00" in result.reasons


def test_exact_reference_match_is_deterministic():
    statement = extraction(
        [transaction("t1", 5, "Vendor ABC", "50.00", BalanceEffect.DECREASE, reference="CHK-7")],
        closing="950.00",
    )
    ledger = [
        LedgerEntry(
            entry_id="l1",
            posted_date=date(2026, 9, 6),
            description="Vendor ABC",
            amount=Decimal("50.00"),
            effect=BalanceEffect.DECREASE,
            reference="CHK-7",
        )
    ]
    match = match_statement_to_ledger(statement, ledger, account())[0]
    assert match.state is MatchState.MATCHED
    assert match.ledger_entry_id == "l1"
    assert match.rule_id == "reference_amount_effect_date_window_v1"


def test_duplicate_candidates_remain_ambiguous():
    statement = extraction(
        [transaction("t1", 5, "Vendor ABC", "50.00", BalanceEffect.DECREASE)],
        closing="950.00",
    )
    ledger = [
        LedgerEntry(
            entry_id="l1",
            posted_date=date(2026, 9, 5),
            description="Vendor ABC",
            amount=Decimal("50.00"),
            effect=BalanceEffect.DECREASE,
        ),
        LedgerEntry(
            entry_id="l2",
            posted_date=date(2026, 9, 6),
            description="Vendor ABC",
            amount=Decimal("50.00"),
            effect=BalanceEffect.DECREASE,
        ),
    ]
    match = match_statement_to_ledger(statement, ledger, account())[0]
    assert match.state is MatchState.AMBIGUOUS
    assert match.ledger_entry_id is None
    assert match.candidate_ledger_entry_ids == ("l1", "l2")


def test_human_input_can_be_rerouted_without_losing_context():
    source = SourceLocation(
        document_sha256=HASH,
        page_number=2,
        bbox=(100.0, 200.0, 140.0, 230.0),
        text_excerpt="... ambiguous character ...",
    )
    request = build_visual_ambiguity_request(
        request_id="q-1",
        workflow_id="recon-2026-09",
        account_id="operating-001",
        recipient="Lori",
        question="Is the highlighted character a 1 or a 7?",
        reason="conflicting PDF extraction",
        source=source,
        evidence_context="September statement, transaction row 14",
        suggested_answers=("1", "7", "Neither"),
    )

    rerouted = reroute_human_input_request(
        request,
        new_request_id="q-2",
        new_recipient="Arnold",
        redirector_display_name="Lori",
    )

    assert rerouted.recipient == "Arnold"
    assert rerouted.parent_request_id == "q-1"
    assert rerouted.redirected_by == "Lori"
    assert rerouted.context_note == "Lori thinks you may know the answer to this."
    assert rerouted.question == request.question
    assert rerouted.source == request.source
