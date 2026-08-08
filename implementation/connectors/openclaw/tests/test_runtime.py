from __future__ import annotations

from pathlib import Path

from kernel.identity_authority import AuthorityDecision, AuthorityOutcome, ExecutionContext, PermissionMode
from jason_openclaw.models import CapabilityRequest
from jason_openclaw.runtime import (
    GateChainPolicyEvaluator,
    JasonAuthorityEvaluator,
    OpenClawOrchestratorDispatcher,
    SQLiteReplayStore,
)
from orchestrator import OrchestrationStatus
from orchestrator.gates import GateDecision, GateOutcome, GovernanceGateChain


class AuthorityService:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def evaluate(self, request):
        self.calls.append(request)
        return self.decision


class Gate:
    name = "security"

    def __init__(self, outcome=GateOutcome.ALLOW):
        self.outcome = outcome

    def evaluate(self, context):
        return GateDecision(gate=self.name, outcome=self.outcome, reason_code="synthetic")


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


def allowed_decision():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    context = ExecutionContext(
        context_id="ctx-openclaw-1",
        correlation_id="corr-runtime-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-jbf",
        capability="autotask.ticket.get",
        requested_mode=PermissionMode.OBSERVE,
        maximum_mode=PermissionMode.OBSERVE,
        outcome=AuthorityOutcome.ALLOWED,
        approval_required=False,
        matched_grants=("grant-1",),
        authentication_assurance="machine_authenticated",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    return AuthorityDecision(
        outcome=AuthorityOutcome.ALLOWED,
        reason_codes=("AUTHORITY_ALLOWED",),
        maximum_mode=PermissionMode.OBSERVE,
        matched_grants=("grant-1",),
        execution_context=context,
    )


def test_authority_adapter_preserves_identity_scope_and_caches_issued_context():
    service = AuthorityService(allowed_decision())
    evaluator = JasonAuthorityEvaluator(service)

    assert evaluator.evaluate(request()) == "allowed"
    submitted = service.calls[0]
    assert submitted.principal_id == "person-al"
    assert submitted.organization_id == "aot"
    assert submitted.client_id == "client-jbf"
    assert submitted.capability == "autotask.ticket.get"
    assert evaluator.context_id_for("req-runtime-1") == "ctx-openclaw-1"


def test_gate_chain_adapter_returns_approval_required():
    evaluator = GateChainPolicyEvaluator(GovernanceGateChain([Gate(GateOutcome.APPROVAL_REQUIRED)]))
    assert evaluator.evaluate(request()) == "approval_required"


def test_dispatcher_passes_issued_context_and_never_self_approves():
    orchestrator = Orchestrator()
    evaluator = JasonAuthorityEvaluator(AuthorityService(allowed_decision()))
    assert evaluator.evaluate(request()) == "allowed"
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={"autotask.ticket.get": "1.0"},
        authority_contexts=evaluator,
    )

    result = dispatcher.dispatch(request())

    assert result["status"] == "succeeded"
    submitted = orchestrator.requests[0]
    assert submitted.authority_context_id == "ctx-openclaw-1"
    assert submitted.approval_present is False
    assert submitted.requester_kind == "service"


def test_dispatcher_fails_closed_when_no_context_was_issued():
    orchestrator = Orchestrator()
    evaluator = JasonAuthorityEvaluator(
        AuthorityService(AuthorityDecision(AuthorityOutcome.DENIED, ("NO_GRANT",)))
    )
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={"autotask.ticket.get": "1.0"},
        authority_contexts=evaluator,
    )
    try:
        dispatcher.dispatch(request())
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing authority context must fail closed")
    assert orchestrator.requests == []


def test_unknown_capability_fails_before_orchestrator_dispatch():
    orchestrator = Orchestrator()
    evaluator = JasonAuthorityEvaluator(AuthorityService(allowed_decision()))
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={"autotask.ticket.get": "1.0"},
        authority_contexts=evaluator,
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
