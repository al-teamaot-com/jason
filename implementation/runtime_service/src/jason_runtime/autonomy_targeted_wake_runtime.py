"""Read-only runtime execution for targeted autonomy wakes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from autonomous_remediation.targeted_recheck import (
    SQLiteTargetedWakeStore,
    WakeKind,
)


class GovernedReadPort(Protocol):
    def execute(self, capability: str, arguments): ...


class QueueAttentionPort(Protocol):
    def request_reconcile(self, reason: str) -> None: ...


DEFAULT_TARGETED_READ_CAPABILITIES = frozenset(
    {
        "service.ticket.read",
        "automation.job.read",
        "automation.job.output.read",
        "endpoint.device.read",
        "endpoint.alert.search",
        "backup.endpoint.asset.read",
        "backup.endpoint.backup.search",
    }
)


class TargetedWakeMaintenance:
    """Execute only due targeted reads; never provider mutations."""

    def __init__(
        self,
        *,
        store: SQLiteTargetedWakeStore,
        reads: GovernedReadPort,
        queue_attention: QueueAttentionPort,
        allowed_capabilities=frozenset(DEFAULT_TARGETED_READ_CAPABILITIES),
        retry_seconds: int = 300,
        maximum_per_tick: int = 20,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if retry_seconds < 60:
            raise ValueError("retry_seconds must be at least 60")
        if not 1 <= maximum_per_tick <= 100:
            raise ValueError("maximum_per_tick must be between 1 and 100")
        self.store = store
        self.reads = reads
        self.queue_attention = queue_attention
        self.allowed_capabilities = frozenset(allowed_capabilities)
        self.retry_seconds = retry_seconds
        self.maximum_per_tick = maximum_per_tick
        self.now = now or (lambda: datetime.now(timezone.utc))

    def tick(self) -> bool:
        current = self.now()
        due = self.store.due(now=current, limit=self.maximum_per_tick)
        if not due:
            return False

        for item in due:
            wake = item.wake
            try:
                if wake.kind is WakeKind.QUEUE_RECONCILE:
                    self.queue_attention.request_reconcile(
                        f"targeted_wake:{wake.reason}"
                    )
                    self.store.complete(wake.wake_id)
                    continue

                capability = str(wake.capability_name or "").strip()
                if capability not in self.allowed_capabilities:
                    raise PermissionError(
                        f"targeted wake capability is not allowlisted: {capability}"
                    )

                result = self.reads.execute(capability, dict(wake.arguments))
                if str(result.get("status") or "") != "succeeded":
                    raise RuntimeError(
                        str(
                            result.get("error_code")
                            or result.get("reason_codes")
                            or "targeted read failed"
                        )
                    )

                self.store.complete(wake.wake_id)
                if wake.queue_reconciliation_required:
                    self.queue_attention.request_reconcile(
                        f"targeted_read_complete:{wake.resource_id}"
                    )
            except Exception as exc:
                self.store.retry_or_fail(
                    wake.wake_id,
                    error=f"{type(exc).__name__}:{exc}",
                    next_due_at=current + timedelta(seconds=self.retry_seconds),
                )

        return True


class CompositeAutonomyMaintenance:
    """Run bounded maintenance services on the runtime's owning thread."""

    def __init__(self, *services) -> None:
        self.services = tuple(service for service in services if service is not None)

    def tick(self) -> bool:
        handled = False
        for service in self.services:
            handled = bool(service.tick()) or handled
        return handled
