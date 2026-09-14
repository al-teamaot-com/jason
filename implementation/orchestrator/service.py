from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
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
from .information_authorization import (
    FailClosedInformationReleaseAuthorizer,
    InformationAuthorizationEnvelope,
    InformationReleaseAuthorizer,
    InformationRemediation,
)


class OrchestrationAuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


class AuthorityContextEnforcer(Protocol):
    def validate(self, request: OrchestrationRequest) -> str | None: ...


@dataclass(frozen=True, slots=True)
class InvocationTelemetry:
    """Bounded accountability metadata for one capability invocation."""

    provider_resources: tuple[str, ...] = ()
    mapping_references: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    hosted_model_used: bool = False
    hosted_model_name: str | None = None
    hosted_model_input_tokens: int = 0
    hosted_model_output_tokens: int = 0
    hosted_model_cost_usd: str = "0"

    def __post_init__(self) -> None:
        if self.hosted_model_input_tokens < 0 or self.hosted_model_output_tokens < 0:
            raise ValueError("hosted model token counts must not be negative")
        if not self.hosted_model_cost_usd.strip():
            raise ValueError("hosted_model_cost_usd must be non-empty")
        if not self.hosted_model_used:
            if self.hosted_model_name is not None:
                raise ValueError("hosted_model_name requires hosted_model_used")
            if self.hosted_model_input_tokens or self.hosted_model_output_tokens:
                raise ValueError("hosted model tokens require hosted_model_used")
            if self.hosted_model_cost_usd not in {"0", "0.0", "0.00", "0.000000"}:
                raise ValueError("hosted model cost must be zero when no hosted model was used")


@dataclass(frozen=True, slots=True)
class InvocationResult:
    output: Mapping[str, Any] = field(default_factory=dict)
    artifact_references: tuple[ArtifactReference, ...] = ()
    attempts: int = 1
    telemetry: InvocationTelemetry | None = None
    information_authorization: InformationAuthorizationEnvelope | None = None


class CapabilityInvoker(Protocol):
    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult: ...


