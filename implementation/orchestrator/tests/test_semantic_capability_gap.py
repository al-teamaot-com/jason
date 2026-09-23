from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor
from orchestrator.semantic_fulfillment_feasibility import FulfillmentFeasibilityResult


def test_conclusive_infeasible_result_becomes_governed_capability_gap():
    assessment = GovernedSemanticCapabilityGapAssessor().assess(
        feasibility_result=FulfillmentFeasibilityResult(
            conclusive=True,
            feasible=False,
            unsupported_facts=("special governed fact",),
            summary="unsupported",
        )
    )
    assert assessment is not None
    context = assessment.as_context()
    assert context["gap_type"] == "capability_registry_gap"
    assert context["unsupported_facts"] == ("special governed fact",)
    assert context["governance_owner"] == "technology-steward"
    assert "authoritative documentation" in context["recommended_next_action"]


def test_feasible_or_inconclusive_result_does_not_create_gap():
    assessor = GovernedSemanticCapabilityGapAssessor()
    assert assessor.assess(
        feasibility_result=FulfillmentFeasibilityResult(conclusive=False, feasible=False)
    ) is None
    assert assessor.assess(
        feasibility_result=FulfillmentFeasibilityResult(conclusive=True, feasible=True)
    ) is None
