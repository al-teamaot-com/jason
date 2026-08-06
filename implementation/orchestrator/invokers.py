from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
from .service import CapabilityInvoker, InvocationResult


class CapabilityInvokerNotRegisteredError(LookupError):
    """Raised when no approved implementation is registered for a capability."""


class CapabilityInvokerAlreadyRegisteredError(ValueError):
    """Raised when registration would replace an existing implementation."""


@dataclass(slots=True)
class CapabilityInvokerRegistry(CapabilityInvoker):
    """Route canonical capability names to approved invocation implementations.

    The registry contains implementation bindings only. It does not resolve
    capabilities, select providers, evaluate policy, retrieve secrets, or call
    agents. Those responsibilities remain with the Kernel and central
    orchestrator.
    """

    _invokers: dict[str, CapabilityInvoker] = field(default_factory=dict)

    def register(self, capability_name: str, invoker: CapabilityInvoker) -> None:
        canonical_name = self._normalize_name(capability_name)
        if canonical_name in self._invokers:
            raise CapabilityInvokerAlreadyRegisteredError(
                f"Capability invoker is already registered: {canonical_name}"
            )
        self._invokers[canonical_name] = invoker

    def unregister(self, capability_name: str) -> None:
        canonical_name = self._normalize_name(capability_name)
        if canonical_name not in self._invokers:
            raise CapabilityInvokerNotRegisteredError(
                f"Capability invoker is not registered: {canonical_name}"
            )
        del self._invokers[canonical_name]

    def registered_capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._invokers))

    def snapshot(self) -> Mapping[str, CapabilityInvoker]:
        return dict(self._invokers)

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        canonical_name = self._normalize_name(resolution.capability_name)
        invoker = self._invokers.get(canonical_name)
        if invoker is None:
            raise CapabilityInvokerNotRegisteredError(
                f"Capability invoker is not registered: {canonical_name}"
            )
        if request.capability_name.strip() != resolution.capability_name:
            raise ValueError(
                "Resolved capability does not match the requested capability."
            )
        return invoker.invoke(request=request, resolution=resolution)

    @staticmethod
    def _normalize_name(capability_name: str) -> str:
        normalized = capability_name.strip()
        if not normalized:
            raise ValueError("capability_name must be non-empty.")
        return normalized
