"""Reference append-only implementation of Jason's model usage ledger."""

from __future__ import annotations

from decimal import Decimal
from threading import RLock
from typing import Iterable

from .contracts import (
    CostUsage,
    UsageAdjustment,
    UsageEntry,
    UsageSource,
    UsageTotals,
)


class DuplicateAttemptError(ValueError):
    """Raised when the same attempt is submitted with different data."""


class ScopeError(PermissionError):
    """Raised when a caller requests data outside the required organization scope."""


class InMemoryUsageLedger:
    """Thread-safe reference store for development and contract testing.

    Production should use an append-only database or event stream with equivalent
    uniqueness and organization-scope guarantees.
    """

    def __init__(self) -> None:
        self._entries_by_id: dict[str, UsageEntry] = {}
        self._entry_id_by_attempt: dict[tuple[str, str], str] = {}
        self._adjustments_by_id: dict[str, UsageAdjustment] = {}
        self._lock = RLock()

    def append(self, entry: UsageEntry) -> None:
        entry.validate()
        attempt_key = (entry.context.organization_id, entry.context.attempt_id)

        with self._lock:
            existing_id = self._entry_id_by_attempt.get(attempt_key)
            if existing_id is not None:
                existing = self._entries_by_id[existing_id]
                if existing == entry:
                    return
                raise DuplicateAttemptError(
                    f"attempt {entry.context.attempt_id!r} already has a different ledger entry"
                )
            if entry.entry_id in self._entries_by_id:
                raise DuplicateAttemptError(f"entry ID {entry.entry_id!r} already exists")

            self._entries_by_id[entry.entry_id] = entry
            self._entry_id_by_attempt[attempt_key] = entry.entry_id

    def append_adjustment(self, adjustment: UsageAdjustment) -> None:
        if not adjustment.adjustment_id:
            raise ValueError("adjustment ID is required")
        if not adjustment.reason:
            raise ValueError("adjustment reason is required")

        with self._lock:
            original = self._entries_by_id.get(adjustment.original_entry_id)
            if original is None:
                raise KeyError("original usage entry does not exist")
            if original.context.organization_id != adjustment.organization_id:
                raise ScopeError("adjustment organization does not match original entry")
            if adjustment.adjustment_id in self._adjustments_by_id:
                if self._adjustments_by_id[adjustment.adjustment_id] == adjustment:
                    return
                raise DuplicateAttemptError("adjustment ID already exists with different data")
            if adjustment.replacement_tokens is not None:
                adjustment.replacement_tokens.validate()
            if adjustment.replacement_cost is not None:
                adjustment.replacement_cost.validate()
            self._adjustments_by_id[adjustment.adjustment_id] = adjustment

    def list_entries(
        self,
        *,
        organization_id: str,
        workflow_id: str | None = None,
        client_id: str | None = None,
        ticket_id: str | None = None,
    ) -> tuple[UsageEntry, ...]:
        if not organization_id:
            raise ScopeError("organization ID is required")

        with self._lock:
            entries = tuple(self._entries_by_id.values())

        return tuple(
            entry
            for entry in entries
            if entry.context.organization_id == organization_id
            and (workflow_id is None or entry.context.workflow_id == workflow_id)
            and (client_id is None or entry.context.client_id == client_id)
            and (ticket_id is None or entry.context.ticket_id == ticket_id)
        )

    def totals(
        self,
        *,
        organization_id: str,
        workflow_id: str | None = None,
        client_id: str | None = None,
        ticket_id: str | None = None,
    ) -> UsageTotals:
        entries = self.list_entries(
            organization_id=organization_id,
            workflow_id=workflow_id,
            client_id=client_id,
            ticket_id=ticket_id,
        )
        effective = [self._effective_values(entry) for entry in entries]

        return UsageTotals(
            attempts=len(entries),
            input_tokens=sum(tokens.input_tokens or 0 for tokens, _ in effective),
            cached_input_tokens=sum(tokens.cached_input_tokens or 0 for tokens, _ in effective),
            output_tokens=sum(tokens.output_tokens or 0 for tokens, _ in effective),
            reasoning_tokens=sum(tokens.reasoning_tokens or 0 for tokens, _ in effective),
            total_tokens=sum(tokens.total_tokens or 0 for tokens, _ in effective),
            provider_reported_cost=sum(
                (cost.provider_reported_cost or Decimal("0") for _, cost in effective),
                Decimal("0"),
            ),
            calculated_cost=sum(
                (cost.calculated_cost or Decimal("0") for _, cost in effective),
                Decimal("0"),
            ),
            unknown_usage_attempts=sum(
                1
                for entry in entries
                if entry.usage_source == UsageSource.UNKNOWN
                or entry.tokens.total_tokens is None
            ),
        )

    def _effective_values(self, entry: UsageEntry):
        tokens = entry.tokens
        cost = entry.cost
        with self._lock:
            adjustments = [
                item
                for item in self._adjustments_by_id.values()
                if item.original_entry_id == entry.entry_id
            ]
        adjustments.sort(key=lambda item: item.created_at)
        for adjustment in adjustments:
            if adjustment.replacement_tokens is not None:
                tokens = adjustment.replacement_tokens
            if adjustment.replacement_cost is not None:
                cost = adjustment.replacement_cost
        return tokens, cost
