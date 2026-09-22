"""Generic persisted state for governed Jason playbook runs.

This module stores orchestration state only. It grants no provider authority,
performs no provider calls, and contains no remediation logic. Playbook-specific
code may use it to survive restarts, rechecks, approvals, and handoffs without
repeating completed work.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class RunState(str, Enum):
    TRIGGERED = "triggered"
    IDENTIFYING = "identifying"
    DIAGNOSING = "diagnosing"
    DECIDING = "deciding"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    WAITING = "waiting"
    RECHECK_PENDING = "recheck_pending"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset({RunState.COMPLETE, RunState.ESCALATED, RunState.CANCELLED})

_ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.TRIGGERED: frozenset({RunState.IDENTIFYING, RunState.BLOCKED, RunState.CANCELLED}),
    RunState.IDENTIFYING: frozenset({RunState.DIAGNOSING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.DIAGNOSING: frozenset({RunState.DECIDING, RunState.WAITING, RunState.RECHECK_PENDING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.DECIDING: frozenset({RunState.AWAITING_APPROVAL, RunState.REMEDIATING, RunState.VERIFYING, RunState.WAITING, RunState.BLOCKED, RunState.ESCALATED, RunState.COMPLETE, RunState.CANCELLED}),
    RunState.AWAITING_APPROVAL: frozenset({RunState.REMEDIATING, RunState.DIAGNOSING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.REMEDIATING: frozenset({RunState.VERIFYING, RunState.WAITING, RunState.RECHECK_PENDING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.VERIFYING: frozenset({RunState.COMPLETE, RunState.DIAGNOSING, RunState.REMEDIATING, RunState.RECHECK_PENDING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.WAITING: frozenset({RunState.DIAGNOSING, RunState.VERIFYING, RunState.RECHECK_PENDING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.RECHECK_PENDING: frozenset({RunState.DIAGNOSING, RunState.VERIFYING, RunState.BLOCKED, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.BLOCKED: frozenset({RunState.IDENTIFYING, RunState.DIAGNOSING, RunState.DECIDING, RunState.REMEDIATING, RunState.VERIFYING, RunState.ESCALATED, RunState.CANCELLED}),
    RunState.COMPLETE: frozenset(),
    RunState.ESCALATED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RunStep:
    name: str
    status: str
    recorded_at: str
    evidence_refs: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class PlaybookRunRecord:
    run_id: str
    playbook_id: str
    playbook_version: str
    ticket_id: str
    company_id: str
    device_id: str = ""
    state: RunState = RunState.TRIGGERED
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    trigger_class: str = "unknown"
    approval_status: str = "not_required"
    approval_id: str = ""
    blocked_reason_class: str = ""
    recheck_at: str = ""
    attempt_count: int = 0
    verification_status: str = "pending"
    outcome: str = "in_progress"
    completed_steps: list[RunStep] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.playbook_id.strip() or not self.playbook_version.strip():
            raise ValueError("run identity is required")
        if not self.ticket_id.strip() or not self.company_id.strip():
            raise ValueError("ticket and company boundary are required")
        if self.attempt_count < 0:
            raise ValueError("attempt count must be non-negative")
        if not isinstance(self.state, RunState):
            self.state = RunState(str(self.state))

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def can_transition(self, target: RunState) -> bool:
        return target == self.state or target in _ALLOWED_TRANSITIONS[self.state]

    def transition(self, target: RunState, *, reason_class: str = "") -> None:
        if target == self.state:
            return
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid playbook transition: {self.state.value}->{target.value}")
        self.state = target
        self.updated_at = _now()
        if target == RunState.AWAITING_APPROVAL:
            self.approval_status = "pending"
        if target == RunState.BLOCKED:
            self.blocked_reason_class = reason_class or "unspecified"
        elif self.blocked_reason_class and target != RunState.ESCALATED:
            self.blocked_reason_class = ""
        if target == RunState.COMPLETE:
            self.outcome = "resolved"
        elif target == RunState.ESCALATED:
            self.outcome = "escalated"
        elif target == RunState.CANCELLED:
            self.outcome = "cancelled"

    def record_step(self, name: str, status: str, *, summary: str = "", evidence_refs: tuple[str, ...] = ()) -> None:
        if self.terminal:
            raise ValueError("terminal playbook run cannot record new steps")
        if not name.strip() or not status.strip():
            raise ValueError("step name and status are required")
        refs = [str(ref) for ref in evidence_refs if str(ref).strip()]
        self.completed_steps.append(RunStep(name=name.strip(), status=status.strip(), recorded_at=_now(), evidence_refs=refs, summary=summary.strip()))
        for ref in refs:
            if ref not in self.evidence_refs:
                self.evidence_refs.append(ref)
        self.updated_at = _now()

    def require_approval(self, approval_id: str) -> None:
        if not approval_id.strip():
            raise ValueError("approval id is required")
        self.approval_id = approval_id.strip()
        self.transition(RunState.AWAITING_APPROVAL)

    def approve(self, approval_id: str) -> None:
        if self.state != RunState.AWAITING_APPROVAL or approval_id.strip() != self.approval_id:
            raise ValueError("approval does not match pending playbook approval")
        self.approval_status = "approved"
        self.updated_at = _now()

    def schedule_recheck(self, when: str) -> None:
        if not when.strip():
            raise ValueError("recheck timestamp is required")
        self.recheck_at = when.strip()
        self.transition(RunState.RECHECK_PENDING)

    def increment_attempt(self) -> None:
        if self.terminal:
            raise ValueError("terminal playbook run cannot increment attempts")
        self.attempt_count += 1
        self.updated_at = _now()


class FilePlaybookRunStore:
    """Atomic JSON-file persistence for one record per run."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or os.environ.get("JASON_PLAYBOOK_RUNS_PATH", "/var/lib/jason/playbooks/runs"))

    def _path(self, run_id: str) -> Path:
        if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in run_id):
            raise ValueError("invalid run id")
        return self.root / f"{run_id}.json"

    def create(self, record: PlaybookRunRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(record.run_id)
        if path.exists():
            raise ValueError("playbook run already exists")
        self.save(record)

    def save(self, record: PlaybookRunRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(record.run_id)
        payload = asdict(record)
        payload["state"] = record.state.value
        fd, temp_name = tempfile.mkstemp(prefix=f".{record.run_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try: os.unlink(temp_name)
            except FileNotFoundError: pass

    def load(self, run_id: str) -> PlaybookRunRecord:
        path = self._path(run_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["state"] = RunState(payload["state"])
        payload["completed_steps"] = [RunStep(**step) for step in payload.get("completed_steps", [])]
        return PlaybookRunRecord(**payload)

    def list(self) -> list[PlaybookRunRecord]:
        if not self.root.exists():
            return []
        records: list[PlaybookRunRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(self.load(path.stem))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return records
