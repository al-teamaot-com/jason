from __future__ import annotations

from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.invokers import (
    CapabilityInvokerAlreadyRegisteredError,
    CapabilityInvokerNotRegisteredError,
    CapabilityInvokerRegistry,
)
from orchestrator.service import InvocationResult


class FakeInvoker:
    def __init__(self) -> None:
        self.calls = []

    def invoke(self, *, request, resolution):
        self.calls.append((request, resolution))
        return InvocationResult(output={"status": "ok"})


def request(capability_name: str = "autotask.ticket.search") -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        capability_name=capability_name,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
        ),
    )


def resolution(capability_name: str = "autotask.ticket.search") -> CapabilityResolutionResult:
    return CapabilityResolutionResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name=capability_name,
        capability_version="1.0.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
        reason_codes=("resolved",),
        eligible_provider_ids=("provider-1",),
        selected_provider_id="provider-1",
    )


def test_routes_only_to_registered_canonical_capability() -> None:
    invoker = FakeInvoker()
    registry = CapabilityInvokerRegistry()
    registry.register("autotask.ticket.search", invoker)

    result = registry.invoke(
        request=request(),
        resolution=resolution(),
    )

    assert result.output == {"status": "ok"}
    assert len(invoker.calls) == 1
    assert registry.registered_capabilities() == (
        "autotask.ticket.search",
    )


def test_unknown_capability_fails_closed() -> None:
    registry = CapabilityInvokerRegistry()

    with pytest.raises(
        CapabilityInvokerNotRegisteredError,
        match="not registered",
    ):
        registry.invoke(
            request=request(),
            resolution=resolution(),
        )


def test_duplicate_registration_is_denied() -> None:
    registry = CapabilityInvokerRegistry()
    registry.register("autotask.ticket.search", FakeInvoker())

    with pytest.raises(
        CapabilityInvokerAlreadyRegisteredError,
        match="already registered",
    ):
        registry.register("autotask.ticket.search", FakeInvoker())


def test_request_and_resolution_capability_must_match() -> None:
    registry = CapabilityInvokerRegistry()
    registry.register("it_glue.organization.read", FakeInvoker())

    with pytest.raises(ValueError, match="does not match"):
        registry.invoke(
            request=request("autotask.ticket.search"),
            resolution=resolution("it_glue.organization.read"),
        )


def test_snapshot_does_not_allow_registry_mutation() -> None:
    registry = CapabilityInvokerRegistry()
    registry.register("autotask.ticket.search", FakeInvoker())

    snapshot = registry.snapshot()
    snapshot.clear()

    assert registry.registered_capabilities() == (
        "autotask.ticket.search",
    )
