from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from kernel.execution_policy.contracts import (
    CostRecord,
    ExecutionAttemptCost,
    ExecutionCandidate,
    ExecutionCostEstimate,
    ExecutionMode,
    ExecutionPlan,
    ExecutionUsage,
    PriceConfidence,
)
from kernel.execution_policy.registries import InMemoryPricingRegistry


_MILLION = Decimal("1000000")


class CostEstimator:
    def __init__(self, pricing: InMemoryPricingRegistry) -> None:
        self._pricing = pricing

    def estimate(self, candidate: ExecutionCandidate) -> ExecutionCostEstimate:
        if candidate.fixed_estimated_cost is not None:
            return ExecutionCostEstimate(
                provider_cost=candidate.fixed_estimated_cost,
                internal_compute_cost=Decimal("0"),
                infrastructure_cost=Decimal("0"),
                operational_cost=Decimal("0"),
                total_estimated_cost=candidate.fixed_estimated_cost,
                currency="USD",
                pricing_version="fixed-estimate",
                confidence=PriceConfidence.MEDIUM,
                limitations=("Fixed estimate supplied by execution candidate.",),
            )

        if candidate.execution_mode in {
            ExecutionMode.DETERMINISTIC,
            ExecutionMode.HUMAN,
        }:
            return ExecutionCostEstimate(
                provider_cost=Decimal("0"),
                internal_compute_cost=Decimal("0"),
                infrastructure_cost=Decimal("0"),
                operational_cost=Decimal("0"),
                total_estimated_cost=Decimal("0"),
                currency="USD",
                pricing_version="zero-cost-foundation",
                confidence=PriceConfidence.LOW,
                limitations=(
                    "Foundation implementation does not yet price deterministic or human execution.",
                ),
            )

        if not candidate.provider_id or not candidate.model_id:
            return self._unknown("AI candidate is missing provider or model identity.")

        entry = self._pricing.get(
            provider_id=candidate.provider_id,
            model_id=candidate.model_id,
            execution_mode=candidate.execution_mode,
        )
        if entry is None:
            return self._unknown("No active pricing entry exists for this execution path.")

        input_cost = (
            Decimal(candidate.estimated_input_tokens)
            / _MILLION
            * entry.input_cost_per_million_tokens
        )
        output_cost = (
            Decimal(candidate.estimated_output_tokens)
            / _MILLION
            * entry.output_cost_per_million_tokens
        )
        provider_cost = (
            input_cost + output_cost + entry.request_cost
        ) * Decimal(candidate.estimated_attempts)
        infrastructure_cost = (
            entry.infrastructure_cost_per_execution
            * Decimal(candidate.estimated_attempts)
        )
        total = provider_cost + infrastructure_cost

        return ExecutionCostEstimate(
            provider_cost=provider_cost,
            internal_compute_cost=Decimal("0"),
            infrastructure_cost=infrastructure_cost,
            operational_cost=Decimal("0"),
            total_estimated_cost=total,
            currency=entry.currency,
            pricing_version=entry.pricing_version,
            confidence=entry.confidence,
        )

    def calculate_token_usage_cost(
        self,
        *,
        provider_id: str,
        model_id: str,
        execution_mode: ExecutionMode,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> ExecutionCostEstimate:
        """Calculate post-execution cost from measured provider token usage."""

        if input_tokens < 0 or output_tokens < 0 or cached_input_tokens < 0:
            raise ValueError("measured token usage must be non-negative")
        if cached_input_tokens > input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")

        entry = self._pricing.get(
            provider_id=provider_id,
            model_id=model_id,
            execution_mode=execution_mode,
        )
        if entry is None:
            return self._unknown(
                "No active pricing entry exists for measured execution usage."
            )

        uncached_input_tokens = input_tokens - cached_input_tokens

        input_cost = (
            Decimal(uncached_input_tokens)
            / _MILLION
            * entry.input_cost_per_million_tokens
        )
        cached_input_cost = (
            Decimal(cached_input_tokens)
            / _MILLION
            * entry.cached_input_cost_per_million_tokens
        )
        output_cost = (
            Decimal(output_tokens)
            / _MILLION
            * entry.output_cost_per_million_tokens
        )

        provider_cost = (
            input_cost
            + cached_input_cost
            + output_cost
            + entry.request_cost
        )

        return ExecutionCostEstimate(
            provider_cost=provider_cost,
            internal_compute_cost=Decimal("0"),
            infrastructure_cost=Decimal("0"),
            operational_cost=Decimal("0"),
            total_estimated_cost=provider_cost,
            currency=entry.currency,
            pricing_version=entry.pricing_version,
            confidence=entry.confidence,
            limitations=(),
        )

    def create_cost_record(
        self,
        *,
        plan: ExecutionPlan,
        usage: ExecutionUsage,
        attempts: tuple[ExecutionAttemptCost, ...] = (),
    ) -> CostRecord:
        total_attempt_cost = sum(
            (attempt.estimated_cost for attempt in attempts),
            Decimal("0"),
        )
        estimated = plan.estimated_cost
        total = (
            total_attempt_cost
            if attempts
            else estimated.total_estimated_cost
        )

        return CostRecord(
            cost_record_id=f"cost_{uuid4().hex}",
            execution_id=plan.execution_id,
            correlation_id=plan.correlation_id,
            tenant_id=plan.tenant_id,
            client_id=plan.client_id,
            capability=plan.capability,
            execution_mode=plan.execution_mode,
            provider_id=plan.provider_id,
            model_id=plan.model_id,
            usage=usage,
            provider_cost=estimated.provider_cost,
            internal_compute_cost=estimated.internal_compute_cost,
            infrastructure_cost=estimated.infrastructure_cost,
            operational_cost=estimated.operational_cost,
            total_estimated_cost=total,
            currency=estimated.currency,
            pricing_version=estimated.pricing_version,
            confidence=estimated.confidence,
            attempts=attempts,
            limitations=estimated.limitations,
        )

    @staticmethod
    def _unknown(reason: str) -> ExecutionCostEstimate:
        return ExecutionCostEstimate(
            provider_cost=Decimal("0"),
            internal_compute_cost=Decimal("0"),
            infrastructure_cost=Decimal("0"),
            operational_cost=Decimal("0"),
            total_estimated_cost=Decimal("0"),
            currency="USD",
            pricing_version="unknown",
            confidence=PriceConfidence.UNKNOWN,
            limitations=(reason,),
        )
