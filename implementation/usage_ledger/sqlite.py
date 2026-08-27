"""SQLite append-only production implementation of the Jason Usage Ledger."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .contracts import (
    AttemptOutcome,
    CostUsage,
    TokenUsage,
    UsageAdjustment,
    UsageEntry,
    UsageSource,
    UsageTotals,
)
from .ledger import DuplicateAttemptError, ScopeError


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS model_usage_entries (
    entry_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    client_id TEXT,
    capability TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    outcome TEXT NOT NULL,
    usage_source TEXT NOT NULL,
    input_tokens INTEGER,
    cached_input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    total_tokens INTEGER,
    provider_reported_cost TEXT,
    calculated_cost TEXT,
    currency TEXT NOT NULL,
    provider_request_id TEXT,
    finish_reason TEXT,
    started_at TEXT,
    completed_at TEXT NOT NULL,
    duration_ms INTEGER,
    confidence REAL NOT NULL,
    metadata TEXT NOT NULL,
    UNIQUE(organization_id, attempt_id)
);

CREATE TABLE IF NOT EXISTS model_usage_adjustments (
    adjustment_id TEXT PRIMARY KEY,
    original_entry_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    input_tokens INTEGER,
    cached_input_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    total_tokens INTEGER,
    provider_reported_cost TEXT,
    calculated_cost TEXT,
    currency TEXT,
    authoritative_reference TEXT,
    FOREIGN KEY(original_entry_id) REFERENCES model_usage_entries(entry_id)
);

CREATE INDEX IF NOT EXISTS ix_model_usage_scope
ON model_usage_entries(organization_id, workflow_id, completed_at);
"""


