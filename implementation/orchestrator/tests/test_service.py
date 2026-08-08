from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator import (
    ArtifactReference,
    CentralOrchestrator,
    InvocationResult,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationStatus,
)


class Resolution:
    def __init__(self, outcome=ResolutionOutcome.RESOLVED):
        self.outcome = outcome
        self.requests = []

    def resolve(self, request):
        self.requests.append(request)
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version="1.0.0",
            outcome=self.outcome,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=(self.outcome.value,),
            eligible_provider_ids=("provider-1",),
            selected_provider_id="provider-1",
        )


class Invoker:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def invoke(self, *, request, resolution):
        self.calls.append((request, resolution))
        if self.fail:
            raise RuntimeError("protected provider detail")
        return InvocationResult(
            output={"status": "ok"},
            artifact_references=(ArtifactReference("evidence://result/1"),),
            attempts=1,
        )


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class AuthorityContext:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def validate(self, request):
        self.calls.append(request)
        return self.failure


def request(mode=OrchestrationMode.EXECUTE, **changes):
    values = {
        "execution_id": "exec-1",
        "correlation_id": "corr-1",
        "principal_id": "person-al",
        "organization_id": "aot",
        "capability_name": "autotask.ticket.search",
        "capability_version": None,
        "requested_mode": "observe",
        "orchestration_mode": mode,
        "authority_allowed": True,
        "approval_present": False,
        "risk": "low",
        "data_handling": DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        "budget": ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        "arguments": {"ticket_number": "T1"},
        "artifact_references": (ArtifactReference("evidence://input/1"),),
    }
    values.update(changes)
    return OrchestrationRequest(**values)


def test_check_only_resolves_policy_without_invoking_capability():
    resolution = Resolution()
    invoker = Invoker()
    audit = Audit()
    result = CentralOrchestrator(resolution=resolution, invoker=invoker, audit=audit).execute(
        request(OrchestrationMode.CHECK_ONLY)
    )
    assert result.status is OrchestrationStatus.VALIDATED
    assert invoker.calls == []
    assert len(resolution.requests) == 1


def test_execute_routes_one_named_capability_and_returns_references():
    invoker = Invoker()
    result = CentralOrchestrator(resolution=Resolution(), invoker=invoker, audit=Audit()).execute(request())
    assert result.status is OrchestrationStatus.SUCCEEDED
    assert [item.reference for item in result.artifact_references] == [
        "evidence://input/1", "evidence://result/1"
    ]


def test_required_authority_context_is_checked_before_resolution():
    resolution = Resolution()
    invoker = Invoker()
    result = CentralOrchestrator(
        resolution=resolution,
        invoker=invoker,
        audit=Audit(),
        authority_context=AuthorityContext(),
        require_authority_context=True,
    ).execute(request())
    assert result.status is OrchestrationStatus.DENIED
    assert result.reason_codes == ("AUTHORITY_CONTEXT_REQUIRED",)
    assert result.resolution is None
    assert resolution.requests == []
    assert invoker.calls == []


def test_invalid_authority_context_is_checked_before_resolution():
    resolution = Resolution()
    invoker = Invoker()
    result = CentralOrchestrator(
        resolution=resolution,
        invoker=invoker,
        audit=Audit(),
        authority_context=AuthorityContext("EXECUTION_CONTEXT_REVOKED"),
        require_authority_context=True,
    ).execute(request(authority_context_id="ctx-1"))
    assert result.status is OrchestrationStatus.DENIED
    assert result.reason_codes == ("EXECUTION_CONTEXT_REVOKED",)
    assert resolution.requests == []
    assert invoker.calls == []


def test_valid_authority_context_allows_normal_resolution():
    context = AuthorityContext()
    result = CentralOrchestrator(
        resolution=Resolution(),
        invoker=Invoker(),
        audit=Audit(),
        authority_context=context,
        require_authority_context=True,
    ).execute(request(authority_context_id="ctx-1"))
    assert result.status is OrchestrationStatus.SUCCEEDED
    assert len(context.calls) == 1


def test_non_allowing_resolution_never_invokes_capability():
    invoker = Invoker()
    result = CentralOrchestrator(
        resolution=Resolution(ResolutionOutcome.APPROVAL_REQUIRED),
        invoker=invoker,
        audit=Audit(),
    ).execute(request())
    assert result.status is OrchestrationStatus.APPROVAL_REQUIRED
    assert invoker.calls == []


def test_provider_failure_is_sanitized_and_correlated():
    audit = Audit()
    result = CentralOrchestrator(
        resolution=Resolution(), invoker=Invoker(fail=True), audit=audit
    ).execute(request())
    assert result.status is OrchestrationStatus.FAILED
    assert result.error_code == "CAPABILITY_INVOCATION_FAILED"
    assert "protected provider detail" not in repr(result) + repr(audit.events)


def test_direct_agent_invocation_contract_is_rejected():
    with pytest.raises(ValueError, match="Direct agent invocation"):
        request(requester_kind="agent", arguments={"target_agent": "other-agent"})
