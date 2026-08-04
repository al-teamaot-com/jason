from __future__ import annotations

from kernel.execution_policy.contracts import (
    DecisionOutcome,
    ExecutionCandidate,
    ExecutionDecision,
    ExecutionMode,
    ExecutionPlan,
    ExecutionRequest,
    PriceConfidence,
)
from kernel.execution_policy.costing import CostEstimator


class ExecutionPolicyEngine:
    def __init__(self, *, cost_estimator: CostEstimator) -> None:
        self._cost_estimator = cost_estimator

    def evaluate(self, request: ExecutionRequest) -> ExecutionDecision:
        if not request.authority_allowed:
            return self._decision(
                request=request,
                outcome=DecisionOutcome.DENIED,
                execution_mode=ExecutionMode.NONE,
                reason_codes=("authority_denied",),
            )

        candidates = [
            candidate
            for candidate in request.candidates
            if candidate.approved
            and candidate.healthy
            and self._classification_supported(request, candidate)
            and self._hosted_processing_allowed(request, candidate)
            and candidate.estimated_attempts <= request.budget.maximum_attempts
        ]

        deterministic = [
            candidate
            for candidate in candidates
            if candidate.execution_mode is ExecutionMode.DETERMINISTIC
            and candidate.deterministic_quality_sufficient
        ]

        if deterministic:
            return self._allow(request, deterministic[0], ("deterministic_first",))

        priced: list[tuple[ExecutionCandidate, object]] = []
        unknown_pricing = False

        for candidate in candidates:
            if candidate.execution_mode is ExecutionMode.HUMAN:
                continue

            estimate = self._cost_estimator.estimate(candidate)
            if estimate.confidence is PriceConfidence.UNKNOWN:
                unknown_pricing = True
                continue
            if (
                candidate.estimated_input_tokens
                > request.budget.maximum_input_tokens
            ):
                continue
            if (
                candidate.estimated_output_tokens
                > request.budget.maximum_output_tokens
            ):
                continue
            if (
                estimate.total_estimated_cost
                > request.budget.maximum_estimated_cost
            ):
                continue
            priced.append((candidate, estimate))

        if priced:
            priced.sort(key=lambda item: item[1].total_estimated_cost)
            candidate, estimate = priced[0]
            return self._allow(
                request,
                candidate,
                ("lowest_cost_compliant_path",),
                estimate=estimate,
            )

        human = next(
            (
                candidate
                for candidate in candidates
                if candidate.execution_mode is ExecutionMode.HUMAN
            ),
            None,
        )
        if human is not None:
            return self._decision(
                request=request,
                outcome=DecisionOutcome.HUMAN_REQUIRED,
                execution_mode=ExecutionMode.HUMAN,
                reason_codes=("no_compliant_automated_path",),
            )

        if unknown_pricing:
            return self._decision(
                request=request,
                outcome=DecisionOutcome.APPROVAL_REQUIRED,
                execution_mode=ExecutionMode.NONE,
                reason_codes=("pricing_unknown",),
            )

        return self._decision(
            request=request,
            outcome=DecisionOutcome.DENIED,
            execution_mode=ExecutionMode.NONE,
            reason_codes=("no_compliant_execution_path",),
        )

    def _allow(
        self,
        request: ExecutionRequest,
        candidate: ExecutionCandidate,
        reason_codes: tuple[str, ...],
        *,
        estimate=None,
    ) -> ExecutionDecision:
        estimate = estimate or self._cost_estimator.estimate(candidate)

        plan = ExecutionPlan(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability=request.capability,
            capability_version=request.capability_version,
            execution_mode=candidate.execution_mode,
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            provider_id=candidate.provider_id,
            model_id=candidate.model_id,
            region=candidate.region,
            budget=request.budget,
            data_handling=request.data_handling,
            estimated_cost=estimate,
            maximum_attempts=request.budget.maximum_attempts,
            policy_ids=request.policy_ids,
        )

        return ExecutionDecision(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            outcome=DecisionOutcome.ALLOWED,
            execution_mode=candidate.execution_mode,
            reason_codes=reason_codes,
            policy_ids=request.policy_ids,
            plan=plan,
        )

    @staticmethod
    def _classification_supported(
        request: ExecutionRequest,
        candidate: ExecutionCandidate,
    ) -> bool:
        if not candidate.supports_classifications:
            return True
        return (
            request.data_handling.classification
            in candidate.supports_classifications
        )

    @staticmethod
    def _hosted_processing_allowed(
        request: ExecutionRequest,
        candidate: ExecutionCandidate,
    ) -> bool:
        if candidate.execution_mode is not ExecutionMode.HOSTED_AI:
            return True
        return request.data_handling.hosted_processing_allowed

    @staticmethod
    def _decision(
        *,
        request: ExecutionRequest,
        outcome: DecisionOutcome,
        execution_mode: ExecutionMode,
        reason_codes: tuple[str, ...],
    ) -> ExecutionDecision:
        return ExecutionDecision(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            outcome=outcome,
            execution_mode=execution_mode,
            reason_codes=reason_codes,
            policy_ids=request.policy_ids,
            plan=None,
        )
