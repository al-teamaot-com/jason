from orchestrator.semantic_fulfillment_feasibility import (
    GovernedSemanticFulfillmentFeasibilityGate,
)


def test_feasibility_is_not_conclusive_until_governed_views_are_present():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("special fact",)},
        context={"capability_registry": {"items": ()}},
    )
    assert result.conclusive is False


def test_feasibility_fails_closed_when_all_governed_views_lack_requested_fact():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("special fact",)},
        context={
            "capability_registry": {"items": ({"fact_hints": "hostname"},)},
            "evidence_catalog": {"items": ({"fact_hints": "operating system"},)},
            "derivation_registry": {"items": ({"relationship_id": "endpoint.belongs_to.organization"},)},
        },
    )
    assert result.conclusive is True
    assert result.feasible is False
    assert result.unsupported_facts == ("special fact",)
    assert "special fact" in str(result.summary)


def test_feasibility_remains_possible_when_governed_context_supports_requested_fact():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("processor model",)},
        context={
            "capability_registry": {"items": ({"fact_hints": "hostname,processor model"},)},
            "evidence_catalog": {"items": ()},
            "derivation_registry": {"items": ()},
        },
    )
    assert result.conclusive is True
    assert result.feasible is True
