from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest, OrchestrationStatus
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
from orchestrator.service import CentralOrchestrator, InvocationResult


class Resolution:
    def __init__(self, provider="provider-1"):
        self.provider = provider

    def resolve(self, request):
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version="1.0.0",
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=("resolved",),
            eligible_provider_ids=(self.provider,),
            selected_provider_id=self.provider,
        )


class Audit:
    def __init__(self): self.events = []
    def append(self, event_type, payload): self.events.append((event_type, dict(payload)))


class PlanInvoker:
    def __init__(self, plans):
        self.plans = list(plans)
        self.prepare_calls = 0
        self.provider_calls = 0

    def prepare_execution_plan(self, *, request, resolution):
        index = min(self.prepare_calls, len(self.plans) - 1)
        spec = dict(self.plans[index])
        self.prepare_calls += 1
        plan = ExecutionPlan(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            canonical_capability=request.capability_name,
            selected_provider_id=spec.get("provider", resolution.selected_provider_id),
            provider_capability=spec.get("provider_capability", "autotask.ticket.update"),
            action_method=spec.get("method", "PATCH"),
            resource_type=spec.get("resource_type", "service_ticket"),
            resource_identifier=spec.get("target", "140000"),
            normalized_path=spec.get("path", "/V1.0/Tickets"),
            normalized_payload=spec.get("payload", {"id": 140000, "queueID": 29682837, "status": 8}),
            material_parameters=spec.get("params", {}),
            symbolic_resolutions=spec.get("symbols", {
                "queueID": {"symbolic": "Jason", "resolved": 29682837},
                "status": {"symbolic": "In Progress", "resolved": 8},
            }),
        )
        return PreparedExecutionPlan(plan=plan, opaque={"prepared_index": index})

    def invoke_execution_plan(self, *, request, resolution, prepared):
        self.provider_calls += 1
        return InvocationResult(
            output={"provider_capability": prepared.plan.provider_capability, "data": {"id": 140000}},
            attempts=1,
        )

    def invoke(self, *, request, resolution):
        raise AssertionError("approved mutation bypassed execution-plan binding")


def make_request(*, execution_id, correlation_id, approval_id, idempotency_key):
    return OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.update",
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
        arguments={"ticket_id": 140000, "payload": {"queueID": "Jason", "status": "In Progress"}},
        requester_kind="human",
        permission_mode="execute",
        authority_context_id="ctx-1",
        idempotency_key=idempotency_key,
        approval_id=approval_id,
    )


def setup(tmp_path, plans):
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "governed.sqlite3")); ledger.initialize()
    arguments={"ticket_id": 140000, "payload": {"queueID": "Jason", "status": "In Progress"}}
    reservation=ledger.reserve_approval(
        principal_id="person-al", organization_id="aot", client_id=None,
        capability_name="service.ticket.update", arguments=arguments, request_id="authority-1",
    )
    invoker=PlanInvoker(plans); audit=Audit()
    orchestrator=CentralOrchestrator(
        resolution=Resolution(), invoker=invoker, audit=audit, governed_execution_ledger=ledger
    )
    request=make_request(
        execution_id="exec-1", correlation_id="corr-1",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
    )
    return ledger, reservation, invoker, audit, orchestrator, request


def test_same_intent_same_resolved_provider_mutation_allowed(tmp_path):
    ledger, reservation, invoker, audit, orchestrator, request = setup(tmp_path, [{}, {}])
    result=orchestrator.execute(request)
    assert result.status is OrchestrationStatus.SUCCEEDED
    assert invoker.provider_calls == 1
    evidence=ledger.evidence(reservation.approval_id)
    assert evidence["intent_fingerprint"] == reservation.intent_fingerprint
    assert evidence["execution_plan_fingerprint"]
    assert evidence["state"] == "succeeded"
    authorized=[p for e,p in audit.events if e=="orchestration.execution_plan.authorized"]
    assert len(authorized)==1
    symbols=authorized[0]["execution_plan"]["symbolic_resolutions"]
    assert symbols["queueID"] == {"symbolic":"Jason","resolved":29682837}
    assert symbols["status"] == {"symbolic":"In Progress","resolved":8}


