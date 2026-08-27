"""Durable provider capability readiness state and transition evidence.

This module has no provider-specific knowledge and no alert delivery authority.

It stores:
- latest readiness state per provider/capability;
- append-only readiness transitions;
- append-only alert-event intents.

Delivery of an alert remains a separately governed capability.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from .provider_capability_readiness import (
    ProviderCapabilityReadiness,
    ReadinessReason,
    ReadinessState,
    ReadinessTransition,
)


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS provider_capability_readiness (
    provider_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    evidence_source TEXT NOT NULL,
    provider_status_code TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(provider_id, capability_name)
);

CREATE TABLE IF NOT EXISTS provider_capability_readiness_transitions (
    transition_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    previous_state TEXT,
    previous_reason TEXT,
    current_state TEXT NOT NULL,
    current_reason TEXT NOT NULL,
    changed INTEGER NOT NULL,
    should_alert INTEGER NOT NULL,
    recovery INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_provider_readiness_transition_identity
ON provider_capability_readiness_transitions(
    provider_id,
    capability_name,
    recorded_at
);

CREATE TABLE IF NOT EXISTS provider_capability_alert_events (
    alert_event_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    readiness_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    provider_status_code TEXT,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_provider_readiness_alert_delivery
ON provider_capability_alert_events(
    delivered,
    created_at
);
"""


@dataclass(frozen=True, slots=True)
class ProviderReadinessAlertEvent:
    alert_event_id: str
    provider_id: str
    capability_name: str
    event_kind: str
    readiness_state: ReadinessState
    reason: ReadinessReason
    provider_status_code: str | None
    observed_at: datetime
    created_at: datetime
    delivered: bool = False


