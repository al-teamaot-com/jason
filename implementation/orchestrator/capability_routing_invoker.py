from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
from .execution_plan import PreparedExecutionPlan
from .service import CapabilityInvoker, InvocationResult


@dataclass(frozen=True, slots=True)
class CanonicalCapabilityRoutingInvoker:
    """Route one canonical capability to its already-governed invoker.

    This adapter does not make an authority or provider-selection decision. The
    Central Orchestrator has already resolved both. It only preserves distinct
    provider-specific information/execution boundaries when several capability
    families share a runtime composition seam.
    """

    routes: Mapping[str, CapabilityInvoker]

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.capability_name != request.capability_name:
            raise PermissionError(
                "resolved capability does not match orchestration request"
            )

        delegate = self.routes.get(request.capability_name)
        if delegate is None:
            raise LookupError(
                "no governed invoker route is registered for canonical capability: "
                f"{request.capability_name}"
            )

        return delegate.invoke(
            request=request,
            resolution=resolution,
        )
    def prepare_execution_plan(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> PreparedExecutionPlan:
        delegate = self._delegate(request=request, resolution=resolution)
        prepare = getattr(delegate, "prepare_execution_plan", None)
        if not callable(prepare):
            raise PermissionError("governed route does not expose execution-plan preparation")
        return prepare(request=request, resolution=resolution)

    def invoke_execution_plan(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        prepared: PreparedExecutionPlan,
    ) -> InvocationResult:
        delegate = self._delegate(request=request, resolution=resolution)
        invoke = getattr(delegate, "invoke_execution_plan", None)
        if not callable(invoke):
            raise PermissionError("governed route does not expose execution-plan invocation")
        return invoke(request=request, resolution=resolution, prepared=prepared)

    def _delegate(self, *, request: OrchestrationRequest, resolution: CapabilityResolutionResult) -> CapabilityInvoker:
        if resolution.capability_name != request.capability_name:
            raise PermissionError("resolved capability does not match orchestration request")
        delegate = self.routes.get(request.capability_name)
        if delegate is None:
            raise LookupError(
                "no governed invoker route is registered for canonical capability: "
                f"{request.capability_name}"
            )
        return delegate
