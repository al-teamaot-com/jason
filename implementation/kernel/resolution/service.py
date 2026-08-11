from __future__ import annotations

from kernel.capabilities import (
    CapabilityDefinition,
    CapabilityLifecycle,
    CapabilityNotFoundError,
    CapabilityRegistryService,
)
from kernel.execution_policy import (
    DecisionOutcome,
    ExecutionDecision,
    ExecutionPolicyEngine,
    ExecutionRequest,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderCandidateQuery,
)
from kernel.resolution.contracts import (
    CapabilityResolutionRequest,
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from kernel.resolution.translators import ProviderCandidateTranslator


class GovernedCapabilityResolutionEngine:
    """Resolve capability requests without executing provider work."""

    def __init__(
        self,
        *,
        capabilities: CapabilityRegistryService,
        providers: ExecutionProviderRegistryService,
        policy: ExecutionPolicyEngine,
        translator: ProviderCandidateTranslator | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._providers = providers
        self._policy = policy
        self._translator = translator or ProviderCandidateTranslator()

    def resolve(self, request: CapabilityResolutionRequest) -> CapabilityResolutionResult:
        capability, status = self._resolve_capability(request)

        if capability is None:
            return self._unresolved(
                request=request,
                status=status,
                reason_codes=("capability_not_found",),
            )

        validation_result = self._validate_capability(
            request=request,
            capability=capability,
            status=status,
        )
        if validation_result is not None:
            return validation_result

        context_result = self._validate_context(
            request=request,
            capability=capability,
            status=status,
        )
        if context_result is not None:
            return context_result

        if capability.idempotency_key_required and request.idempotency_key is None:
            return self._unresolved(
                request=request,
                capability=capability,
                status=CapabilityResolutionStatus.IDEMPOTENCY_KEY_MISSING,
                reason_codes=("idempotency_key_required",),
            )

        if capability.approval.required and not request.approval_present:
            return CapabilityResolutionResult(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=capability.capability_name,
                capability_version=capability.version,
                outcome=ResolutionOutcome.APPROVAL_REQUIRED,
                capability_status=status,
                reason_codes=("capability_approval_required",),
                audit_required=True,
            )

        providers = self._find_candidate_providers(request=request, capability=capability)

        if not providers:
            return self._unresolved(
                request=request,
                capability=capability,
                status=status,
                reason_codes=("no_eligible_provider",),
            )

        candidates = self._translator.translate_all(
            providers,
            requested_mode=request.requested_mode,
            requested_region=request.region,
        )

        policy_request = ExecutionRequest(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability=capability.capability_name,
            capability_version=capability.version,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            requested_mode=request.requested_mode,
            authority_allowed=request.authority_allowed,
            approval_present=request.approval_present,
            risk=request.risk,
            data_handling=request.data_handling,
            budget=request.budget,
            candidates=candidates,
            policy_ids=request.policy_ids,
        )

        decision = self._policy.evaluate(policy_request)

        return self._build_policy_result(
            request=request,
            capability=capability,
            status=status,
            providers=providers,
            decision=decision,
        )

    def _resolve_capability(
        self,
        request: CapabilityResolutionRequest,
    ) -> tuple[CapabilityDefinition | None, CapabilityResolutionStatus]:
        try:
            if request.capability_version is not None:
                capability = self._capabilities.get(
                    capability_name=request.capability_name,
                    version=request.capability_version,
                )
                return capability, CapabilityResolutionStatus.RESOLVED_EXACT

            capability = self._capabilities.get_current(
                capability_name=request.capability_name,
                allow_pilot=request.allow_pilot_capability,
            )
            return capability, CapabilityResolutionStatus.RESOLVED_CURRENT
        except CapabilityNotFoundError:
            return None, CapabilityResolutionStatus.NOT_FOUND

    def _validate_capability(
        self,
        *,
        request: CapabilityResolutionRequest,
        capability: CapabilityDefinition,
        status: CapabilityResolutionStatus,
    ) -> CapabilityResolutionResult | None:
        eligible_lifecycles = {CapabilityLifecycle.ACTIVE}
        if request.allow_pilot_capability:
            eligible_lifecycles.add(CapabilityLifecycle.PILOT)

        if capability.lifecycle_status not in eligible_lifecycles:
            return self._unresolved(
                request=request,
                capability=capability,
                status=CapabilityResolutionStatus.INELIGIBLE_LIFECYCLE,
                reason_codes=("capability_lifecycle_ineligible",),
            )

        if request.requested_mode not in capability.permitted_execution_modes:
            return self._unresolved(
                request=request,
                capability=capability,
                status=CapabilityResolutionStatus.EXECUTION_MODE_PROHIBITED,
                reason_codes=("execution_mode_prohibited",),
            )

        return None

    def _validate_context(
        self,
        *,
        request: CapabilityResolutionRequest,
        capability: CapabilityDefinition,
        status: CapabilityResolutionStatus,
    ) -> CapabilityResolutionResult | None:
        if capability.tenant_isolation_required and not request.tenant_id.strip():
            return self._unresolved(
                request=request,
                capability=capability,
                status=CapabilityResolutionStatus.ISOLATION_CONTEXT_MISSING,
                reason_codes=("tenant_context_required",),
            )

        if capability.client_isolation_required and (
            request.client_id is None or not request.client_id.strip()
        ):
            return self._unresolved(
                request=request,
                capability=capability,
                status=CapabilityResolutionStatus.ISOLATION_CONTEXT_MISSING,
                reason_codes=("client_context_required",),
            )

        return None

    def _find_candidate_providers(
        self,
        *,
        request: CapabilityResolutionRequest,
        capability: CapabilityDefinition,
    ) -> tuple[ExecutionProvider, ...]:
        return self._providers.find_candidates(
            ProviderCandidateQuery(
                capability=capability.capability_name,
                execution_mode=request.requested_mode,
                classification=request.data_handling.classification,
                region=request.region,
                allow_pilot=request.allow_pilot_provider,
            )
        )

    def _build_policy_result(
        self,
        *,
        request: CapabilityResolutionRequest,
        capability: CapabilityDefinition,
        status: CapabilityResolutionStatus,
        providers: tuple[ExecutionProvider, ...],
        decision: ExecutionDecision,
    ) -> CapabilityResolutionResult:
        outcome = self._resolution_outcome(decision.outcome)
        plan = decision.plan
        selected_provider_id = plan.provider_id if plan is not None else None

        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=capability.capability_name,
            capability_version=capability.version,
            outcome=outcome,
            capability_status=status,
            reason_codes=decision.reason_codes,
            eligible_provider_ids=tuple(provider.provider_id for provider in providers),
            selected_provider_id=selected_provider_id,
            execution_decision=decision,
            execution_plan=plan,
            audit_required=decision.audit_required,
        )

    @staticmethod
    def _resolution_outcome(outcome: DecisionOutcome) -> ResolutionOutcome:
        if outcome in {DecisionOutcome.ALLOWED, DecisionOutcome.ALLOWED_LIMITED}:
            return ResolutionOutcome.RESOLVED
        if outcome is DecisionOutcome.APPROVAL_REQUIRED:
            return ResolutionOutcome.APPROVAL_REQUIRED
        if outcome is DecisionOutcome.HUMAN_REQUIRED:
            return ResolutionOutcome.HUMAN_REQUIRED
        return ResolutionOutcome.DENIED

    @staticmethod
    def _unresolved(
        *,
        request: CapabilityResolutionRequest,
        status: CapabilityResolutionStatus,
        reason_codes: tuple[str, ...],
        capability: CapabilityDefinition | None = None,
    ) -> CapabilityResolutionResult:
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version=(
                capability.version if capability is not None else request.capability_version
            ),
            outcome=ResolutionOutcome.UNRESOLVED,
            capability_status=status,
            reason_codes=reason_codes,
            audit_required=True,
        )
