from __future__ import annotations

from dataclasses import dataclass

from orchestrator.gates import (
    GateContext,
    GateDecision,
    GateOutcome,
    GovernanceGateChain,
)


@dataclass
class Gate:
    name: str
    outcome: GateOutcome

    def evaluate(self, context):
        return GateDecision(
            gate=self.name,
            outcome=self.outcome,
            reason_code=f"{self.name}_{self.outcome.value}",
            evidence={"capability": context.capability},
        )


def context():
    return GateContext(
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        capability="autotask.ticket.get",
        requested_mode="observe",
    )


def test_all_gates_allow():
    chain = GovernanceGateChain([
        Gate("security", GateOutcome.ALLOW),
        Gate("compliance", GateOutcome.ALLOW),
    ])
    result = chain.evaluate(context())
    assert result.outcome is GateOutcome.ALLOW
    assert [d.gate for d in result.decisions] == ["security", "compliance"]


def test_deny_stops_later_gates():
    chain = GovernanceGateChain([
        Gate("security", GateOutcome.ALLOW),
        Gate("privacy", GateOutcome.DENY),
        Gate("communications", GateOutcome.ALLOW),
    ])
    result = chain.evaluate(context())
    assert result.outcome is GateOutcome.DENY
    assert [d.gate for d in result.decisions] == ["security", "privacy"]


def test_approval_required_survives_later_allows():
    chain = GovernanceGateChain([
        Gate("business_authority", GateOutcome.APPROVAL_REQUIRED),
        Gate("rollback_reversibility", GateOutcome.ALLOW),
    ])
    result = chain.evaluate(context())
    assert result.outcome is GateOutcome.APPROVAL_REQUIRED


def test_duplicate_gate_names_are_rejected():
    try:
        GovernanceGateChain([
            Gate("security", GateOutcome.ALLOW),
            Gate("security", GateOutcome.ALLOW),
        ])
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate gate names must fail closed")
