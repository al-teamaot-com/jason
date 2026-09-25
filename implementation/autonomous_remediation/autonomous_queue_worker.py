"""Provider-neutral autonomous queue worker.

This module coordinates attention, matching, ownership and execution. It never
calls Autotask, DRMM or another provider directly; runtime adapters remain behind
Central Orchestrator governed capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
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
class WorkStepResult:
    state: WorkState
    reason: str
    next_action: str | None = None
    next_check_at: datetime | None = None
    wake_on: str | None = None
    queue_reconciliation_required: bool = False


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
        updated = replace(
            item,
            state=result.state,
            playbook_id=playbook_id or item.playbook_id,
            next_action=result.next_action,
            next_check_at=result.next_check_at,
            wake_on=result.wake_on,
            queue_reconciliation_required=result.queue_reconciliation_required,
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
