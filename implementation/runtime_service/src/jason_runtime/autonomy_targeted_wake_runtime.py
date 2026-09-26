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


DATTO_TERMINAL_JOB_STATUSES = frozenset({
    "complete", "completed", "success", "successful", "succeeded", "finished",
    "failed", "failure", "error", "cancelled", "canceled", "aborted",
})


class AutonomyAttentionEventIngress:
    """Provider-neutral bridge from trusted runtime events into scheduler attention.

    Known work is signaled by exact resource ID so only matching armed wakes become
    due. Broad queue reconciliation is opt-in and must be declared by the producer;
    ordinary known-work events never imply a whole-queue scan.
    """

    def __init__(
        self,
        *,
        store: SQLiteTargetedWakeStore,
        queue_attention: QueueAttentionPort,
    ) -> None:
        self.store = store
        self.queue_attention = queue_attention

    def signal(
        self,
        *,
        event: str,
        resource_id: str,
        queue_reconciliation_required: bool = False,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        normalized_event = str(event or "").strip()
        normalized_resource = str(resource_id or "").strip()
        if not normalized_event:
            raise ValueError("attention event must be non-empty")
        if not normalized_resource:
            raise ValueError("attention resource_id must be non-empty")
        if any(token in normalized_resource for token in ("*", "?", "[", "]")):
            raise ValueError("attention resource_id must be exact")

        wake_ids = self.store.signal(
            normalized_event,
            resource_id=normalized_resource,
            now=now,
        )
        if queue_reconciliation_required:
            self.queue_attention.request_reconcile(
                f"event:{normalized_event}:{normalized_resource}"
            )
        return wake_ids

    def approval_received(
        self,
        resource_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        resource = str(resource_id or "").strip()
        if not resource:
            raise ValueError("approval attention resource_id must be non-empty")
        if any(token in resource for token in ("*", "?", "[", "]")):
            raise ValueError("approval attention resource_id must be exact")
        return self.store.signal_subject(
            "approval_received",
            event_subject_id=resource,
            now=now,
        )

    def observe_datto_job_read(
        self,
        result,
        *,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        if str(result.get("status") or "") != "succeeded":
            return ()
        evidence = result.get("evidence") or {}
        job = evidence.get("job") if isinstance(evidence, dict) else None
        if not isinstance(job, dict):
            return ()
        job_uid = str(job.get("resource_id") or "").strip()
        status = str(job.get("status") or "").strip().casefold()
        if not job_uid or status not in DATTO_TERMINAL_JOB_STATUSES:
            return ()
        return self.store.signal_subject(
            "job_completed",
            event_subject_id=job_uid,
            now=now,
        )

    def observe_device_read(
        self,
        result,
        *,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        if str(result.get("status") or "") != "succeeded":
            return ()
        evidence = result.get("evidence") or {}
        record = evidence.get("record") if isinstance(evidence, dict) else None
        if not isinstance(record, dict):
            return ()
        device_uid = str(record.get("resource_id") or "").strip()
        if not device_uid or record.get("online") is not True:
            return ()
        return self.store.signal_subject(
            "device_online",
            event_subject_id=device_uid,
            now=now,
        )


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
        event_ingress: AutonomyAttentionEventIngress | None = None,
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
        self.event_ingress = event_ingress
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

                if self.event_ingress is not None:
                    if capability == "automation.job.read":
                        self.event_ingress.observe_datto_job_read(result, now=current)
                    elif capability == "endpoint.device.read":
                        self.event_ingress.observe_device_read(result, now=current)

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


class TicketAttentionRelay:
    """Late-bound bridge from verified ticket events to queue attention."""

    def __init__(self) -> None:
        self._target = None

    def bind(self, target) -> None:
        self._target = target

    def notify(self, *, event: str, ticket_id: int) -> None:
        if self._target is None:
            return
        normalized_event = str(event or "").strip()
        if normalized_event not in {"ticket_created", "ticket_changed"}:
            raise ValueError("unsupported ticket attention event")
        ticket = int(ticket_id)
        if ticket < 1:
            raise ValueError("ticket attention id must be positive")
        self._target.request_reconcile(f"autotask:{normalized_event}:{ticket}")


class CompositeAutonomyMaintenance:
    """Run bounded maintenance services on the runtime's owning thread."""

    def __init__(self, *services) -> None:
        self.services = tuple(service for service in services if service is not None)

    def request_reconcile(self, reason: str) -> None:
        delivered = False
        for service in self.services:
            callback = getattr(service, "request_reconcile", None)
            if callback is None:
                continue
            callback(reason)
            delivered = True
        if not delivered:
            raise RuntimeError("autonomy maintenance has no queue attention target")

    def tick(self) -> bool:
        handled = False
        for service in self.services:
            handled = bool(service.tick()) or handled
        return handled
