from orchestrator.semantic_intent_planning_loop import (
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
)
from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator


def plan(*, expected_evidence=("operating system display version",)):
    return FulfillmentPlanCandidate(
        steps=(
            FulfillmentPlanStepCandidate(
                capability_name="endpoint.device.search",
                purpose="retrieve governed endpoint facts",
                required_facts=("hostname", "operating system"),
                expected_evidence=expected_evidence,
            ),
        ),
        rationale_summary="use governed endpoint discovery",
    )


def context(*fact_hints):
    return {
        "capability_registry": {
            "capability_names": ("endpoint.device.search",),
            "items": (
                {
                    "capability_name": "endpoint.device.search",
                    "fact_hints": ",".join(fact_hints),
                },
            ),
        }
    }


def test_expected_evidence_claim_does_not_make_unsupported_fact_sufficient():
    result = GovernedSemanticPlanSufficiencyValidator().validate(
        intent={"requested_facts": ("operating system display version",)},
        plan=plan(),
        context=context("hostname", "operating system"),
    )
    assert result.sufficient is False
    assert result.issues == (
        "no selected governed capability advertises requested fact: operating system display version",
    )


def test_selected_governed_capability_must_advertise_requested_fact():
    result = GovernedSemanticPlanSufficiencyValidator().validate(
        intent={"requested_facts": ("processor model",)},
        plan=plan(expected_evidence=("processor model",)),
        context=context("hostname", "processor model", "total memory"),
    )
    assert result.sufficient is True
    assert result.issues == ()
