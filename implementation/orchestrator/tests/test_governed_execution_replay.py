from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest, OrchestrationStatus
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan
from orchestrator.service import CentralOrchestrator, InvocationResult


class Resolution:
    def resolve(self, request):
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version="1.0.0",
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=("resolved",),
            eligible_provider_ids=("provider-1",),
            selected_provider_id="provider-1",
        )


class Invoker:
    def __init__(self):
        self.calls = 0

    def _prepared(self, *, request, resolution):
        ticket_id = request.arguments.get("ticket_id") or request.arguments.get("payload", {}).get("id") or 1
        payload = dict(request.arguments.get("payload") or request.arguments)
        return PreparedExecutionPlan(
            ExecutionPlan(
                principal_id=request.principal_id, organization_id=request.organization_id,
                client_id=request.client_id, canonical_capability=request.capability_name,
                selected_provider_id=resolution.selected_provider_id,
                provider_capability="autotask.ticket.note.create", action_method="POST",
                resource_type="service_ticket_note", resource_identifier=f"ticket:{ticket_id}",
                normalized_path="/V1.0/TicketNotes", normalized_payload=payload,
            )
        )

    def prepare_execution_plan(self, *, request, resolution):
        return self._prepared(request=request, resolution=resolution)

    def invoke_execution_plan(self, *, request, resolution, prepared):
        self.calls += 1
        return InvocationResult(output={"data": {"itemId": 30509999}}, attempts=1)

    def invoke(self, *, request, resolution):
        raise AssertionError("approval-governed mutation bypassed execution-plan invocation")


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


def make_request(*, execution_id, correlation_id, approval_id, idempotency_key, arguments):
    return OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.note.create",
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=True,
        risk="high",
        data_handling=DataHandlingPolicy(
            classification="internal", hosted_processing_allowed=False, retention_allowed=False
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("1.00"), maximum_attempts=1),
        arguments=arguments,
        requester_kind="human",
        permission_mode="execute",
        authority_context_id="ctx-1",
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )


def test_same_approved_action_is_consumed_once_and_replay_is_deduplicated(tmp_path):
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "governed.sqlite3"))
    ledger.initialize()
    arguments = {"ticket_id": 140000, "note": "SECURITY TEST — APPROVAL REPLAY TEST.", "title": ""}
    reservation = ledger.reserve_approval(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.note.create",
        arguments=arguments,
        request_id="authority-request-1",
    )
    same = ledger.reserve_approval(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.note.create",
        arguments=arguments,
        request_id="authority-request-2",
    )
    assert same.approval_id == reservation.approval_id
    assert same.idempotency_key == reservation.idempotency_key
    assert same.request_id == "authority-request-1"
    assert same.created is False

    invoker = Invoker()
    audit = Audit()
    orchestrator = CentralOrchestrator(
        resolution=Resolution(), invoker=invoker, audit=audit, governed_execution_ledger=ledger
    )
    first = orchestrator.execute(make_request(
        execution_id="exec-1", correlation_id="corr-1",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
        arguments=arguments,
    ))
    replay = orchestrator.execute(make_request(
        execution_id="exec-2", correlation_id="corr-2",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
        arguments=arguments,
    ))

    assert first.status is OrchestrationStatus.SUCCEEDED
    assert replay.status is OrchestrationStatus.SUCCEEDED
    assert invoker.calls == 1
    assert replay.output == first.output
    evidence = ledger.evidence(reservation.approval_id)
    assert evidence is not None
    assert evidence["state"] == "succeeded"
    assert evidence["execution_id"] == "exec-1"
    assert evidence["correlation_id"] == "corr-1"
    dedupe = [payload for event, payload in audit.events if event == "orchestration.idempotency.deduplicated"]
    assert len(dedupe) == 1
    assert dedupe[0]["approval_id"] == reservation.approval_id
    assert dedupe[0]["idempotency_key"] == reservation.idempotency_key
    assert dedupe[0]["action_fingerprint"] == reservation.action_fingerprint
    assert dedupe[0]["replay_result"] == "deduplicated"
    assert dedupe[0]["execution_id"] == "exec-2"
    assert dedupe[0]["correlation_id"] == "corr-2"


def test_approval_cannot_be_reused_with_changed_arguments(tmp_path):
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "governed.sqlite3"))
    ledger.initialize()
    arguments = {"ticket_id": 140000, "note": "approved", "title": ""}
    reservation = ledger.reserve_approval(
        principal_id="person-al", organization_id="aot", client_id=None,
        capability_name="service.ticket.note.create", arguments=arguments,
        request_id="authority-request-1",
    )
    invoker = Invoker()
    audit = Audit()
    orchestrator = CentralOrchestrator(
        resolution=Resolution(), invoker=invoker, audit=audit, governed_execution_ledger=ledger
    )
    changed = orchestrator.execute(make_request(
        execution_id="exec-1", correlation_id="corr-1",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
        arguments={"ticket_id": 140000, "note": "different", "title": ""},
    ))
    assert changed.status is OrchestrationStatus.DENIED
    assert changed.error_code == "APPROVAL_CONSUMPTION_REJECTED"
    assert invoker.calls == 0


def test_initialize_migrates_pre_request_id_schema(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE governed_action_approvals (
          approval_id TEXT PRIMARY KEY, action_fingerprint TEXT NOT NULL UNIQUE,
          idempotency_key TEXT NOT NULL UNIQUE, principal_id TEXT NOT NULL,
          organization_id TEXT NOT NULL, client_id TEXT, capability_name TEXT NOT NULL,
          state TEXT NOT NULL, execution_id TEXT, correlation_id TEXT, result_json TEXT,
          created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT, completed_at TEXT
        );
        """)
    ledger = SQLiteGovernedExecutionLedger(str(path))
    ledger.initialize()
    with sqlite3.connect(path) as c:
        columns = {row[1] for row in c.execute("PRAGMA table_info(governed_action_approvals)")}
    assert {
        "request_id", "intent_fingerprint", "execution_plan_fingerprint",
        "execution_plan_json", "failure_reason",
    } <= columns
    reservation = ledger.reserve_approval(
        principal_id="person-al", organization_id="aot", client_id=None,
        capability_name="service.ticket.note.create",
        arguments={"ticket_id": 1, "note": "x", "title": ""},
        request_id="authority-request-migrated",
    )
    assert reservation.request_id == "authority-request-migrated"
