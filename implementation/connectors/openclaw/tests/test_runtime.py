from __future__ import annotations

from pathlib import Path

from jason_openclaw.models import CapabilityRequest
from jason_openclaw.runtime import (
    GateChainPolicyEvaluator,
    JasonAuthorityEvaluator,
    OpenClawOrchestratorDispatcher,
    SQLiteReplayStore,
)
from orchestrator import OrchestrationStatus
from orchestrator.gates import (
    GateDecision,
    GateOutcome,
    GovernanceGateChain,
)


class AuthorityService:
    def __init__(self, decision="allowed"):
        self.decision = decision
        self.calls = []

    def evaluate(self, **kwargs):
        self.calls.append(kwargs)
        return self.decision


class Gate:
    name = "security"

    def __init__(self, outcome=GateOutcome.ALLOW):
        self.outcome = outcome

    def evaluate(self, context):
        return GateDecision(
            gate=self.name,
            outcome=self.outcome,
            reason_code="synthetic",
        )


class Result:
    execution_id = "exec-1"
    status = OrchestrationStatus.SUCCEEDED
    reason_codes = ("capability_completed",)
    provider_id = "synthetic-provider"
    output = {"ok": True}
    artifact_references = ()


class Orchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return Result()


def request(capability="autotask.ticket.get"):
    return CapabilityRequest.from_payload(
        {
            "request_id": "req-runtime-1",
            "correlation_id": "corr-runtime-1",
            "capability": capability,
            "requested_mode": "observe",
            "arguments": {"ticket_id": "12445279"},
            "principal": {
                "principal_id": "person-al",
                "channel": "teams",
                "external_user_id": "openclaw-user-1",
                "organization_id": "aot",
                "client_id": "client-jbf",
                "authentication_assurance": "machine_authenticated",
            },
        }
    )


def test_authority_adapter_preserves_identity_scope_and_fails_closed():
    service = AuthorityService("unexpected")
    evaluator = JasonAuthorityEvaluator(service)

    assert evaluator.evaluate(request()) == "denied"
    assert service.calls[0]["principal_id"] == "person-al"
    assert service.calls[0]["organization_id"] == "aot"
    assert service.calls[0]["client_id"] == "client-jbf"
    assert service.calls[0]["capability"] == "autotask.ticket.get"


def test_gate_chain_adapter_returns_approval_required():
    evaluator = GateChainPolicyEvaluator(
        GovernanceGateChain([Gate(GateOutcome.APPROVAL_REQUIRED)])
    )
    assert evaluator.evaluate(request()) == "approval_required"


def test_dispatcher_builds_real_orchestration_request_without_self_approval():
    orchestrator = Orchestrator()
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={"autotask.ticket.get": "1.0"},
    )

    result = dispatcher.dispatch(request())

    assert result["status"] == "succeeded"
    submitted = orchestrator.requests[0]
    assert submitted.principal_id == "person-al"
    assert submitted.organization_id == "aot"
    assert submitted.client_id == "client-jbf"
    assert submitted.capability_name == "autotask.ticket.get"
    assert submitted.capability_version == "1.0"
    assert submitted.authority_allowed is True
    assert submitted.approval_present is False
    assert submitted.requester_kind == "service"
    assert submitted.data_handling.hosted_processing_allowed is False
    assert submitted.budget.maximum_attempts == 1


def test_unknown_capability_fails_before_orchestrator_dispatch():
    orchestrator = Orchestrator()
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={"autotask.ticket.get": "1.0"},
    )

    try:
        dispatcher.dispatch(request("datto_rmm.device.delete"))
    except KeyError:
        pass
    else:
        raise AssertionError("unknown capability should fail closed")

    assert orchestrator.requests == []


def test_sqlite_replay_store_survives_new_instance(tmp_path: Path):
    database = tmp_path / "openclaw-replay.sqlite3"
    first = SQLiteReplayStore(database)
    assert first.claim("req-persisted-1") is True
    assert first.claim("req-persisted-1") is False

    second = SQLiteReplayStore(database)
    assert second.claim("req-persisted-1") is False
    assert second.claim("req-persisted-2") is True
