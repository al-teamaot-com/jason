from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
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