def _assert_denied_zero_writes(tmp_path, first, second):
    ledger, reservation, invoker, audit, orchestrator, request = setup(tmp_path, [first, second])
    result=orchestrator.execute(request)
    assert result.status is OrchestrationStatus.DENIED
    assert result.error_code == "EXECUTION_PLAN_MISMATCH"
    assert invoker.provider_calls == 0
    evidence=ledger.evidence(reservation.approval_id)
    assert evidence["state"] == "failed"
    assert evidence["failure_reason"] == "execution_plan_mismatch"
    denied=[p for e,p in audit.events if e=="orchestration.execution_plan.denied"]
    assert len(denied)==1
    assert denied[0]["provider_invoked"] is False
    return denied[0]


def test_same_intent_changed_symbolic_mapping_denied_zero_provider_writes(tmp_path):
    first={}
    second={"payload":{"id":140000,"queueID":999999,"status":8},
            "symbols":{"queueID":{"symbolic":"Jason","resolved":999999},"status":{"symbolic":"In Progress","resolved":8}}}
    denied=_assert_denied_zero_writes(tmp_path, first, second)
    assert denied["authorized_execution_plan_fingerprint"] != denied["observed_execution_plan_fingerprint"]


def test_same_intent_changed_provider_denied_zero_provider_writes(tmp_path):
    _assert_denied_zero_writes(tmp_path, {}, {"provider":"provider-2"})


def test_same_intent_changed_target_resource_denied_zero_provider_writes(tmp_path):
    _assert_denied_zero_writes(tmp_path, {}, {"target":"140001","payload":{"id":140001,"queueID":29682837,"status":8}})


def test_same_intent_changed_normalized_payload_denied_zero_provider_writes(tmp_path):
    _assert_denied_zero_writes(tmp_path, {}, {"payload":{"id":140000,"queueID":29682837,"status":9}})


def test_exact_execution_retry_after_success_is_deduplicated(tmp_path):
    ledger, reservation, invoker, audit, orchestrator, request = setup(tmp_path, [{}, {}])
    first=orchestrator.execute(request)
    replay=orchestrator.execute(make_request(
        execution_id="exec-2", correlation_id="corr-2",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
    ))
    assert first.status is OrchestrationStatus.SUCCEEDED
    assert replay.status is OrchestrationStatus.SUCCEEDED
    assert replay.output == first.output
    assert invoker.provider_calls == 1
    assert invoker.prepare_calls == 2
    dedupe=[p for e,p in audit.events if e=="orchestration.idempotency.deduplicated"]
    assert len(dedupe)==1
    assert dedupe[0]["intent_fingerprint"] == reservation.intent_fingerprint
    assert dedupe[0]["execution_plan_fingerprint"]


def test_execution_plan_rejects_secret_material_and_absolute_provider_host():
    import pytest
    with pytest.raises(ValueError, match="secret material"):
        ExecutionPlan(
            principal_id="person-al", organization_id="aot", client_id=None,
            canonical_capability="service.ticket.update", selected_provider_id="provider-1",
            provider_capability="autotask.ticket.update", action_method="PATCH",
            resource_type="service_ticket", resource_identifier="140000",
            normalized_path="/V1.0/Tickets",
            normalized_payload={"id": 140000, "Authorization": "Bearer secret"},
        )
    with pytest.raises(ValueError, match="provider-relative"):
        ExecutionPlan(
            principal_id="person-al", organization_id="aot", client_id=None,
            canonical_capability="service.ticket.update", selected_provider_id="provider-1",
            provider_capability="autotask.ticket.update", action_method="PATCH",
            resource_type="service_ticket", resource_identifier="140000",
            normalized_path="https://dynamic-zone.example/V1.0/Tickets",
            normalized_payload={"id": 140000, "status": 8},
        )


