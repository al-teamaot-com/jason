"""Provider-neutral autonomous queue worker.

This module coordinates attention, matching, ownership and execution. It never
calls Autotask, DRMM or another provider directly; runtime adapters remain behind
Central Orchestrator governed capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence

from .attention_scheduler import (
    AttentionScheduler,
    AutonomyConfig,
    QueueAttentionState,
    WorkItem,
    WorkLedger,
    WorkState,
)
from .playbook_matching import MatchState, PlaybookMatch
from .targeted_recheck import TargetedWake, WakeKind


@dataclass(frozen=True)
class QueueCandidate:
    resource_id: str
    priority: int
    source_queue: str
    owned_by_jason: bool = False
    urgent: bool = False
    source_version: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecheckRequest:
    """Exact read-only follow-up requested by a playbook outcome."""

    capability_name: str
    arguments: Mapping[str, Any]
    due_at: datetime | None = None
    wake_on: str | None = None
    queue_reconciliation_required: bool = False
    max_attempts: int = 3

    def __post_init__(self) -> None:
        capability = str(self.capability_name or "").strip()
        if not capability:
            raise ValueError("recheck capability_name must be non-empty")
        if (self.due_at is None) == (not str(self.wake_on or "").strip()):
            raise ValueError("recheck requires exactly one of due_at or wake_on")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("recheck due_at must be timezone-aware")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("recheck max_attempts must be between 1 and 10")
        try:
            json.dumps(dict(self.arguments), sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("recheck arguments must be JSON-serializable") from exc

    def to_wake(
        self,
        *,
        resource_id: str,
        playbook_id: str,
        reason: str,
    ) -> TargetedWake:
        fingerprint_payload = {
            "resource_id": resource_id,
            "playbook_id": playbook_id,
            "capability_name": self.capability_name,
            "arguments": dict(self.arguments),
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "wake_on": self.wake_on,
            "queue_reconciliation_required": self.queue_reconciliation_required,
            "resume_work_item": True,
        }
        encoded = json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        wake_id = "recheck_" + hashlib.sha256(encoded).hexdigest()[:32]
        return TargetedWake(
            wake_id=wake_id,
            resource_id=resource_id,
            reason=reason,
            kind=WakeKind.TARGETED_READ,
            due_at=self.due_at,
            wake_on=self.wake_on,
            capability_name=self.capability_name,
            arguments=dict(self.arguments),
            queue_reconciliation_required=self.queue_reconciliation_required,
            resume_work_item=True,
            max_attempts=self.max_attempts,
        )


@dataclass(frozen=True)
class WorkStepResult:
    state: WorkState
    reason: str
    next_action: str | None = None
    next_check_at: datetime | None = None
    wake_on: str | None = None
    queue_reconciliation_required: bool = False
    recheck: RecheckRequest | None = None

    def __post_init__(self) -> None:
        if self.recheck is not None:
            if self.next_check_at is not None or self.wake_on is not None:
                raise ValueError(
                    "structured recheck cannot be combined with legacy next_check_at/wake_on"
                )
            if self.state not in {
                WorkState.WAITING,
                WorkState.APPROVAL_PENDING,
            }:
                raise ValueError(
                    "structured recheck is valid only for waiting/approval-pending work"
                )


@dataclass(frozen=True)
class WorkerCycleResult:
    reconciled: bool
    reconcile_reason: str
    activated: tuple[str, ...]
    investigated: tuple[str, ...]
    executed: tuple[str, ...]
    blocked: tuple[str, ...]


class QueueSourcePort(Protocol):
    def reconcile_candidates(self) -> Sequence[QueueCandidate]: ...


class PlaybookClassificationPort(Protocol):
    def classify(self, candidate: QueueCandidate) -> PlaybookMatch: ...


class OwnershipPort(Protocol):
    def ensure_jason_ownership(self, candidate: QueueCandidate, playbook_id: str) -> None: ...


class InvestigationPort(Protocol):
    def investigate(self, candidate: QueueCandidate, match: PlaybookMatch) -> WorkStepResult: ...


class ExecutionPort(Protocol):
    def execute(self, candidate: QueueCandidate, match: PlaybookMatch) -> WorkStepResult: ...


class AuditPort(Protocol):
    def record(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


class WakeSchedulerPort(Protocol):
    def schedule(self, wake: TargetedWake) -> None: ...


class AutonomousQueueWorker:
    """One bounded scheduling/execution cycle.

    The hosting runtime decides when to invoke a cycle. Known waiting work is
    resumed by targeted wakeups rather than forcing broad queue scans.
    """

    def __init__(
        self,
        *,
        config: AutonomyConfig,
        ledger: WorkLedger,
        attention: QueueAttentionState,
        scheduler: AttentionScheduler,
        queue_source: QueueSourcePort,
        classifier: PlaybookClassificationPort,
        ownership: OwnershipPort,
        investigation: InvestigationPort,
        execution: ExecutionPort,
        audit: AuditPort,
        wake_scheduler: WakeSchedulerPort | None = None,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.attention = attention
        self.scheduler = scheduler
        self.queue_source = queue_source
        self.classifier = classifier
        self.ownership = ownership
        self.investigation = investigation
        self.execution = execution
        self.audit = audit
        self.wake_scheduler = wake_scheduler
        self._candidates: dict[str, QueueCandidate] = {}

    def cycle(
        self,
        *,
        urgent_event: bool = False,
        explicitly_requested: bool = False,
        now: datetime | None = None,
    ) -> WorkerCycleResult:
        now = now or datetime.now(timezone.utc)
        decision = self.scheduler.should_reconcile(
            self.attention,
            capacity_available=self.ledger.available_slots(self.config) > 0,
            urgent_event=urgent_event,
            explicitly_requested=explicitly_requested,
            now=now,
        )
        reconciled = False
        if decision.should_reconcile:
            self._reconcile(now=now)
            reconciled = True

        activated = self.ledger.activate_next(self.config, now=now)
        investigated: list[str] = []
        executed: list[str] = []
        blocked: list[str] = []

        for item in activated:
            candidate = self._candidates.get(item.resource_id)
            if candidate is None:
                self._persist_result(
                    item,
                    WorkStepResult(WorkState.BLOCKED, "Candidate context unavailable after activation."),
                    now=now,
                )
                blocked.append(item.resource_id)
                continue

            match = self.classifier.classify(candidate)
            self.audit.record(
                "autonomy.playbook.match",
                {
                    "resource_id": item.resource_id,
                    "playbook_id": match.playbook_id,
                    "match_state": match.state.value,
                    "standing_authority_active": match.standing_authority_active,
                    "reasons": list(match.reasons),
                },
            )

            if match.state == MatchState.MATCHED_AUTONOMY:
                self.ownership.ensure_jason_ownership(candidate, match.playbook_id)
                result = self.execution.execute(candidate, match)
                self._persist_result(item, result, now=now, playbook_id=match.playbook_id)
                executed.append(item.resource_id)
                continue

            if match.state == MatchState.CANDIDATE_INVESTIGATION:
                result = self.investigation.investigate(candidate, match)
                self._persist_result(item, result, now=now, playbook_id=match.playbook_id)
                investigated.append(item.resource_id)
                continue

            reason = "; ".join(match.reasons) or "Playbook did not qualify."
            terminal_state = (
                WorkState.BLOCKED
                if match.state == MatchState.CONFLICT_BLOCKED
                else WorkState.CANDIDATE
            )
            self._persist_result(
                item,
                WorkStepResult(terminal_state, reason),
                now=now,
                playbook_id=match.playbook_id,
            )
            if terminal_state == WorkState.BLOCKED:
                blocked.append(item.resource_id)

        return WorkerCycleResult(
            reconciled=reconciled,
            reconcile_reason=decision.reason,
            activated=tuple(item.resource_id for item in activated),
            investigated=tuple(investigated),
            executed=tuple(executed),
            blocked=tuple(blocked),
        )

    def _reconcile(self, *, now: datetime) -> None:
        candidates = tuple(self.queue_source.reconcile_candidates())
        current_ids = {candidate.resource_id for candidate in candidates}
        self._candidates = {candidate.resource_id: candidate for candidate in candidates}

        for candidate in candidates:
            existing = self.ledger.get(candidate.resource_id)
            if (
                existing
                and existing.source_version is not None
                and candidate.source_version is not None
                and existing.source_version == candidate.source_version
            ):
                continue
            self.ledger.upsert(
                WorkItem(
                    resource_id=candidate.resource_id,
                    state=WorkState.CANDIDATE,
                    priority=candidate.priority,
                    owned_by_jason=candidate.owned_by_jason,
                    urgent=candidate.urgent,
                    reason=f"Queue candidate from {candidate.source_queue}",
                    source_version=candidate.source_version,
                    updated_at=now,
                )
            )

        for item in self.ledger.items():
            if (
                item.resource_id not in current_ids
                and item.state in {WorkState.AVAILABLE, WorkState.CANDIDATE}
            ):
                self.ledger.upsert(
                    replace(
                        item,
                        state=WorkState.BLOCKED,
                        reason="Candidate no longer present in eligible queue view.",
                        updated_at=now,
                    )
                )

        reasons = self.attention.mark_reconciled(now=now)
        self.audit.record(
            "autonomy.queue.reconciled",
            {
                "candidate_count": len(candidates),
                "wake_reasons": list(reasons),
                "max_active_work_items": self.config.max_active_work_items,
            },
        )

    def _persist_result(
        self,
        item: WorkItem,
        result: WorkStepResult,
        *,
        now: datetime,
        playbook_id: str | None = None,
    ) -> None:
        effective_playbook_id = playbook_id or item.playbook_id
        next_check_at = result.next_check_at
        wake_on = result.wake_on
        queue_reconciliation_required = result.queue_reconciliation_required

        if result.recheck is not None:
            if self.wake_scheduler is None:
                raise RuntimeError(
                    "structured playbook recheck requires a configured wake scheduler"
                )
            wake = result.recheck.to_wake(
                resource_id=item.resource_id,
                playbook_id=effective_playbook_id or "unclassified",
                reason=result.reason,
            )
            self.wake_scheduler.schedule(wake)
            next_check_at = result.recheck.due_at
            wake_on = result.recheck.wake_on
            queue_reconciliation_required = (
                result.recheck.queue_reconciliation_required
            )
            self.audit.record(
                "autonomy.work.recheck_scheduled",
                {
                    "resource_id": item.resource_id,
                    "playbook_id": effective_playbook_id,
                    "wake_id": wake.wake_id,
                    "capability_name": wake.capability_name,
                    "due_at": (
                        wake.due_at.isoformat()
                        if wake.due_at is not None
                        else None
                    ),
                    "wake_on": wake.wake_on,
                    "queue_reconciliation_required": (
                        wake.queue_reconciliation_required
                    ),
                },
            )

        updated = replace(
            item,
            state=result.state,
            playbook_id=effective_playbook_id,
            next_action=result.next_action,
            next_check_at=next_check_at,
            wake_on=wake_on,
            queue_reconciliation_required=queue_reconciliation_required,
            reason=result.reason,
            source_version=item.source_version,
            updated_at=now,
        )
        self.ledger.upsert(updated)
        if result.queue_reconciliation_required:
            self.attention.mark_dirty("work_capacity_or_queue_state_changed")
        self.audit.record(
            "autonomy.work.state_changed",
            {
                "resource_id": updated.resource_id,
                "state": updated.state.value,
                "playbook_id": updated.playbook_id,
                "reason": updated.reason,
                "next_action": updated.next_action,
                "wake_on": updated.wake_on,
                "queue_reconciliation_required": updated.queue_reconciliation_required,
            },
        )