class SQLiteUsageLedger:
    """Append-only SQLite ledger with organization-scoped reads."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def append(self, entry: UsageEntry) -> None:
        entry.validate()

        existing = self._connection.execute(
            """
            SELECT entry_id FROM model_usage_entries
            WHERE organization_id = ? AND attempt_id = ?
            """,
            (entry.context.organization_id, entry.context.attempt_id),
        ).fetchone()

        if existing is not None:
            stored = self._get_entry(str(existing["entry_id"]))
            if stored == entry:
                return
            raise DuplicateAttemptError(
                f"attempt {entry.context.attempt_id!r} already has a different ledger entry"
            )

        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO model_usage_entries(
                        entry_id, workflow_id, request_id, attempt_id,
                        organization_id, client_id, capability, provider, model,
                        outcome, usage_source, input_tokens, cached_input_tokens,
                        output_tokens, reasoning_tokens, total_tokens,
                        provider_reported_cost, calculated_cost, currency,
                        provider_request_id, finish_reason, started_at,
                        completed_at, duration_ms, confidence, metadata
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        entry.entry_id,
                        entry.context.workflow_id,
                        entry.context.request_id,
                        entry.context.attempt_id,
                        entry.context.organization_id,
                        entry.context.client_id,
                        entry.context.capability,
                        entry.provider,
                        entry.model,
                        entry.outcome.value,
                        entry.usage_source.value,
                        entry.tokens.input_tokens,
                        entry.tokens.cached_input_tokens,
                        entry.tokens.output_tokens,
                        entry.tokens.reasoning_tokens,
                        entry.tokens.total_tokens,
                        _decimal_text(entry.cost.provider_reported_cost),
                        _decimal_text(entry.cost.calculated_cost),
                        entry.cost.currency,
                        entry.provider_request_id,
                        entry.finish_reason,
                        _datetime_text(entry.started_at),
                        _datetime_text(entry.completed_at),
                        entry.duration_ms,
                        entry.confidence,
                        json.dumps(
                            dict(entry.metadata),
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateAttemptError(
                f"usage entry already exists: {entry.entry_id}"
            ) from error

    def append_adjustment(self, adjustment: UsageAdjustment) -> None:
        if not adjustment.adjustment_id:
            raise ValueError("adjustment ID is required")
        if not adjustment.reason:
            raise ValueError("adjustment reason is required")

        original = self._connection.execute(
            """
            SELECT organization_id FROM model_usage_entries
            WHERE entry_id = ?
            """,
            (adjustment.original_entry_id,),
        ).fetchone()

        if original is None:
            raise KeyError("original usage entry does not exist")

        if str(original["organization_id"]) != adjustment.organization_id:
            raise ScopeError(
                "adjustment organization does not match original entry"
            )

        tokens = adjustment.replacement_tokens
        cost = adjustment.replacement_cost

        if tokens is not None:
            tokens.validate()
        if cost is not None:
            cost.validate()

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO model_usage_adjustments(
                    adjustment_id, original_entry_id, organization_id,
                    reason, created_at, input_tokens, cached_input_tokens,
                    output_tokens, reasoning_tokens, total_tokens,
                    provider_reported_cost, calculated_cost, currency,
                    authoritative_reference
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    adjustment.adjustment_id,
                    adjustment.original_entry_id,
                    adjustment.organization_id,
                    adjustment.reason,
                    _datetime_text(adjustment.created_at),
                    None if tokens is None else tokens.input_tokens,
                    None if tokens is None else tokens.cached_input_tokens,
                    None if tokens is None else tokens.output_tokens,
                    None if tokens is None else tokens.reasoning_tokens,
                    None if tokens is None else tokens.total_tokens,
                    None if cost is None else _decimal_text(cost.provider_reported_cost),
                    None if cost is None else _decimal_text(cost.calculated_cost),
                    None if cost is None else cost.currency,
                    adjustment.authoritative_reference,
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

        clauses = ["organization_id = ?"]
        values: list[object] = [organization_id]

        if workflow_id is not None:
            clauses.append("workflow_id = ?")
            values.append(workflow_id)

        if client_id is not None:
            clauses.append("client_id = ?")
            values.append(client_id)

        rows = self._connection.execute(
            """
            SELECT * FROM model_usage_entries
            WHERE """ + " AND ".join(clauses) + """
            ORDER BY completed_at, entry_id
            """,
            tuple(values),
        ).fetchall()

        entries = tuple(self._entry_from_row(row) for row in rows)

        # ticket_id is not currently populated by hosted Conversation Kernel work.
        if ticket_id is not None:
            return tuple(
                item
                for item in entries
                if item.context.ticket_id == ticket_id
            )

        return entries

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

        effective = [self._effective(item) for item in entries]

        return UsageTotals(
            attempts=len(entries),
            input_tokens=sum((t.input_tokens or 0) for t, _ in effective),
            cached_input_tokens=sum(
                (t.cached_input_tokens or 0) for t, _ in effective
            ),
            output_tokens=sum((t.output_tokens or 0) for t, _ in effective),
            reasoning_tokens=sum(
                (t.reasoning_tokens or 0) for t, _ in effective
            ),
            total_tokens=sum((t.total_tokens or 0) for t, _ in effective),
            provider_reported_cost=sum(
                (c.provider_reported_cost or Decimal("0") for _, c in effective),
                Decimal("0"),
            ),
            calculated_cost=sum(
                (c.calculated_cost or Decimal("0") for _, c in effective),
                Decimal("0"),
            ),
            unknown_usage_attempts=sum(
                1
                for item in entries
                if item.usage_source is UsageSource.UNKNOWN
                or item.tokens.total_tokens is None
            ),
        )

    def close(self) -> None:
        self._connection.close()

    def _get_entry(self, entry_id: str) -> UsageEntry:
        row = self._connection.execute(
            "SELECT * FROM model_usage_entries WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return self._entry_from_row(row)

    def _effective(self, entry: UsageEntry):
        tokens = entry.tokens
        cost = entry.cost

        rows = self._connection.execute(
            """
            SELECT * FROM model_usage_adjustments
            WHERE original_entry_id = ?
            ORDER BY created_at, adjustment_id
            """,
            (entry.entry_id,),
        ).fetchall()

        for row in rows:
            if any(
                row[name] is not None
                for name in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                    "total_tokens",
                )
            ):
                tokens = TokenUsage(
                    input_tokens=row["input_tokens"],
                    cached_input_tokens=row["cached_input_tokens"],
                    output_tokens=row["output_tokens"],
                    reasoning_tokens=row["reasoning_tokens"],
                    total_tokens=row["total_tokens"],
                )

            if (
                row["provider_reported_cost"] is not None
                or row["calculated_cost"] is not None
            ):
                cost = CostUsage(
                    provider_reported_cost=_decimal(row["provider_reported_cost"]),
                    calculated_cost=_decimal(row["calculated_cost"]),
                    currency=str(row["currency"] or "USD"),
                )

        return tokens, cost

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> UsageEntry:
        from .contracts import UsageContext

        return UsageEntry(
            entry_id=str(row["entry_id"]),
            context=UsageContext(
                workflow_id=str(row["workflow_id"]),
                request_id=str(row["request_id"]),
                attempt_id=str(row["attempt_id"]),
                organization_id=str(row["organization_id"]),
                client_id=row["client_id"],
                capability=str(row["capability"]),
            ),
            provider=str(row["provider"]),
            model=str(row["model"]),
            outcome=AttemptOutcome(str(row["outcome"])),
            usage_source=UsageSource(str(row["usage_source"])),
            tokens=TokenUsage(
                input_tokens=row["input_tokens"],
                cached_input_tokens=row["cached_input_tokens"],
                output_tokens=row["output_tokens"],
                reasoning_tokens=row["reasoning_tokens"],
                total_tokens=row["total_tokens"],
            ),
            cost=CostUsage(
                provider_reported_cost=_decimal(row["provider_reported_cost"]),
                calculated_cost=_decimal(row["calculated_cost"]),
                currency=str(row["currency"]),
            ),
            provider_request_id=row["provider_request_id"],
            finish_reason=row["finish_reason"],
            started_at=_datetime(row["started_at"]),
            completed_at=_datetime(row["completed_at"]),
            duration_ms=row["duration_ms"],
            confidence=float(row["confidence"]),
            metadata=json.loads(str(row["metadata"])),
        )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _datetime(value: object) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))
