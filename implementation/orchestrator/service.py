from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from kernel.resolution import (
    CapabilityResolutionRequest,
    CapabilityResolutionResult,
    GovernedCapabilityResolutionEngine,
    ResolutionOutcome,
)

from .contracts import (
    ArtifactReference,
    ExecutionStage,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)


class OrchestrationAuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class InvocationResult:
    output: Mapping[str, Any] = field(default_factory=dict)
    artifact_references: tuple[ArtifactReference, ...] = ()
    attempts: int = 1


class CapabilityInvoker(Protocol):
    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult: ...


class CentralOrchestrator:
    """Coordinate governed capability execution without provider logic."""

    def __init__(
        self,
        *,
        resolution: GovernedCapabilityResolutionEngine,
        invoker: CapabilityInvoker,
        audit: OrchestrationAuditSink,
    ) -> None:
        self._resolution = resolution
        self._invoker = invoker
        self._audit = audit

    def execute(self, request: OrchestrationRequest) -> OrchestrationResult:
        self._record(
            "orchestration.request.received",
            request,
            stage=ExecutionStage.RECEIVED,
        )

        resolution = self._resolution.resolve(
            CapabilityResolutionRequest(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=request.capability_name,
                capability_version=request.capability_version,
                tenant_id=request.organization_id,
                client_id=request.client_id,
                requested_mode=request.requested_mode,
                authority_allowed=request.authority_allowed,
                approval_present=request.approval_present,
                risk=request.risk,
                data_handling=request.data_handling,
                budget=request.budget,
                region=request.region,
                policy_ids=request.policy_ids,
                allow_pilot_capability=request.allow_pilot_capability,
                allow_pilot_provider=request.allow_pilot_provider,
            )
        )

        self._record(
            "orchestration.capability.resolved",
            request,
            stage=ExecutionStage.POLICY_DECIDED,
            details={
                "resolution_outcome": resolution.outcome.value,
                "reason_codes": resolution.reason_codes,
                "selected_provider_id": resolution.selected_provider_id,
            },
        )

        terminal = self._terminal_result(request, resolution)
        if terminal is not None:
            self._record(
                "orchestration.request.terminated",
                request,
                stage=terminal.stage,
                details={
                    "status": terminal.status.value,
                    "reason_codes": terminal.reason_codes,
                },
            )
            return terminal

        if request.orchestration_mode is OrchestrationMode.CHECK_ONLY:
            result = OrchestrationResult(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=resolution.capability_name,
                status=OrchestrationStatus.VALIDATED,
                stage=ExecutionStage.COMPLETED,
                reason_codes=("check_only_validated",),
                resolution=resolution,
                artifact_references=request.artifact_references,
                attempts=0,
                provider_id=resolution.selected_provider_id,
            )
            self._record(
                "orchestration.check_only.validated",
                request,
                stage=ExecutionStage.COMPLETED,
                details={"provider_invoked": False},
            )
            return result

        self._record(
            "orchestration.capability.invoking",
            request,
            stage=ExecutionStage.INVOKING,
            details={"provider_id": resolution.selected_provider_id},
        )

        try:
            invocation = self._invoker.invoke(
                request=request,
                resolution=resolution,
            )
        except Exception as exc:
            safe_error_code = getattr(exc, "error_code", "CAPABILITY_INVOCATION_FAILED")
            result = OrchestrationResult(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=resolution.capability_name,
                status=OrchestrationStatus.FAILED,
                stage=ExecutionStage.FAILED,
                reason_codes=("capability_invocation_failed",),
                resolution=resolution,
                artifact_references=request.artifact_references,
                attempts=1,
                provider_id=resolution.selected_provider_id,
                error_code=str(safe_error_code),
            )
            self._record(
                "orchestration.capability.failed",
                request,
                stage=ExecutionStage.FAILED,
                details={"error_code": result.error_code},
            )
            return result

        result = OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=resolution.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=resolution,
            output=dict(invocation.output),
            artifact_references=(
                request.artifact_references
                + invocation.artifact_references
            ),
            attempts=invocation.attempts,
            provider_id=resolution.selected_provider_id,
        )
        self._record(
            "orchestration.capability.completed",
            request,
            stage=ExecutionStage.COMPLETED,
            details={
                "attempts": invocation.attempts,
                "artifact_reference_count": len(result.artifact_references),
            },
        )
        return result

    @staticmethod
    def _terminal_result(
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> OrchestrationResult | None:
        mapping = {
            ResolutionOutcome.APPROVAL_REQUIRED: (
                OrchestrationStatus.APPROVAL_REQUIRED,
                ExecutionStage.DENIED,
            ),
            ResolutionOutcome.HUMAN_REQUIRED: (
                OrchestrationStatus.HUMAN_REQUIRED,
                ExecutionStage.DENIED,
            ),
            ResolutionOutcome.DENIED: (
                OrchestrationStatus.DENIED,
                ExecutionStage.DENIED,
            ),
            ResolutionOutcome.UNRESOLVED: (
                OrchestrationStatus.DENIED,
                ExecutionStage.DENIED,
            ),
        }
        translated = mapping.get(resolution.outcome)
        if translated is None:
            return None
        status, stage = translated
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=resolution.capability_name,
            status=status,
            stage=stage,
            reason_codes=resolution.reason_codes,
            resolution=resolution,
            artifact_references=request.artifact_references,
            attempts=0,
            provider_id=resolution.selected_provider_id,
        )

    def _record(
        self,
        event_type: str,
        request: OrchestrationRequest,
        *,
        stage: ExecutionStage,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "execution_id": request.execution_id,
            "correlation_id": request.correlation_id,
            "principal_id": request.principal_id,
            "organization_id": request.organization_id,
            "capability_name": request.capability_name,
            "stage": stage.value,
            "requester_kind": request.requester_kind,
        }
        payload.update(details or {})
        self._audit.append(event_type, payload)
