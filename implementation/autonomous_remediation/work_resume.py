"""Exact work-item resume boundary for targeted autonomy wakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .attention_scheduler import WorkLedger, WorkState


_RESUMABLE_STATES = frozenset(
    {
        WorkState.WAITING,
        WorkState.APPROVAL_PENDING,
    }
)


class LedgerWorkResumePort:
    """Resume one persisted work item without reconciling the whole queue."""

    def __init__(
        self,
        ledger: WorkLedger,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.ledger = ledger
        self.now = now or (lambda: datetime.now(timezone.utc))

    def resume(self, resource_id: str, *, reason: str) -> bool:
        item = self.ledger.get(resource_id)
        if item is None:
            raise KeyError(f"unknown autonomous work item: {resource_id}")

        if item.state not in _RESUMABLE_STATES:
            # Stale wake: never resurrect terminal, blocked, or already-running work.
            return False

        self.ledger.upsert(
            replace(
                item,
                state=WorkState.AVAILABLE,
                next_check_at=None,
                wake_on=None,
                queue_reconciliation_required=False,
                reason=str(reason or "targeted recheck completed")[:500],
                updated_at=self.now(),
            )
        )
        return True
