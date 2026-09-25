from datetime import datetime, timezone

from .attention_scheduler import AttentionScheduler, AutonomyConfig, QueueAttentionState, WorkLedger, WorkState
from .autonomous_queue_worker import AutonomousQueueWorker, QueueCandidate, WorkStepResult
from .playbook_matching import EligibilityGate, GateState, PlaybookMatcher


class QueueSource:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def reconcile_candidates(self):
        self.calls += 1
        return self.candidates


class Classifier:
    def __init__(self, states):
        self.states = states

    def classify(self, candidate):
        state = self.states[candidate.resource_id]
        gates = [
            EligibilityGate("trigger", GateState.PASS),
            EligibilityGate("identity", GateState.PASS, blocking_on_fail=True),
            EligibilityGate("autonomy_approved", GateState.PASS, blocking_on_fail=True),
        ]
        if state == "matched":
            return PlaybookMatcher.evaluate(playbook_id="pb", gates=gates)
        if state == "candidate":
            return PlaybookMatcher.evaluate(
                playbook_id="pb",
                gates=gates + [EligibilityGate("evidence", GateState.UNKNOWN)],
            )
        if state == "conflict":
            return PlaybookMatcher.evaluate(
                playbook_id="pb",
                gates=[
                    EligibilityGate("trigger", GateState.PASS),
                    EligibilityGate("identity", GateState.FAIL, "ambiguous target", True),
                    EligibilityGate("autonomy_approved", GateState.PASS, True),
                ],
            )
        return PlaybookMatcher.evaluate(
            playbook_id="pb",
            gates=[EligibilityGate("trigger", GateState.FAIL)],
        )


class Ownership:
    def __init__(self):
        self.claimed = []

    def ensure_jason_ownership(self, candidate, playbook_id):
        self.claimed.append(candidate.resource_id)


class Investigation:
    def __init__(self):
        self.calls = []

    def investigate(self, candidate, match):
        self.calls.append(candidate.resource_id)
        return WorkStepResult(
            WorkState.WAITING,
            "Need more evidence",
            next_action="Targeted evidence read",
            wake_on="evidence_available",
        )


class Execution:
    def __init__(self):
        self.calls = []

    def execute(self, candidate, match):
        self.calls.append(candidate.resource_id)
        return WorkStepResult(
            WorkState.COMPLETE,
            "Verified complete",
            queue_reconciliation_required=True,
        )


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload):
        self.events.append((event_type, payload))


def build(candidates, states, *, limit=2):
    source = QueueSource(candidates)
    ownership = Ownership()
    investigation = Investigation()
    execution = Execution()
    audit = Audit()
    attention = QueueAttentionState(dirty=True, reasons={"ticket_entered"})
    worker = AutonomousQueueWorker(
        config=AutonomyConfig(limit),
        ledger=WorkLedger(),
        attention=attention,
        scheduler=AttentionScheduler(),
        queue_source=source,
        classifier=Classifier(states),
        ownership=ownership,
        investigation=investigation,
        execution=execution,
        audit=audit,
    )
    return worker, source, ownership, investigation, execution, audit


def test_cycle_works_only_two_highest_priority_candidates():
    worker, source, ownership, investigation, execution, audit = build(
        [
            QueueCandidate("T1", 10, "Help Desk I"),
            QueueCandidate("T2", 20, "Jason", owned_by_jason=True),
            QueueCandidate("T3", 5, "Monitoring Alert"),
        ],
        {"T1": "matched", "T2": "matched", "T3": "matched"},
    )
    result = worker.cycle(now=datetime.now(timezone.utc))
    assert result.activated == ("T2", "T1")
    assert execution.calls == ["T2", "T1"]
    assert ownership.claimed == ["T2", "T1"]
    assert worker.ledger.get("T3").state == WorkState.CANDIDATE


def test_candidate_investigation_does_not_claim_ticket():
    worker, source, ownership, investigation, execution, audit = build(
        [QueueCandidate("T1", 10, "Help Desk I")],
        {"T1": "candidate"},
    )
    result = worker.cycle(now=datetime.now(timezone.utc))
    assert result.investigated == ("T1",)
    assert ownership.claimed == []
    assert execution.calls == []
    assert worker.ledger.get("T1").state == WorkState.WAITING


def test_conflict_fails_closed_without_claim_or_execution():
    worker, source, ownership, investigation, execution, audit = build(
        [QueueCandidate("T1", 10, "Help Desk I")],
        {"T1": "conflict"},
    )
    result = worker.cycle(now=datetime.now(timezone.utc))
    assert result.blocked == ("T1",)
    assert ownership.claimed == []
    assert execution.calls == []
    assert worker.ledger.get("T1").state == WorkState.BLOCKED


def test_completed_work_marks_queue_dirty_to_fill_freed_slot():
    worker, source, ownership, investigation, execution, audit = build(
        [QueueCandidate("T1", 10, "Jason", owned_by_jason=True)],
        {"T1": "matched"},
    )
    worker.cycle(now=datetime.now(timezone.utc))
    assert worker.attention.dirty
    assert "work_capacity_or_queue_state_changed" in worker.attention.reasons


def test_audit_explains_reconciliation_match_and_state_change():
    worker, source, ownership, investigation, execution, audit = build(
        [QueueCandidate("T1", 10, "Jason", owned_by_jason=True)],
        {"T1": "matched"},
    )
    worker.cycle(now=datetime.now(timezone.utc))
    event_types = [name for name, _ in audit.events]
    assert "autonomy.queue.reconciled" in event_types
    assert "autonomy.playbook.match" in event_types
    assert "autonomy.work.state_changed" in event_types
