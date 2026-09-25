"""Deterministic eligibility gates for activating playbook standing authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class GateState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class MatchState(str, Enum):
    MATCHED_AUTONOMY = "matched_autonomy"
    CANDIDATE_INVESTIGATION = "candidate_investigation"
    NOT_MATCHED = "not_matched"
    CONFLICT_BLOCKED = "conflict_blocked"


@dataclass(frozen=True)
class EligibilityGate:
    name: str
    state: GateState
    detail: str = ""
    blocking_on_fail: bool = False


@dataclass(frozen=True)
class PlaybookMatch:
    playbook_id: str
    state: MatchState
    gates: tuple[EligibilityGate, ...]
    reasons: tuple[str, ...]

    @property
    def standing_authority_active(self) -> bool:
        return self.state == MatchState.MATCHED_AUTONOMY


class PlaybookMatcher:
    """Reasoning may nominate a playbook; deterministic gates activate authority."""

    TRIGGER_GATE = "trigger"
    AUTONOMY_GATE = "autonomy_approved"

    @classmethod
    def evaluate(
        cls,
        *,
        playbook_id: str,
        gates: Iterable[EligibilityGate],
    ) -> PlaybookMatch:
        gate_tuple = tuple(gates)
        by_name = {gate.name: gate for gate in gate_tuple}
        trigger = by_name.get(cls.TRIGGER_GATE)

        if trigger is None or trigger.state == GateState.FAIL:
            return PlaybookMatch(
                playbook_id,
                MatchState.NOT_MATCHED,
                gate_tuple,
                ("Playbook trigger did not match.",),
            )

        conflicts = tuple(
            gate for gate in gate_tuple
            if gate.state == GateState.FAIL and gate.blocking_on_fail
        )
        if conflicts:
            return PlaybookMatch(
                playbook_id,
                MatchState.CONFLICT_BLOCKED,
                gate_tuple,
                tuple(gate.detail or gate.name for gate in conflicts),
            )

        unresolved = tuple(
            gate for gate in gate_tuple
            if gate.state != GateState.PASS
        )
        if unresolved:
            return PlaybookMatch(
                playbook_id,
                MatchState.CANDIDATE_INVESTIGATION,
                gate_tuple,
                tuple(gate.detail or gate.name for gate in unresolved),
            )

        autonomy_gate = by_name.get(cls.AUTONOMY_GATE)
        if autonomy_gate is None:
            return PlaybookMatch(
                playbook_id,
                MatchState.CANDIDATE_INVESTIGATION,
                gate_tuple,
                ("Playbook is not explicitly approved for autonomous execution.",),
            )

        return PlaybookMatch(
            playbook_id,
            MatchState.MATCHED_AUTONOMY,
            gate_tuple,
            ("All deterministic eligibility gates passed.",),
        )
