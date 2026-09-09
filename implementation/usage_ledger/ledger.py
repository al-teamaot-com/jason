"""Reference append-only implementation of Jason's model usage ledger."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Iterable

from .contracts import (
    CostUsage,
    AttemptOutcome,
    TokenUsage,
    UsageContext,
    UsageAdjustment,
    UsageEntry,
    UsageSource,
    UsageTotals,
)


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_usage_entries (
    entry_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (organization_id, attempt_id)
);
CREATE INDEX IF NOT EXISTS ix_model_usage_entries_scope
  ON model_usage_entries(organization_id);
CREATE TABLE IF NOT EXISTS model_usage_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    original_entry_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (original_entry_id) REFERENCES model_usage_entries(entry_id)
);
CREATE INDEX IF NOT EXISTS ix_model_usage_adjustments_original
  ON model_usage_adjustments(original_entry_id);
"""


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


class SQLiteUsageLedger(InMemoryUsageLedger):
    """Durable append-only usage ledger with organization-scoped reads.

    Raw prompts and provider responses are intentionally excluded. Each database
    record contains only the normalized provider-neutral UsageEntry contract.
    """

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(_SQLITE_SCHEMA)
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def append(self, entry: UsageEntry) -> None:
        entry.validate()
        payload = _entry_to_json(entry)
        with self._lock, self._connection:
            row = self._connection.execute(
                """SELECT entry_id, payload_json FROM model_usage_entries
                   WHERE organization_id = ? AND attempt_id = ?""",
                (entry.context.organization_id, entry.context.attempt_id),
            ).fetchone()
            if row is not None:
                if str(row[0]) == entry.entry_id and str(row[1]) == payload:
                    return
                raise DuplicateAttemptError(
                    f"attempt {entry.context.attempt_id!r} already has a different ledger entry"
                )
            if self._connection.execute(
                "SELECT 1 FROM model_usage_entries WHERE entry_id = ?", (entry.entry_id,)
            ).fetchone() is not None:
                raise DuplicateAttemptError(f"entry ID {entry.entry_id!r} already exists")
            self._connection.execute(
                """INSERT INTO model_usage_entries(
                       entry_id, organization_id, attempt_id, payload_json
                   ) VALUES (?, ?, ?, ?)""",
                (entry.entry_id, entry.context.organization_id, entry.context.attempt_id, payload),
            )

    def append_adjustment(self, adjustment: UsageAdjustment) -> None:
        if not adjustment.adjustment_id:
            raise ValueError("adjustment ID is required")
        if not adjustment.reason:
            raise ValueError("adjustment reason is required")
        if adjustment.replacement_tokens is not None:
            adjustment.replacement_tokens.validate()
        if adjustment.replacement_cost is not None:
            adjustment.replacement_cost.validate()
        payload = _adjustment_to_json(adjustment)
        with self._lock, self._connection:
            original = self._connection.execute(
                "SELECT organization_id FROM model_usage_entries WHERE entry_id = ?",
                (adjustment.original_entry_id,),
            ).fetchone()
            if original is None:
                raise KeyError("original usage entry does not exist")
            if str(original[0]) != adjustment.organization_id:
                raise ScopeError("adjustment organization does not match original entry")
            existing = self._connection.execute(
                "SELECT payload_json FROM model_usage_adjustments WHERE adjustment_id = ?",
                (adjustment.adjustment_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) == payload:
                    return
                raise DuplicateAttemptError("adjustment ID already exists with different data")
            self._connection.execute(
                """INSERT INTO model_usage_adjustments(
                       adjustment_id, original_entry_id, organization_id, payload_json
                   ) VALUES (?, ?, ?, ?)""",
                (
                    adjustment.adjustment_id,
                    adjustment.original_entry_id,
                    adjustment.organization_id,
                    payload,
                ),
            )

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
            rows = self._connection.execute(
                """SELECT payload_json FROM model_usage_entries
                   WHERE organization_id = ? ORDER BY rowid""",
                (organization_id,),
            ).fetchall()
        entries = tuple(_entry_from_json(str(row[0])) for row in rows)
        return tuple(
            entry for entry in entries
            if (workflow_id is None or entry.context.workflow_id == workflow_id)
            and (client_id is None or entry.context.client_id == client_id)
            and (ticket_id is None or entry.context.ticket_id == ticket_id)
        )

    def _effective_values(self, entry: UsageEntry):
        tokens = entry.tokens
        cost = entry.cost
        with self._lock:
            rows = self._connection.execute(
                """SELECT payload_json FROM model_usage_adjustments
                   WHERE original_entry_id = ? ORDER BY rowid""",
                (entry.entry_id,),
            ).fetchall()
        for row in rows:
            adjustment = _adjustment_from_json(str(row[0]))
            if adjustment.replacement_tokens is not None:
                tokens = adjustment.replacement_tokens
            if adjustment.replacement_cost is not None:
                cost = adjustment.replacement_cost
        return tokens, cost

    def close(self) -> None:
        self._connection.close()


def _entry_to_json(entry: UsageEntry) -> str:
    context = entry.context
    payload = {
        "entry_id": entry.entry_id,
        "context": {
            "workflow_id": context.workflow_id, "request_id": context.request_id,
            "attempt_id": context.attempt_id, "organization_id": context.organization_id,
            "client_id": context.client_id, "capability": context.capability,
            "agent_name": context.agent_name, "ticket_id": context.ticket_id,
            "parent_attempt_id": context.parent_attempt_id,
            "routing_profile": context.routing_profile, "metadata": dict(context.metadata),
        },
        "provider": entry.provider, "model": entry.model, "outcome": entry.outcome.value,
        "usage_source": entry.usage_source.value, "tokens": _tokens_dict(entry.tokens),
        "cost": {
            "provider_reported_cost": _decimal_text(entry.cost.provider_reported_cost),
            "calculated_cost": _decimal_text(entry.cost.calculated_cost),
            "currency": entry.cost.currency,
        },
        "provider_request_id": entry.provider_request_id,
        "provider_usage_reference": entry.provider_usage_reference,
        "finish_reason": entry.finish_reason,
        "started_at": _datetime_text(entry.started_at),
        "completed_at": _datetime_text(entry.completed_at),
        "duration_ms": entry.duration_ms, "time_to_first_token_ms": entry.time_to_first_token_ms,
        "local_eval_duration_ms": entry.local_eval_duration_ms,
        "confidence": entry.confidence, "metadata": dict(entry.metadata),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _entry_from_json(raw: str) -> UsageEntry:
    item = json.loads(raw); context = item["context"]; cost = item["cost"]
    return UsageEntry(
        entry_id=item["entry_id"], context=UsageContext(**context), provider=item["provider"],
        model=item["model"], outcome=AttemptOutcome(item["outcome"]),
        usage_source=UsageSource(item["usage_source"]), tokens=TokenUsage(**item["tokens"]),
        cost=CostUsage(
            provider_reported_cost=_decimal_value(cost["provider_reported_cost"]),
            calculated_cost=_decimal_value(cost["calculated_cost"]),
            currency=cost["currency"],
        ),
        provider_request_id=item["provider_request_id"],
        provider_usage_reference=item["provider_usage_reference"],
        finish_reason=item["finish_reason"],
        started_at=(None if item["started_at"] is None else datetime.fromisoformat(item["started_at"])),
        completed_at=datetime.fromisoformat(item["completed_at"]),
        duration_ms=item["duration_ms"],
        time_to_first_token_ms=item["time_to_first_token_ms"],
        local_eval_duration_ms=item["local_eval_duration_ms"],
        confidence=float(item["confidence"]), metadata=item["metadata"],
    )


def _adjustment_to_json(adjustment: UsageAdjustment) -> str:
    payload = {
        "adjustment_id": adjustment.adjustment_id,
        "original_entry_id": adjustment.original_entry_id,
        "organization_id": adjustment.organization_id, "reason": adjustment.reason,
        "created_at": adjustment.created_at.isoformat(),
        "replacement_tokens": None if adjustment.replacement_tokens is None else _tokens_dict(adjustment.replacement_tokens),
        "replacement_cost": None if adjustment.replacement_cost is None else {
            "provider_reported_cost": _decimal_text(adjustment.replacement_cost.provider_reported_cost),
            "calculated_cost": _decimal_text(adjustment.replacement_cost.calculated_cost),
            "currency": adjustment.replacement_cost.currency,
        },
        "authoritative_reference": adjustment.authoritative_reference,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _adjustment_from_json(raw: str) -> UsageAdjustment:
    item = json.loads(raw); tokens = item["replacement_tokens"]; cost = item["replacement_cost"]
    return UsageAdjustment(
        adjustment_id=item["adjustment_id"], original_entry_id=item["original_entry_id"],
        organization_id=item["organization_id"], reason=item["reason"],
        created_at=datetime.fromisoformat(item["created_at"]),
        replacement_tokens=None if tokens is None else TokenUsage(**tokens),
        replacement_cost=None if cost is None else CostUsage(
            provider_reported_cost=_decimal_value(cost["provider_reported_cost"]),
            calculated_cost=_decimal_value(cost["calculated_cost"]), currency=cost["currency"]),
        authoritative_reference=item["authoritative_reference"],
    )


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal_value(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _tokens_dict(tokens: TokenUsage) -> dict[str, int | None]:
    return {
        "input_tokens": tokens.input_tokens,
        "cached_input_tokens": tokens.cached_input_tokens,
        "output_tokens": tokens.output_tokens,
        "reasoning_tokens": tokens.reasoning_tokens,
        "total_tokens": tokens.total_tokens,
    }
