from dataclasses import dataclass, field
from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.service import CentralOrchestrator


@dataclass
class Resolution:
    requests: list = field(default_factory=list)

    def resolve(self, request):
        self.requests.append(request)
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version="1.0",
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=("test_resolved",),
            eligible_provider_ids=(request.required_provider_id,),
            selected_provider_id=request.required_provider_id,
        )


@dataclass
class Audit:
    events: list = field(default_factory=list)

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class NeverInvoke:
    def invoke(self, **kwargs):
        raise AssertionError("CHECK_ONLY must not invoke provider")


def test_central_orchestrator_preserves_required_provider_affinity_into_resolution():
    resolution = Resolution()
    orchestrator = CentralOrchestrator(
        resolution=resolution,
        invoker=NeverInvoke(),
        audit=Audit(),
    )
    request = OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="person-1",
        organization_id="aot",
        capability_name="provider.resource.search",
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.CHECK_ONLY,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("1.00"),
            maximum_attempts=1,
        ),
        required_provider_id="microsoft_graph",
    )

    result = orchestrator.execute(request)

    assert resolution.requests[0].required_provider_id == "microsoft_graph"
    assert result.provider_id == "microsoft_graph"
    assert result.status.value == "validated"
