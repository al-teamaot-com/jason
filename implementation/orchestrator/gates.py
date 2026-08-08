from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class GateOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True, slots=True)
class GateContext:
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    capability: str
    requested_mode: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GateDecision:
    gate: str
    outcome: GateOutcome
    reason_code: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


class GovernanceGate(Protocol):
    name: str

    def evaluate(self, context: GateContext) -> GateDecision: ...


@dataclass(frozen=True, slots=True)
class GateChainResult:
    outcome: GateOutcome
    decisions: tuple[GateDecision, ...]


class GovernanceGateChain:
    """Central deterministic gate chain.

    Gates evaluate facts/policy and return structured decisions. They do not
    invoke capabilities, providers, or other gates. The orchestrator owns order,
    routing, and the final allow/deny/approval-required result.
    """

    def __init__(self, gates: Sequence[GovernanceGate]) -> None:
        self._gates = tuple(gates)
        names = [gate.name for gate in self._gates]
        if len(names) != len(set(names)):
            raise ValueError("Governance gate names must be unique.")

    @property
    def gate_names(self) -> tuple[str, ...]:
        return tuple(gate.name for gate in self._gates)

    def evaluate(self, context: GateContext) -> GateChainResult:
        decisions: list[GateDecision] = []
        approval_required = False

        for gate in self._gates:
            decision = gate.evaluate(context)
            if decision.gate != gate.name:
                raise ValueError("Gate decision name does not match registered gate.")
            decisions.append(decision)

            if decision.outcome is GateOutcome.DENY:
                return GateChainResult(GateOutcome.DENY, tuple(decisions))
            if decision.outcome is GateOutcome.APPROVAL_REQUIRED:
                approval_required = True

        outcome = (
            GateOutcome.APPROVAL_REQUIRED
            if approval_required
            else GateOutcome.ALLOW
        )
        return GateChainResult(outcome, tuple(decisions))


CANONICAL_GOVERNANCE_GATES = (
    "security",
    "compliance",
    "privacy",
    "business_authority",
    "communications",
    "evidence_quality",
    "rollback_reversibility",
    "human_approval",
)
