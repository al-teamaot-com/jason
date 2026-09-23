from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Mapping, Protocol

from kernel.execution_deadline import governed_execution_deadline_at
from kernel.resolution import (
    CapabilityResolutionRequest,
    CapabilityResolutionResult,
    GovernedCapabilityResolutionEngine,
    ResolutionOutcome,
)

from .governed_execution_ledger import (
    SQLiteGovernedExecutionLedger,
    intent_fingerprint as governed_intent_fingerprint,
)
from .execution_plan import ExecutionPlan, PreparedExecutionPlan

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


_PROVIDER_EXECUTION_SECONDS_METADATA = "provider_maximum_execution_seconds"


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


class GovernedExecutionPlanInvoker(Protocol):
    """Invoker contract for approval-governed provider mutations.

    Preparation must be side-effect-free with respect to provider mutation. It may
    perform bounded metadata/identity reads needed to resolve symbolic values. The
    second prepared plan is the only object eligible for provider invocation.
    """

    def prepare_execution_plan(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> PreparedExecutionPlan: ...

    def invoke_execution_plan(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        prepared: PreparedExecutionPlan,
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
        governed_execution_ledger: SQLiteGovernedExecutionLedger | None = None,
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
        self._governed_execution_ledger = governed_execution_ledger
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

        intent_fingerprint = None
        execution_plan_fingerprint = None
        prepared_execution: PreparedExecutionPlan | None = None
        invoke_prepared = None
        provider_deadline_monotonic: float | None = None

        if request.approval_id is not None:
            if self._governed_execution_ledger is None:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("governed_execution_ledger_required",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="GOVERNED_EXECUTION_LEDGER_REQUIRED",
                )
                self._record(
                    "orchestration.approval.consumption_denied", request,
                    stage=ExecutionStage.DENIED,
                    details={"replay_result": "rejected", "error_code": result.error_code},
                )
                return result
            try:
                intent = self._governed_execution_ledger.check_intent(request)
                intent_fingerprint = intent.intent_fingerprint
            except PermissionError as exc:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("approval_consumption_rejected",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="APPROVAL_CONSUMPTION_REJECTED",
                )
                self._record(
                    "orchestration.approval.consumption_denied", request,
                    stage=ExecutionStage.DENIED,
                    details={"replay_result": "rejected", "message": str(exc)},
                )
                return result
            if intent.replay_result is not None:
                prior = intent.replay_result
                evidence = self._governed_execution_ledger.evidence(request.approval_id) or {}
                self._record(
                    "orchestration.idempotency.deduplicated", request,
                    stage=ExecutionStage.COMPLETED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "action_fingerprint": intent_fingerprint,
                        "execution_plan_fingerprint": evidence.get("execution_plan_fingerprint"),
                        "replay_result": "deduplicated",
                        "consumption_state": "succeeded",
                        "original_execution_id": prior.execution_id,
                        "original_correlation_id": prior.correlation_id,
                    },
                )
                return prior

            prepare_plan = getattr(self._invoker, "prepare_execution_plan", None)
            invoke_prepared = getattr(self._invoker, "invoke_execution_plan", None)
            if not callable(prepare_plan) or not callable(invoke_prepared):
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_binding_required",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="EXECUTION_PLAN_BINDING_REQUIRED",
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "provider_invoked": False,
                        "message": "approved mutation invoker does not expose governed execution-plan binding",
                    },
                )
                return result

            try:
                provider_deadline_monotonic = self._provider_deadline_monotonic(resolution)
                with governed_execution_deadline_at(provider_deadline_monotonic):
                    authorized_prepared = prepare_plan(request=request, resolution=resolution)
                contract_error = self._execution_plan_contract_error(
                    request=request, resolution=resolution, plan=authorized_prepared.plan
                )
                if contract_error is not None:
                    raise PermissionError(contract_error)
                binding = self._governed_execution_ledger.authorize_execution_plan(
                    request, authorized_prepared.plan
                )
                execution_plan_fingerprint = binding.execution_plan_fingerprint
            except Exception as exc:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_authorization_rejected",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="EXECUTION_PLAN_AUTHORIZATION_REJECTED",
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "provider_invoked": False,
                        "message": str(exc),
                    },
                )
                return result

            self._record(
                "orchestration.execution_plan.authorized", request,
                stage=ExecutionStage.POLICY_DECIDED,
                details={
                    "intent_fingerprint": intent_fingerprint,
                    "execution_plan_fingerprint": execution_plan_fingerprint,
                    "execution_plan": authorized_prepared.plan.canonical_material(),
                    "consumption_state": "consumed",
                },
            )
            self._record(
                "orchestration.approval.consumed", request,
                stage=ExecutionStage.POLICY_DECIDED,
                details={
                    "intent_fingerprint": intent_fingerprint,
                    "action_fingerprint": intent_fingerprint,
                    "execution_plan_fingerprint": execution_plan_fingerprint,
                    "consumption_state": "consumed",
                    "replay_result": "new_execution",
                },
            )

            try:
                # Independent re-resolution immediately before provider invocation.
                # Only this second prepared object can reach the provider.
                with governed_execution_deadline_at(provider_deadline_monotonic):
                    prepared_execution = prepare_plan(request=request, resolution=resolution)
                observed_plan_fingerprint = prepared_execution.plan.fingerprint
                contract_error = self._execution_plan_contract_error(
                    request=request, resolution=resolution, plan=prepared_execution.plan
                )
                if contract_error is not None:
                    raise PermissionError(contract_error)
                self._governed_execution_ledger.verify_execution_plan(
                    request, prepared_execution.plan
                )
            except Exception as exc:
                if self._governed_execution_ledger is not None:
                    self._governed_execution_ledger.fail(request, reason="execution_plan_mismatch")
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_mismatch",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="EXECUTION_PLAN_MISMATCH",
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "authorized_execution_plan_fingerprint": execution_plan_fingerprint,
                        "observed_execution_plan_fingerprint": locals().get("observed_plan_fingerprint"),
                        "provider_invoked": False,
                        "message": str(exc),
                    },
                )
                return result

        elif self._external_approval_plan_binding_required(request):
            if not request.authority_allowed or not request.authority_context_id:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("fresh_authority_required",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="AUTHORITY_CONTEXT_REQUIRED",
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "provider_invoked": False,
                        "message": "approval continuation requires fresh authority context",
                    },
                )
                return result

            intent_fingerprint = governed_intent_fingerprint(
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                capability_name=request.capability_name,
                arguments=request.arguments,
            )
            prepare_plan = getattr(self._invoker, "prepare_execution_plan", None)
            invoke_prepared = getattr(self._invoker, "invoke_execution_plan", None)
            if not callable(prepare_plan) or not callable(invoke_prepared):
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_binding_required",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code="EXECUTION_PLAN_BINDING_REQUIRED",
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "provider_invoked": False,
                        "approval_binding": "external_continuation_guard",
                        "message": "approved mutation invoker does not expose governed execution-plan binding",
                    },
                )
                return result

            try:
                provider_deadline_monotonic = self._provider_deadline_monotonic(resolution)
                with governed_execution_deadline_at(provider_deadline_monotonic):
                    authorized_prepared = prepare_plan(request=request, resolution=resolution)
                contract_error = self._execution_plan_contract_error(
                    request=request, resolution=resolution, plan=authorized_prepared.plan
                )
                if contract_error is not None:
                    raise PermissionError(contract_error)
                execution_plan_fingerprint = authorized_prepared.plan.fingerprint
            except Exception as exc:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_authorization_rejected",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code=getattr(exc, "error_code", "EXECUTION_PLAN_AUTHORIZATION_REJECTED"),
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "provider_invoked": False,
                        "approval_binding": "external_continuation_guard",
                        "message": str(exc),
                    },
                )
                return result

            self._record(
                "orchestration.execution_plan.authorized", request,
                stage=ExecutionStage.POLICY_DECIDED,
                details={
                    "intent_fingerprint": intent_fingerprint,
                    "execution_plan_fingerprint": execution_plan_fingerprint,
                    "execution_plan": authorized_prepared.plan.canonical_material(),
                    "consumption_state": "external_guard_consumed",
                    "approval_binding": "external_continuation_guard",
                },
            )

            try:
                with governed_execution_deadline_at(provider_deadline_monotonic):
                    prepared_execution = prepare_plan(request=request, resolution=resolution)
                observed_plan_fingerprint = prepared_execution.plan.fingerprint
                contract_error = self._execution_plan_contract_error(
                    request=request, resolution=resolution, plan=prepared_execution.plan
                )
                if contract_error is not None:
                    raise PermissionError(contract_error)
                if observed_plan_fingerprint != execution_plan_fingerprint:
                    raise PermissionError(
                        "concrete execution plan does not match authorized execution plan"
                    )
            except Exception as exc:
                result = OrchestrationResult(
                    execution_id=request.execution_id,
                    correlation_id=request.correlation_id,
                    capability_name=resolution.capability_name,
                    status=OrchestrationStatus.DENIED,
                    stage=ExecutionStage.DENIED,
                    reason_codes=("execution_plan_mismatch",),
                    resolution=resolution,
                    attempts=0,
                    provider_id=resolution.selected_provider_id,
                    error_code=getattr(exc, "error_code", "EXECUTION_PLAN_MISMATCH"),
                )
                self._record(
                    "orchestration.execution_plan.denied", request,
                    stage=ExecutionStage.DENIED,
                    details={
                        "intent_fingerprint": intent_fingerprint,
                        "authorized_execution_plan_fingerprint": execution_plan_fingerprint,
                        "observed_execution_plan_fingerprint": locals().get("observed_plan_fingerprint"),
                        "provider_invoked": False,
                        "approval_binding": "external_continuation_guard",
                        "message": str(exc),
                    },
                )
                return result

        self._record(
            "orchestration.capability.invoking",
            request,
            stage=ExecutionStage.INVOKING,
            details={
                "provider_id": resolution.selected_provider_id,
                "intent_fingerprint": intent_fingerprint,
                "action_fingerprint": intent_fingerprint,
                "execution_plan_fingerprint": execution_plan_fingerprint,
            },
        )

        invocation_started = monotonic()
        try:
            if prepared_execution is not None:
                assert callable(invoke_prepared)
                with governed_execution_deadline_at(provider_deadline_monotonic):
                    invocation = invoke_prepared(
                        request=request, resolution=resolution, prepared=prepared_execution
                    )
            else:
                invocation = self._invoker.invoke(request=request, resolution=resolution)
        except Exception as exc:
            if request.approval_id is not None and self._governed_execution_ledger is not None:
                self._governed_execution_ledger.fail(request, reason="provider_invocation_failed")
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
                    "intent_fingerprint": intent_fingerprint,
                    "execution_plan_fingerprint": execution_plan_fingerprint,
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

        if request.approval_id is not None and self._governed_execution_ledger is not None:
            self._governed_execution_ledger.complete(request, result)
        details.update({
            "intent_fingerprint": intent_fingerprint,
            "action_fingerprint": intent_fingerprint,
            "execution_plan_fingerprint": execution_plan_fingerprint,
            "replay_result": "executed",
            "consumption_state": (
                "succeeded"
                if request.approval_id is not None
                else (
                    "external_guard_consumed"
                    if self._external_approval_plan_binding_required(request)
                    else "not_applicable"
                )
            ),
        })
        self._record(
            "orchestration.capability.completed",
            request,
            stage=ExecutionStage.COMPLETED,
            details=details,
        )
        return result

    @staticmethod
    def _external_approval_plan_binding_required(
        request: OrchestrationRequest,
    ) -> bool:
        return (
            request.approval_id is None
            and request.approval_present
            and request.orchestration_mode is OrchestrationMode.EXECUTE
        )

    @staticmethod
    def _provider_deadline_monotonic(
        resolution: CapabilityResolutionResult,
    ) -> float | None:
        metadata = getattr(resolution, "metadata", {}) or {}
        declared = metadata.get(_PROVIDER_EXECUTION_SECONDS_METADATA)
        if declared is None:
            return None
        try:
            seconds = float(declared)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "provider maximum execution seconds metadata must be numeric"
            ) from exc
        if seconds <= 0:
            raise ValueError(
                "provider maximum execution seconds metadata must be positive"
            )
        return monotonic() + seconds

    @staticmethod
    def _execution_plan_contract_error(
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
        plan: ExecutionPlan,
    ) -> str | None:
        expected_provider = str(resolution.selected_provider_id or "").strip()
        checks = (
            (plan.principal_id, request.principal_id, "principal_id"),
            (plan.organization_id, request.organization_id, "organization_id"),
            (plan.client_id, request.client_id, "client_id"),
            (plan.canonical_capability, resolution.capability_name, "canonical_capability"),
            (plan.selected_provider_id, expected_provider, "selected_provider_id"),
        )
        for actual, expected, name in checks:
            if actual != expected:
                return f"execution plan {name} does not match governed resolution"
        return None

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
            "approval_id": request.approval_id,
            "idempotency_key": request.idempotency_key,
        }
        payload.update(details or {})
        self._audit.append(event_type, payload)
