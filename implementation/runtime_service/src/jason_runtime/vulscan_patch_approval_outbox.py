"""Drain VulScan V2 notifications through the preexisting durable Teams outbox.

Uses the existing operational SQLite outbox and JasonTeamsCommunicationService.
No second provider, bot, transport, approval callback, or delivery queue.
This lane is intentionally NOT registered in production composition.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .vulscan_patch_approval_notification import PreparedPatchNotification

if TYPE_CHECKING:
    from .autonomy_worker_runtime import SQLiteOperationalWorkStore


def drain_patch_approval_notifications(
    *, store: SQLiteOperationalWorkStore, notifier: Any,
    verify_current: Callable[[PreparedPatchNotification], bool] | None,
    now: datetime | None = None,
    audit: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> int:
    """Make bounded, at-most-once send attempts after authoritative recheck.

    The verified callback must independently re-read current patch approval and
    release evidence with exact client/policy bounds. An exception, absent
    callback or false verification cannot cause a Teams send. A provider timeout
    after entering 'sending' requires reconciliation, never automatic replay.
    """
    if notifier is None or verify_current is None:
        return 0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("timezone-aware current time required")

    def record(name: str, fields: Mapping[str, Any]) -> None:
        if audit:
            try:
                audit(name, fields)
            except Exception:
                pass

    # Crash-safe reconciliation: a claimed send older than five minutes
    # cannot be replayed because the provider outcome may be unknown.
    store.reconcile_inflight_patch_approval_notifications(
        older_than=current - timedelta(minutes=5))
    attempts = 0
    for row in store.due_patch_approval_notifications(now=current, limit=4):
        key = str(row["event_key"])
        try:
            created = datetime.fromisoformat(str(row["recorded_at"]))
            if created.tzinfo is None or current - created > timedelta(hours=24):
                store.record_teams_notification_result(
                    event_key=key, state="expired", attempts=int(row["attempts"]),
                    next_due_at=current + timedelta(days=365),
                    last_error="stale_or_invalid_event_timestamp",
                )
                continue
            payload = json.loads(str(row["arguments_json"]))
            notification = PreparedPatchNotification(
                kb=str(payload["kb"]),
                stage=str(payload["stage"]),
                released=date.fromisoformat(payload["released"]),
                age_days=int(payload["age_days"]),
                policy_ids=tuple(payload["policy_ids"]),
                affected_clients=int(payload["affected_clients"]),
                affected_devices=int(payload["affected_devices"]),
                idempotency_key=str(payload["idempotency_key"]),
                text=str(payload["text"]),
            )
            if (notification.idempotency_key != str(row["fingerprint"])
                    or str(row["event_type"]) != "patch_approval_aging"
                    or notification.age_days < 0
                    or notification.affected_devices < 1
                    or notification.affected_clients < 1):
                raise ValueError("malformed patch notification")
            if not verify_current(notification):
                store.record_teams_notification_result(
                    event_key=key, state="expired", attempts=int(row["attempts"]),
                    next_due_at=current + timedelta(days=365),
                    last_error="authoritative_patch_state_changed",
                )
                continue
        except (ValueError, TypeError, KeyError, AttributeError):
            store.record_teams_notification_result(
                event_key=key, state="expired", attempts=int(row["attempts"]),
                next_due_at=current + timedelta(days=365),
                last_error="malformed_or_unverifiable_patch_event",
            )
            continue
        except Exception as exc:
            count = int(row["attempts"]) + 1
            # Read failure before a send may be retried. Never convert it into
            # an unverified "success" or a cross-client broad search.
            store.record_teams_notification_result(
                event_key=key,
                state="expired" if count >= 3 else "pending",
                attempts=count,
                next_due_at=current + timedelta(minutes=5 if count < 3 else 525600),
                last_error=f"authoritative_recheck_{type(exc).__name__}",
            )
            continue

        if not store.claim_patch_approval_notification(event_key=key, now=current):
            continue
        attempts += 1
        try:
            result = notifier.send_prepared(notification)
            message_id = str(result.get("message_id", "")).strip()
            if not message_id:
                raise RuntimeError("missing Teams provider receipt")
            # A message_id is provider acceptance, not confirmation that the
            # human owner saw it. Do not automatically retry.
            store.record_teams_notification_result(
                event_key=key, state="unverified",
                attempts=int(row["attempts"]) + 1,
                next_due_at=current + timedelta(days=365),
                last_error="provider_accepted_human_delivery_unverified",
                message_id=message_id,
            )
            record("vulscan_patch_approval_provider_accepted", {
                "kb": notification.kb, "stage": notification.stage,
                "provider_receipt": True,
            })
        except Exception as exc:
            # Sending may have succeeded before a transport/readback failure.
            # Never automatically duplicate a potentially sent notification.
            store.record_teams_notification_result(
                event_key=key, state="unverified",
                attempts=int(row["attempts"]) + 1,
                next_due_at=current + timedelta(days=365),
                last_error=f"delivery_outcome_unknown_{type(exc).__name__}",
            )
            record("vulscan_patch_approval_delivery_unverified", {
                "kb": notification.kb, "stage": notification.stage,
                "error_type": type(exc).__name__,
            })
    return attempts