class SQLiteProviderCapabilityReadinessStore:
    """Durable readiness state with append-only transition evidence."""

    def __init__(
        self,
        path: str | Path = ":memory:",
    ) -> None:
        self._path = str(path)
        self._connection = sqlite3.connect(
            self._path
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            _SCHEMA
        )
        self._connection.commit()

    def get(
        self,
        *,
        provider_id: str,
        capability_name: str,
    ) -> ProviderCapabilityReadiness | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM provider_capability_readiness
            WHERE provider_id = ?
              AND capability_name = ?
            """,
            (
                provider_id,
                capability_name,
            ),
        ).fetchone()

        if row is None:
            return None

        return self._readiness_from_row(
            row
        )

    def record(
        self,
        *,
        transition: ReadinessTransition,
    ) -> ProviderReadinessAlertEvent | None:
        current = transition.current
        now = datetime.now(
            timezone.utc
        )

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO provider_capability_readiness(
                    provider_id,
                    capability_name,
                    state,
                    reason,
                    observed_at,
                    evidence_source,
                    provider_status_code,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    provider_id,
                    capability_name
                )
                DO UPDATE SET
                    state = excluded.state,
                    reason = excluded.reason,
                    observed_at = excluded.observed_at,
                    evidence_source = excluded.evidence_source,
                    provider_status_code = excluded.provider_status_code,
                    updated_at = excluded.updated_at
                """,
                (
                    current.provider_id,
                    current.capability_name,
                    current.state.value,
                    current.reason.value,
                    current.observed_at.astimezone(
                        timezone.utc
                    ).isoformat(),
                    current.evidence_source,
                    current.provider_status_code,
                    now.isoformat(),
                ),
            )

            self._connection.execute(
                """
                INSERT INTO provider_capability_readiness_transitions(
                    transition_id,
                    provider_id,
                    capability_name,
                    previous_state,
                    previous_reason,
                    current_state,
                    current_reason,
                    changed,
                    should_alert,
                    recovery,
                    observed_at,
                    recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    current.provider_id,
                    current.capability_name,
                    (
                        transition.previous.state.value
                        if transition.previous is not None
                        else None
                    ),
                    (
                        transition.previous.reason.value
                        if transition.previous is not None
                        else None
                    ),
                    current.state.value,
                    current.reason.value,
                    1 if transition.changed else 0,
                    1 if transition.should_alert else 0,
                    1 if transition.recovery else 0,
                    current.observed_at.astimezone(
                        timezone.utc
                    ).isoformat(),
                    now.isoformat(),
                ),
            )

            alert = None

            if transition.should_alert:
                alert = self._create_alert_event(
                    transition=transition,
                    now=now,
                )

                self._connection.execute(
                    """
                    INSERT INTO provider_capability_alert_events(
                        alert_event_id,
                        provider_id,
                        capability_name,
                        event_kind,
                        readiness_state,
                        reason,
                        provider_status_code,
                        observed_at,
                        created_at,
                        delivered
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.alert_event_id,
                        alert.provider_id,
                        alert.capability_name,
                        alert.event_kind,
                        alert.readiness_state.value,
                        alert.reason.value,
                        alert.provider_status_code,
                        alert.observed_at.astimezone(
                            timezone.utc
                        ).isoformat(),
                        alert.created_at.astimezone(
                            timezone.utc
                        ).isoformat(),
                        0,
                    ),
                )

        return alert

    def pending_alerts(
        self,
    ) -> tuple[ProviderReadinessAlertEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT *
            FROM provider_capability_alert_events
            WHERE delivered = 0
            ORDER BY created_at, alert_event_id
            """
        ).fetchall()

        return tuple(
            self._alert_from_row(
                row
            )
            for row in rows
        )

    def mark_alert_delivered(
        self,
        *,
        alert_event_id: str,
    ) -> None:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE provider_capability_alert_events
                SET delivered = 1
                WHERE alert_event_id = ?
                  AND delivered = 0
                """,
                (
                    alert_event_id,
                ),
            )

        if cursor.rowcount == 0:
            raise KeyError(
                "pending readiness alert event not found"
            )

    def transition_history(
        self,
        *,
        provider_id: str,
        capability_name: str,
    ) -> tuple[Mapping[str, object], ...]:
        rows = self._connection.execute(
            """
            SELECT *
            FROM provider_capability_readiness_transitions
            WHERE provider_id = ?
              AND capability_name = ?
            ORDER BY recorded_at, transition_id
            """,
            (
                provider_id,
                capability_name,
            ),
        ).fetchall()

        return tuple(
            {
                key: row[key]
                for key in row.keys()
            }
            for row in rows
        )

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _create_alert_event(
        *,
        transition: ReadinessTransition,
        now: datetime,
    ) -> ProviderReadinessAlertEvent:
        current = transition.current

        if transition.recovery:
            event_kind = "provider_capability_recovered"
        else:
            event_kind = "provider_capability_unavailable"

        return ProviderReadinessAlertEvent(
            alert_event_id=str(
                uuid4()
            ),
            provider_id=current.provider_id,
            capability_name=current.capability_name,
            event_kind=event_kind,
            readiness_state=current.state,
            reason=current.reason,
            provider_status_code=current.provider_status_code,
            observed_at=current.observed_at,
            created_at=now,
            delivered=False,
        )

    @staticmethod
    def _readiness_from_row(
        row: sqlite3.Row,
    ) -> ProviderCapabilityReadiness:
        return ProviderCapabilityReadiness(
            provider_id=row["provider_id"],
            capability_name=row[
                "capability_name"
            ],
            state=ReadinessState(
                row["state"]
            ),
            reason=ReadinessReason(
                row["reason"]
            ),
            observed_at=datetime.fromisoformat(
                row["observed_at"]
            ),
            evidence_source=row[
                "evidence_source"
            ],
            provider_status_code=row[
                "provider_status_code"
            ],
        )

    @staticmethod
    def _alert_from_row(
        row: sqlite3.Row,
    ) -> ProviderReadinessAlertEvent:
        return ProviderReadinessAlertEvent(
            alert_event_id=row[
                "alert_event_id"
            ],
            provider_id=row[
                "provider_id"
            ],
            capability_name=row[
                "capability_name"
            ],
            event_kind=row[
                "event_kind"
            ],
            readiness_state=ReadinessState(
                row["readiness_state"]
            ),
            reason=ReadinessReason(
                row["reason"]
            ),
            provider_status_code=row[
                "provider_status_code"
            ],
            observed_at=datetime.fromisoformat(
                row["observed_at"]
            ),
            created_at=datetime.fromisoformat(
                row["created_at"]
            ),
            delivered=bool(
                row["delivered"]
            ),
        )
