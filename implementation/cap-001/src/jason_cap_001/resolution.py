from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from kernel.execution_policy import (
    DataHandlingPolicy,
    ExecutionBudget,
)
from kernel.resolution import (
    CapabilityResolutionRequest,
    CapabilityResolutionResult,
    GovernedCapabilityResolutionEngine,
    ResolutionOutcome,
)


class CapabilityResolutionError(PermissionError):
    """Raised when the Kernel does not resolve CAP-001 for execution."""


class CapabilityResolver(Protocol):
    def resolve(
        self,
        request: CapabilityResolutionRequest,
    ) -> CapabilityResolutionResult: ...


@dataclass(frozen=True, slots=True)
class ResolutionAuthorization:
    result: CapabilityResolutionResult

    @property
    def execution_plan(self):
        return self.result.execution_plan


class Cap001KernelResolutionAdapter:
    """Translate a CAP-001 request into the JKD-007 resolution contract."""

    def __init__(
        self,
        resolver: CapabilityResolver
        | GovernedCapabilityResolutionEngine,
    ) -> None:
        self._resolver = resolver

    def authorize(
        self,
        request: dict[str, Any],
        *,
        authority_allowed: bool,
    ) -> ResolutionAuthorization:
        context = request["execution_context"]

        resolution_request = CapabilityResolutionRequest(
            execution_id=request["request_id"],
            correlation_id=request["correlation_id"],
            capability_name=context["capability"],
            capability_version="0.1",
            tenant_id=context["organization_id"],
            client_id=context["client_id"],
            requested_mode=context["execution_mode"],
            authority_allowed=authority_allowed,
            approval_present=False,
            risk="medium",
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=(
                    context["execution_mode"] == "hosted_ai"
                ),
            ),
            budget=ExecutionBudget(
                maximum_estimated_cost=Decimal("0"),
                maximum_attempts=1,
            ),
            policy_ids=("cap-001-read-only-v0.1",),
            allow_pilot_capability=True,
            allow_pilot_provider=True,
            # CAP-001 request IDs are already unique operation identifiers. Reusing
            # the request ID as the resolution idempotency key preserves the
            # capability's existing deterministic/read-only contract while
            # satisfying the Kernel's capability-level idempotency gate.
            idempotency_key=request["request_id"],
        )

        result = self._resolver.resolve(resolution_request)

        if result.outcome is not ResolutionOutcome.RESOLVED:
            reasons = ", ".join(result.reason_codes)
            raise CapabilityResolutionError(
                "CAP-001 resolution did not permit execution: "
                f"{reasons}"
            )

        if result.execution_plan is None:
            raise CapabilityResolutionError(
                "CAP-001 resolution returned no execution plan."
            )

        return ResolutionAuthorization(result=result)
