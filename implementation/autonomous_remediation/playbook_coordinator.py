"""Provider-neutral coordinator for durable Jason playbook runs.

The coordinator binds the generic PlaybookRun store to orchestration milestones.
It does not invoke providers and does not grant action authority. Callers execute
reads/actions through Jason's existing governed paths, then record the resulting
state/evidence here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from playbook_runtime import FilePlaybookRunStore, PlaybookRunRecord, RunState, TERMINAL_STATES


@dataclass(frozen=True, slots=True)
class PlaybookIdentity:
    playbook_id: str
    version: str


@dataclass(frozen=True, slots=True)
class PlaybookRunCoordinator:
    store: FilePlaybookRunStore

    def ensure_run(
        self,
        *,
        identity: PlaybookIdentity,
        run_id: str,
        ticket_id: str,
        company_id: str,
        device_id: str = "",
        trigger_class: str = "unknown",
    ) -> PlaybookRunRecord:
        active = self._matching_active(
            playbook_id=identity.playbook_id,
            ticket_id=ticket_id,
            company_id=company_id,
            device_id=device_id,
        )
        if len(active) > 1:
            raise ValueError("multiple active playbook runs match one work item")
        if active:
            existing = active[0]
            if existing.playbook_version != identity.version:
                raise ValueError("active playbook run version mismatch")
            return existing
        record = PlaybookRunRecord(
            run_id=run_id,
            playbook_id=identity.playbook_id,
            playbook_version=identity.version,
            ticket_id=ticket_id,
            company_id=company_id,
            device_id=device_id,
            trigger_class=trigger_class,
        )
        self.store.create(record)
        return record

    def transition(
        self,
        run: PlaybookRunRecord,
        target: RunState,
        *,
        reason_class: str = "",
    ) -> PlaybookRunRecord:
        run.transition(target, reason_class=reason_class)
        self.store.save(run)
        return run

    def record_observation(
        self,
        run: PlaybookRunRecord,
        *,
        step: str,
        result: str,
        evidence_refs: Iterable[str] = (),
        summary: str = "",
    ) -> PlaybookRunRecord:
        run.record_step(
            step,
            result,
            evidence_refs=tuple(evidence_refs),
            summary=summary,
        )
        self.store.save(run)
        return run

    def require_approval(self, run: PlaybookRunRecord, *, approval_id: str) -> PlaybookRunRecord:
        run.require_approval(approval_id)
        self.store.save(run)
        return run

    def approve(self, run: PlaybookRunRecord, *, approval_id: str) -> PlaybookRunRecord:
        run.approve(approval_id)
        self.store.save(run)
        return run

    def record_governed_action_result(
        self,
        run: PlaybookRunRecord,
        *,
        step: str,
        status: str,
        correlation_id: str = "",
        job_id: str = "",
        summary: str = "",
    ) -> PlaybookRunRecord:
        refs = tuple(ref for ref in (correlation_id, job_id) if ref)
        run.record_step(step, status, evidence_refs=refs, summary=summary)
        if status in {"submitted", "succeeded", "completed"}:
            run.increment_attempt()
        self.store.save(run)
        return run

    def schedule_recheck(self, run: PlaybookRunRecord, *, when: str) -> PlaybookRunRecord:
        run.schedule_recheck(when)
        self.store.save(run)
        return run

    def _matching_active(
        self,
        *,
        playbook_id: str,
        ticket_id: str,
        company_id: str,
        device_id: str,
    ) -> list[PlaybookRunRecord]:
        matches = []
        for record in self.store.list():
            if record.state in TERMINAL_STATES:
                continue
            if record.playbook_id != playbook_id:
                continue
            if record.ticket_id != ticket_id or record.company_id != company_id:
                continue
            if device_id and record.device_id and record.device_id != device_id:
                continue
            matches.append(record)
        return matches


class GovernedOrchestratorProtocol:
    def execute(self, request): ...


@dataclass(frozen=True, slots=True)
class GovernedPlaybookExecutor:
    """Execute through the existing Central Orchestrator, then persist the result."""

    orchestrator: object
    coordinator: PlaybookRunCoordinator

    def execute(
        self,
        run: PlaybookRunRecord,
        *,
        step: str,
        request: object,
        success_state: RunState | None = None,
    ):
        execute = getattr(self.orchestrator, "execute", None)
        if not callable(execute):
            raise ValueError("governed orchestrator execute method is required")
        if success_state is not None and not run.can_transition(success_state):
            raise ValueError("invalid playbook success transition")
        result = execute(request)
        status_obj = getattr(result, "status", "")
        status = str(getattr(status_obj, "value", status_obj)).strip().lower()
        correlation_id = str(getattr(result, "correlation_id", "")).strip()
        attempts = getattr(result, "attempts", 0)
        reason_codes = tuple(str(x) for x in getattr(result, "reason_codes", ()) if str(x))
        summary = ",".join(reason_codes[:6])

        # Persist the observed governed result. Do not reinterpret denial or
        # approval-required as provider success, and do not retry here.
        run.record_step(
            step,
            status or "unknown",
            evidence_refs=((correlation_id,) if correlation_id else ()),
            summary=summary,
        )
        if isinstance(attempts, int) and attempts > 0:
            run.attempt_count += attempts
        if status == "approval_required":
            run.transition(RunState.BLOCKED, reason_class="approval_required")
        elif status in {"denied", "human_required"}:
            run.transition(RunState.BLOCKED, reason_class="authority_or_human_required")
        elif status == "failed":
            run.transition(RunState.BLOCKED, reason_class="governed_action_failed")
        elif status == "succeeded" and success_state is not None:
            run.transition(success_state)
        self.coordinator.store.save(run)
        return result
