from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import (
    CostEstimator,
    DataHandlingPolicy,
    DecisionOutcome,
    ExecutionAttemptCost,
    ExecutionBudget,
    ExecutionCandidate,
    ExecutionMode,
    ExecutionPolicyEngine,
    ExecutionRequest,
    ExecutionUsage,
    InMemoryPricingRegistry,
    PriceConfidence,
    PricingEntry,
)


def pricing_registry() -> InMemoryPricingRegistry:
    return InMemoryPricingRegistry(
        [
            PricingEntry(
                provider_id="hosted-a",
                model_id="model-a",
                execution_mode=ExecutionMode.HOSTED_AI,
                input_cost_per_million_tokens=Decimal("2"),
                output_cost_per_million_tokens=Decimal("8"),
                request_cost=Decimal("0.001"),
                pricing_version="hosted-a-2026-08-04",
                confidence=PriceConfidence.HIGH,
            ),
            PricingEntry(
                provider_id="local-a",
                model_id="model-local",
                execution_mode=ExecutionMode.LOCAL_AI,
                input_cost_per_million_tokens=Decimal("0.20"),
                output_cost_per_million_tokens=Decimal("0.40"),
                infrastructure_cost_per_execution=Decimal("0.002"),
                pricing_version="local-a-2026-08-04",
                confidence=PriceConfidence.MEDIUM,
            ),
        ]
    )


def request(
    *candidates: ExecutionCandidate,
    authority_allowed: bool = True,
    hosted_processing_allowed: bool = True,
    maximum_cost: str = "0.10",
) -> ExecutionRequest:
    return ExecutionRequest(
        execution_id="exec_001",
        correlation_id="corr_001",
        capability="operations.ticket.investigate",
        capability_version="0.1",
        tenant_id="tenant_client",
        client_id="client_001",
        requested_mode="recommend",
        authority_allowed=authority_allowed,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="confidential",
            hosted_processing_allowed=hosted_processing_allowed,
            redaction_profile="client-default",
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal(maximum_cost),
            maximum_input_tokens=12000,
            maximum_output_tokens=2000,
            maximum_attempts=2,
        ),
        candidates=candidates,
        policy_ids=("policy-execution-default",),
    )


def engine() -> ExecutionPolicyEngine:
    return ExecutionPolicyEngine(
        cost_estimator=CostEstimator(pricing_registry())
    )


def test_denies_when_authority_is_absent() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.DETERMINISTIC,
                deterministic_quality_sufficient=True,
            ),
            authority_allowed=False,
        )
    )

    assert result.outcome is DecisionOutcome.DENIED
    assert result.reason_codes == ("authority_denied",)
    assert result.plan is None


def test_prefers_quality_sufficient_deterministic_path() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="hosted-a",
                model_id="model-a",
                estimated_input_tokens=1000,
                estimated_output_tokens=250,
            ),
            ExecutionCandidate(
                execution_mode=ExecutionMode.DETERMINISTIC,
                deterministic_quality_sufficient=True,
            ),
        )
    )

    assert result.outcome is DecisionOutcome.ALLOWED
    assert result.execution_mode is ExecutionMode.DETERMINISTIC
    assert result.reason_codes == ("deterministic_first",)
    assert result.plan is not None
    assert result.plan.estimated_cost.total_estimated_cost == Decimal("0")


def test_selects_lowest_cost_compliant_ai_path() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="hosted-a",
                model_id="model-a",
                estimated_input_tokens=4000,
                estimated_output_tokens=500,
            ),
            ExecutionCandidate(
                execution_mode=ExecutionMode.LOCAL_AI,
                provider_id="local-a",
                model_id="model-local",
                estimated_input_tokens=4000,
                estimated_output_tokens=500,
            ),
        )
    )

    assert result.outcome is DecisionOutcome.ALLOWED
    assert result.execution_mode is ExecutionMode.LOCAL_AI
    assert result.plan is not None
    assert result.plan.provider_id == "local-a"


def test_rejects_hosted_ai_when_hosted_processing_is_prohibited() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="hosted-a",
                model_id="model-a",
                estimated_input_tokens=1000,
                estimated_output_tokens=250,
            ),
            hosted_processing_allowed=False,
        )
    )

    assert result.outcome is DecisionOutcome.DENIED
    assert result.reason_codes == ("no_compliant_execution_path",)


def test_budget_blocks_over_cost_execution() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="hosted-a",
                model_id="model-a",
                estimated_input_tokens=12000,
                estimated_output_tokens=2000,
            ),
            maximum_cost="0.001",
        )
    )

    assert result.outcome is DecisionOutcome.DENIED


def test_unknown_pricing_requires_approval() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="unknown",
                model_id="unknown",
                estimated_input_tokens=1000,
                estimated_output_tokens=250,
            )
        )
    )

    assert result.outcome is DecisionOutcome.APPROVAL_REQUIRED
    assert result.reason_codes == ("pricing_unknown",)


def test_human_path_is_selected_when_no_automated_path_is_compliant() -> None:
    result = engine().evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HUMAN,
            )
        )
    )

    assert result.outcome is DecisionOutcome.HUMAN_REQUIRED
    assert result.execution_mode is ExecutionMode.HUMAN


def test_creates_cost_record_with_failover_attempt_attribution() -> None:
    estimator = CostEstimator(pricing_registry())
    decision = ExecutionPolicyEngine(cost_estimator=estimator).evaluate(
        request(
            ExecutionCandidate(
                execution_mode=ExecutionMode.HOSTED_AI,
                provider_id="hosted-a",
                model_id="model-a",
                estimated_input_tokens=1000,
                estimated_output_tokens=250,
            )
        )
    )

    assert decision.plan is not None

    attempts = (
        ExecutionAttemptCost(
            attempt_number=1,
            execution_mode=ExecutionMode.HOSTED_AI,
            provider_id="hosted-a",
            model_id="model-a",
            estimated_cost=Decimal("0.006"),
            status="failed",
            failure_reason="provider_unavailable",
        ),
        ExecutionAttemptCost(
            attempt_number=2,
            execution_mode=ExecutionMode.LOCAL_AI,
            provider_id="local-a",
            model_id="model-local",
            estimated_cost=Decimal("0.003"),
            status="succeeded",
        ),
    )

    record = estimator.create_cost_record(
        plan=decision.plan,
        usage=ExecutionUsage(
            input_tokens=1000,
            output_tokens=250,
            attempts=2,
            execution_seconds=Decimal("8.5"),
        ),
        attempts=attempts,
    )

    assert record.total_estimated_cost == Decimal("0.009")
    assert len(record.attempts) == 2
    assert record.attempts[0].status == "failed"
    assert record.attempts[1].status == "succeeded"
