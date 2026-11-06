"""Deliver durable ticket-owner notifications outside the ticket scan process.

This is intentionally a separate auxiliary maintenance lane. A slow Teams POST
must never hold the operational ticket worker's scan heartbeat or remediation
capacity. The outbox is shared via the existing WAL SQLite state; no direct
Teams/provider route or new autonomous approval is introduced.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping
from uuid import uuid4

if TYPE_CHECKING:
    from .autonomy_worker_runtime import SQLiteOperationalWorkStore


def drain_owner_notification_outbox(
    *,
    store: SQLiteOperationalWorkStore,
    notifier: Any,
    audit: Callable[[str, Mapping[str, Any]], None] | None = None,
    now: datetime | None = None,
) -> int:
    if notifier is None:
        return 0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("notification drain requires timezone-aware time")

    def record(event: str, data: Mapping[str, Any]) -> None:
        if audit is not None:
            try:
                audit(event, data)
            except Exception:
                pass  # Structured outbox remains authoritative, not audit transport.

    try:
        due = store.due_teams_notifications(now=current, limit=4)
    except Exception as exc:
        record("ticket_teams_outbox_read_failed", {"error_type": type(exc).__name__})
        return 0

    attempted = 0
    for row in due:
        event_key = str(row["event_key"])
        attempts = int(row["attempts"]) + 1
        try:
            created = datetime.fromisoformat(str(row["recorded_at"]))
            if created.tzinfo is None or current - created > timedelta(hours=24):
                store.record_teams_notification_result(
                    event_key=event_key, state="expired", attempts=attempts,
                    next_due_at=current + timedelta(days=365),
                    last_error="older_than_24h_or_invalid_timestamp",
                )
                continue
        except (ValueError, TypeError):
            continue

        # Never send a stale owner-action request after the corresponding PSA
        # assessment has changed or been retired by a later scan.
        if str(row["event_type"]) == "work_blocked":
            disposition = store.classification_disposition(int(row["ticket_id"]))
            expected = (
                "Teams - Owner Action - " + disposition[0] + " - " + disposition[1]
                if disposition else None
            )
            if str(row["note_title"]) != expected:
                store.record_teams_notification_result(
                    event_key=event_key, state="expired", attempts=attempts,
                    next_due_at=current + timedelta(days=365),
                    last_error="ticket_disposition_changed_or_missing",
                )
                continue

        attempted += 1
        try:
            payload = json.loads(str(row["arguments_json"]))
            result = notifier.send(str(row["event_type"]), **payload)
            if not isinstance(result, Mapping):
                raise RuntimeError("Teams provider returned no receipt")
            message_id = str(result.get("message_id") or "").strip()
            if not message_id:
                raise RuntimeError("Teams provider message reference missing")
            synthetic = result.get(
                "message_id_synthetic", message_id.startswith("accepted:")
            )
            if type(synthetic) is not bool:
                raise RuntimeError("Teams provider receipt is malformed")
            state = "unverified" if synthetic else "delivered"
            store.record_teams_notification_result(
                event_key=event_key, state=state, attempts=attempts,
                next_due_at=current + timedelta(days=365),
                last_error=None, message_id=message_id,
            )
            if not synthetic:
                try:
                    store.remember_note_fingerprint(
                        int(row["ticket_id"]), str(row["playbook_id"]),
                        str(row["note_title"]), str(row["fingerprint"]),
                    )
                except Exception:
                    # The delivered marker, not a secondary fingerprint, is
                    # authoritative for suppressing a duplicate send.
                    pass
            record("ticket_teams_outbox_result", {
                "ticket_id": int(row["ticket_id"]),
                "event_type": str(row["event_type"]), "state": state,
            })
        except Exception as exc:
            retry_seconds = min(3600, 300 * (2 ** min(attempts - 1, 4)))
            store.record_teams_notification_result(
                event_key=event_key, state="pending", attempts=attempts,
                next_due_at=current + timedelta(seconds=retry_seconds),
                last_error=type(exc).__name__,
            )
            record("ticket_teams_notification_failed", {
                "ticket_id": int(row["ticket_id"]),
                "event_type": str(row["event_type"]),
                "attempts": attempts, "error_type": type(exc).__name__,
            })
    return attempted


class TicketOwnerNotificationMaintenance:
    """Independent auxiliary-process reader of the worker's persistent outbox."""

    def __init__(
        self, *, store: SQLiteOperationalWorkStore, notifier: Any, audit: Any = None,
        interval_seconds: int = 15, monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds < 5:
            raise ValueError("owner notification interval is too short")
        self.store = store
        self.notifier = notifier
        self.audit = audit
        self.interval_seconds = interval_seconds
        self.monotonic = monotonic
        self._next_due = 0.0

    def _record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self.audit is None:
            return
        event_id = "ticket-owner-notification-" + uuid4().hex
        self.audit.append(event_type, {
            "execution_id": event_id,
            "correlation_id": event_id,
            "organization_id": "aot",
            "principal_id": "jason-autonomy-worker",
            "capability_name": "autonomy.ticket.owner_notification",
            "stage": "completed",
            **dict(payload),
        })

    def tick(self) -> None:
        now = self.monotonic()
        if now < self._next_due:
            return
        self._next_due = now + self.interval_seconds
        drain_owner_notification_outbox(
            store=self.store,
            notifier=self.notifier,
            audit=self._record,
        )
