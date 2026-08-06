from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator import (
    CentralOrchestrator,
    InvocationResult,
    OrchestrationMode,
    OrchestrationRequest,
    SQLiteOrchestrationEventStore,
)


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
    def invoke(self, *, request, resolution):
        return InvocationResult(output={"status": "approved"})


def request(mode: OrchestrationMode) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-durable-1",
        correlation_id="corr-durable-1",
        principal_id="operator-al",
        organization_id="aot",
        capability_name="example.capability.read",
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=mode,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
    )


def test_execute_lifecycle_is_durable_across_restart(tmp_path: Path) -> None:
    database = tmp_path / "orchestration.sqlite3"
    store = SQLiteOrchestrationEventStore(database)
    result = CentralOrchestrator(
        resolution=Resolution(),
        invoker=Invoker(),
        audit=store,
    ).execute(request(OrchestrationMode.EXECUTE))
    store.close()

    assert result.status.value == "succeeded"

    reopened = SQLiteOrchestrationEventStore(database)
    events = reopened.list_by_execution("exec-durable-1")
    reopened.close()

    assert tuple(event.event_type for event in events) == (
        "orchestration.request.received",
        "orchestration.capability.resolved",
        "orchestration.capability.invoking",
        "orchestration.capability.completed",
    )
    assert all(event.correlation_id == "corr-durable-1" for event in events)
    assert all(event.organization_id == "aot" for event in events)
    assert all(event.principal_id == "operator-al" for event in events)


def test_check_only_lifecycle_is_durable_without_invocation(tmp_path: Path) -> None:
    database = tmp_path / "orchestration.sqlite3"
    store = SQLiteOrchestrationEventStore(database)

    class DenyInvocation:
        def invoke(self, **kwargs):
            raise AssertionError("check-only invoked a capability")

    result = CentralOrchestrator(
        resolution=Resolution(),
        invoker=DenyInvocation(),
        audit=store,
    ).execute(request(OrchestrationMode.CHECK_ONLY))
    events = store.list_by_correlation("corr-durable-1")
    store.close()

    assert result.status.value == "validated"
    assert tuple(event.event_type for event in events) == (
        "orchestration.request.received",
        "orchestration.capability.resolved",
        "orchestration.check_only.validated",
    )
    assert events[-1].payload["provider_invoked"] is False