class CentralOrchestrator:
    """Coordinate governed capability execution without provider logic.

    Information release authorization is deliberately separate from capability and
    provider execution authorization. Any invocation that carries an information
    authorization envelope is automatically release-gated. Callers may also require
    the gate for every invocation; in that mode a missing envelope fails closed.
    """

    def __init__(
        self,
        *,
        resolution: GovernedCapabilityResolutionEngine,
        invoker: CapabilityInvoker,
        audit: OrchestrationAuditSink,
        authority_context: AuthorityContextEnforcer | None = None,
        require_authority_context: bool = False,
        information_release: InformationReleaseAuthorizer | None = None,
        require_information_release_authorization: bool = False,
    ) -> None:
        self._resolution = resolution
        self._invoker = invoker
        self._audit = audit
        self._authority_context = authority_context
        self._require_authority_context = require_authority_context
        self._information_release = (
            information_release or FailClosedInformationReleaseAuthorizer()
        )
        self._require_information_release_authorization = (
            require_information_release_authorization
        )
        if require_authority_context and authority_context is None:
            raise ValueError("authority_context enforcer is required when enforcement is enabled")

    def execute(self, request: OrchestrationRequest) -> OrchestrationResult:
        self._record("orchestration.request.received", request, stage=ExecutionStage.RECEIVED)

        authority_failure = self._authority_failure(request)
        if authority_failure is not None:
            result = OrchestrationResult(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=request.capability_name,
                status=OrchestrationStatus.DENIED,
                stage=ExecutionStage.DENIED,
                reason_codes=(authority_failure,),
                resolution=None,
                artifact_references=request.artifact_references,
                attempts=0,
                error_code="AUTHORITY_CONTEXT_INVALID",
            )
            self._record(
                "orchestration.authority_context.denied",
                request,
                stage=ExecutionStage.DENIED,
                details={"reason_code": authority_failure},
            )
            return result

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
                idempotency_key=request.idempotency_key,
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
                details={"status": terminal.status.value, "reason_codes": terminal.reason_codes},
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

        invocation_started = monotonic()
        try:
            invocation = self._invoker.invoke(request=request, resolution=resolution)
        except Exception as exc:
            duration_ms = round((monotonic() - invocation_started) * 1000, 3)
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
                details={
                    "error_code": result.error_code,
                    "provider_id": resolution.selected_provider_id,
                    "duration_ms": duration_ms,
                    "status": result.status.value,
                },
            )
            return result

        duration_ms = round((monotonic() - invocation_started) * 1000, 3)
        release_output = dict(invocation.output)
        release_gate_applies = (
            self._require_information_release_authorization
            or invocation.information_authorization is not None
        )
        if release_gate_applies:
            release = self._information_release.authorize_release(
                request=request,
                resolution=resolution,
                output=invocation.output,
                authorization=invocation.information_authorization,
            )
            self._record(
                "orchestration.information_release.decided",
                request,
                stage=(ExecutionStage.COMPLETED if release.allowed else ExecutionStage.DENIED),
                details={
                    "provider_id": resolution.selected_provider_id,
                    "allowed": release.allowed,
                    "reason_code": release.reason_code,
                    "remediation": release.remediation.value,
                    "handling_class": release.handling_class.value,
                    "policy_ids": release.policy_ids,
                    "authorization_basis": release.authorization_basis,
                },
            )
            if not release.allowed:
                status = (
                    OrchestrationStatus.APPROVAL_REQUIRED
                    if release.remediation is InformationRemediation.REQUEST_APPROVAL
                    else OrchestrationStatus.DENIED
                )
                return OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=status,
                    stage=ExecutionStage.DENIED,
                    reason_codes=(release.reason_code, release.remediation.value.upper()),
                    resolution=resolution,
                    output={},
                    artifact_references=request.artifact_references,
                    attempts=invocation.attempts,
                    provider_id=resolution.selected_provider_id,
                    error_code="INFORMATION_RELEASE_DENIED",
                )
            release_output = dict(release.output)

        result = OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=resolution.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=resolution,
            output=release_output,
            artifact_references=request.artifact_references + invocation.artifact_references,
            attempts=invocation.attempts,
            provider_id=resolution.selected_provider_id,
        )
        details: dict[str, Any] = {
            "attempts": invocation.attempts,
            "artifact_reference_count": len(result.artifact_references),
            "provider_id": resolution.selected_provider_id,
            "provider_capability": invocation.output.get("provider_capability"),
            "duration_ms": duration_ms,
            "status": result.status.value,
            "information_release_gate_applied": release_gate_applies,
        }
        telemetry = invocation.telemetry
        if telemetry is not None:
            details.update(
                {
                    "provider_resources": telemetry.provider_resources,
                    "mapping_references": telemetry.mapping_references,
                    "evidence_references": telemetry.evidence_references,
                    "hosted_model_used": telemetry.hosted_model_used,
                    "hosted_model_name": telemetry.hosted_model_name,
                    "hosted_model_input_tokens": telemetry.hosted_model_input_tokens,
                    "hosted_model_output_tokens": telemetry.hosted_model_output_tokens,
                    "hosted_model_cost_usd": telemetry.hosted_model_cost_usd,
                }
            )
        else:
            details["invocation_telemetry"] = "not_reported"

        self._record(
            "orchestration.capability.completed",
            request,
            stage=ExecutionStage.COMPLETED,
            details=details,
        )
        return result

    def _authority_failure(self, request: OrchestrationRequest) -> str | None:
        if not self._require_authority_context:
            return None
        if request.authority_context_id is None:
            return "AUTHORITY_CONTEXT_REQUIRED"
        assert self._authority_context is not None
        return self._authority_context.validate(request)

    @staticmethod
    def _terminal_result(
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> OrchestrationResult | None:
        mapping = {
            ResolutionOutcome.APPROVAL_REQUIRED: (OrchestrationStatus.APPROVAL_REQUIRED, ExecutionStage.DENIED),
            ResolutionOutcome.HUMAN_REQUIRED: (OrchestrationStatus.HUMAN_REQUIRED, ExecutionStage.DENIED),
            ResolutionOutcome.DENIED: (OrchestrationStatus.DENIED, ExecutionStage.DENIED),
            ResolutionOutcome.UNRESOLVED: (OrchestrationStatus.DENIED, ExecutionStage.DENIED),
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
            "client_id": request.client_id,
            "capability_name": request.capability_name,
            "stage": stage.value,
            "requester_kind": request.requester_kind,
            "authority_context_id": request.authority_context_id,
        }
        payload.update(details or {})
        self._audit.append(event_type, payload)