def test_execution_plan_rejects_proxy_auth_cookie_and_private_key_material():
    import pytest
    for key in ("Proxy-Authorization", "Cookie", "Set-Cookie", "X-API-Key", "private-key"):
        with pytest.raises(ValueError, match="secret material"):
            ExecutionPlan(
                principal_id="person-al", organization_id="aot", client_id=None,
                canonical_capability="service.ticket.update", selected_provider_id="provider-1",
                provider_capability="autotask.ticket.update", action_method="PATCH",
                resource_type="service_ticket", resource_identifier="140000",
                normalized_path="/V1.0/Tickets",
                normalized_payload={"id": 140000, key: "secret"},
            )


def test_execution_plan_rejects_non_json_and_non_finite_material():
    import pytest
    from decimal import Decimal
    for bad in (Decimal("1.0"), {"not", "json"}, float("nan"), float("inf")):
        with pytest.raises(TypeError):
            ExecutionPlan(
                principal_id="person-al", organization_id="aot", client_id=None,
                canonical_capability="service.ticket.update", selected_provider_id="provider-1",
                provider_capability="autotask.ticket.update", action_method="PATCH",
                resource_type="service_ticket", resource_identifier="140000",
                normalized_path="/V1.0/Tickets",
                normalized_payload={"id": 140000, "bad": bad},
            )


def test_execution_plan_rejects_non_string_object_keys():
    import pytest
    with pytest.raises(TypeError, match="keys must be strings"):
        ExecutionPlan(
            principal_id="person-al", organization_id="aot", client_id=None,
            canonical_capability="service.ticket.update", selected_provider_id="provider-1",
            provider_capability="autotask.ticket.update", action_method="PATCH",
            resource_type="service_ticket", resource_identifier="140000",
            normalized_path="/V1.0/Tickets",
            normalized_payload={1: "bad-key"},
        )


def test_external_approval_continuation_without_ledger_still_plan_binds():
    invoker = PlanInvoker([{}, {}])
    audit = Audit()
    orchestrator = CentralOrchestrator(
        resolution=Resolution(), invoker=invoker, audit=audit
    )
    request = make_request(
        execution_id="exec-external", correlation_id="corr-external",
        approval_id="approval-unused", idempotency_key="idem-unused",
    )
    from dataclasses import replace
    request = replace(request, approval_id=None, idempotency_key=None)

    result = orchestrator.execute(request)

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert invoker.prepare_calls == 2
    assert invoker.provider_calls == 1
    authorized = [p for e, p in audit.events if e == "orchestration.execution_plan.authorized"]
    assert len(authorized) == 1
    assert authorized[0]["approval_binding"] == "external_continuation_guard"
    assert authorized[0]["execution_plan_fingerprint"]


def test_external_approval_continuation_plan_change_denied_zero_writes():
    invoker = PlanInvoker([{}, {"target": "140001", "payload": {"id": 140001, "queueID": 29682837, "status": 8}}])
    audit = Audit()
    orchestrator = CentralOrchestrator(
        resolution=Resolution(), invoker=invoker, audit=audit
    )
    request = make_request(
        execution_id="exec-external-mismatch", correlation_id="corr-external-mismatch",
        approval_id="approval-unused", idempotency_key="idem-unused",
    )
    from dataclasses import replace
    request = replace(request, approval_id=None, idempotency_key=None)

    result = orchestrator.execute(request)

    assert result.status is OrchestrationStatus.DENIED
    assert result.error_code == "EXECUTION_PLAN_MISMATCH"
    assert invoker.provider_calls == 0
    denied = [p for e, p in audit.events if e == "orchestration.execution_plan.denied"]
    assert denied[-1]["provider_invoked"] is False
    assert denied[-1]["approval_binding"] == "external_continuation_guard"
