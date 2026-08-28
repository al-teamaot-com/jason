from datetime import datetime, timezone
from decimal import Decimal

import pytest

from .adapters import from_openai_response

from .contracts import (
    AttemptOutcome,
    CostUsage,
    TokenUsage,
    UsageAdjustment,
    UsageContext,
    UsageEntry,
    UsageSource,
)
from .ledger import DuplicateAttemptError, InMemoryUsageLedger, SQLiteUsageLedger, ScopeError


def context(attempt_id: str, *, organization_id: str = "aot") -> UsageContext:
    return UsageContext(
        workflow_id="wf-1",
        request_id="req-1",
        attempt_id=attempt_id,
        organization_id=organization_id,
        client_id="client-1",
        capability="triage.ticket.assess",
        ticket_id="ticket-1",
    )


def entry(attempt_id: str, total: int = 15) -> UsageEntry:
    return UsageEntry(
        entry_id=f"entry-{attempt_id}",
        context=context(attempt_id),
        provider="openai",
        model="example-model",
        outcome=AttemptOutcome.COMPLETED,
        usage_source=UsageSource.PROVIDER_REPORTED,
        tokens=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=total),
        cost=CostUsage(provider_reported_cost=Decimal("0.01")),
    )


def test_records_every_attempt_including_fallbacks() -> None:
    ledger = InMemoryUsageLedger()
    ledger.append(entry("attempt-1"))
    ledger.append(entry("attempt-2"))

    totals = ledger.totals(organization_id="aot", workflow_id="wf-1")

    assert totals.attempts == 2
    assert totals.total_tokens == 30
    assert totals.provider_reported_cost == Decimal("0.02")


def test_identical_retry_is_idempotent() -> None:
    ledger = InMemoryUsageLedger()
    record = entry("attempt-1")
    ledger.append(record)
    ledger.append(record)

    assert ledger.totals(organization_id="aot").attempts == 1


def test_conflicting_duplicate_attempt_is_rejected() -> None:
    ledger = InMemoryUsageLedger()
    ledger.append(entry("attempt-1"))

    with pytest.raises(DuplicateAttemptError):
        ledger.append(entry("attempt-1", total=20))


def test_organization_scope_is_required() -> None:
    ledger = InMemoryUsageLedger()

    with pytest.raises(ScopeError):
        ledger.list_entries(organization_id="")


def test_reconciliation_adjusts_totals_without_mutating_original() -> None:
    ledger = InMemoryUsageLedger()
    original = entry("attempt-1")
    ledger.append(original)
    ledger.append_adjustment(
        UsageAdjustment(
            adjustment_id="adjustment-1",
            original_entry_id=original.entry_id,
            organization_id="aot",
            reason="provider billing export reconciliation",
            created_at=datetime.now(timezone.utc),
            replacement_tokens=TokenUsage(
                input_tokens=11,
                output_tokens=5,
                total_tokens=16,
            ),
            replacement_cost=CostUsage(provider_reported_cost=Decimal("0.012")),
            authoritative_reference="billing-export-2026-07-31",
        )
    )

    totals = ledger.totals(organization_id="aot")
    stored = ledger.list_entries(organization_id="aot")[0]

    assert totals.total_tokens == 16
    assert totals.provider_reported_cost == Decimal("0.012")
    assert stored.tokens.total_tokens == 15


def test_unknown_usage_attempt_is_visible() -> None:
    ledger = InMemoryUsageLedger()
    ledger.append(
        UsageEntry(
            entry_id="entry-timeout",
            context=context("attempt-timeout"),
            provider="openai",
            model="example-model",
            outcome=AttemptOutcome.TIMED_OUT,
            usage_source=UsageSource.UNKNOWN,
            tokens=TokenUsage(),
            confidence=0.0,
        )
    )

    totals = ledger.totals(organization_id="aot")

    assert totals.attempts == 1
    assert totals.unknown_usage_attempts == 1


def test_sqlite_ledger_survives_restart(tmp_path) -> None:
    path = tmp_path / "model-usage.sqlite3"
    ledger = SQLiteUsageLedger(path)
    ledger.append(entry("attempt-1"))
    ledger.close()

    reopened = SQLiteUsageLedger(path)
    totals = reopened.totals(organization_id="aot", workflow_id="wf-1")
    reopened.close()

    assert totals.attempts == 1
    assert totals.total_tokens == 15
    assert totals.provider_reported_cost == Decimal("0.01")
    assert path.stat().st_mode & 0o777 == 0o600


def test_sqlite_ledger_preserves_idempotency_and_adjustments(tmp_path) -> None:
    ledger = SQLiteUsageLedger(tmp_path / "model-usage.sqlite3")
    original = entry("attempt-1")
    ledger.append(original)
    ledger.append(original)
    ledger.append_adjustment(
        UsageAdjustment(
            adjustment_id="adjustment-1",
            original_entry_id=original.entry_id,
            organization_id="aot",
            reason="provider reconciliation",
            created_at=datetime.now(timezone.utc),
            replacement_tokens=TokenUsage(input_tokens=12, output_tokens=5, total_tokens=17),
            replacement_cost=CostUsage(provider_reported_cost=Decimal("0.015")),
        )
    )

    totals = ledger.totals(organization_id="aot")
    ledger.close()

    assert totals.attempts == 1
    assert totals.total_tokens == 17
    assert totals.provider_reported_cost == Decimal("0.015")


def test_openai_usage_calculates_uncached_cached_and_output_cost() -> None:
    recorded = from_openai_response(
        context=context("attempt-priced"),
        model="gpt-5.4-mini",
        response={
            "usage": {
                "input_tokens": 1_000_000,
                "input_tokens_details": {"cached_tokens": 200_000},
                "output_tokens": 100_000,
                "total_tokens": 1_100_000,
            }
        },
        input_cost_per_million_tokens=Decimal("0.75"),
        cached_input_cost_per_million_tokens=Decimal("0.075"),
        output_cost_per_million_tokens=Decimal("4.50"),
    )

    assert recorded.cost.calculated_cost == Decimal("1.065")
