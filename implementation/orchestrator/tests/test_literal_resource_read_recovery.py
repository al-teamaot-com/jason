from types import SimpleNamespace

from orchestrator.conversation_experience import (
    _enrich_literal_resource_selector,
    _recover_literal_resource_observe_read,
)
from orchestrator.conversation_kernel import (
    ConversationKernelDecision,
    InformationNeed,
    InformationTarget,
)


def inquiry(
    *,
    resource_type="printer",
    selector=None,
    permission_mode="observe",
    execution_mode="deterministic",
):
    return SimpleNamespace(
        resource_type=resource_type,
        resource_selector=selector or {"asset_tag": "PRINT-12"},
        permission_mode=permission_mode,
        execution_mode=execution_mode,
        completeness_requirement="sufficient",
    )


def test_unseen_literal_resource_preserves_original_human_question():
    decision = _recover_literal_resource_observe_read(
        text="What arbitrary maintenance state does PRINT-12 report?",
        inquiry=inquiry(),
    )

    assert decision is not None
    assert decision.outcome == "information"
    assert len(decision.information_needs) == 1

    need = decision.information_needs[0]
    assert need.target.kind == "printer"
    assert need.target.source == "literal"
    assert need.target.reference == "PRINT-12"
    assert need.target.selector == "asset_tag"
    assert need.authority == "observe"
    assert need.need == "What arbitrary maintenance state does PRINT-12 report?"


def test_compound_selector_fails_closed_instead_of_choosing_one():
    decision = _recover_literal_resource_observe_read(
        text="Inspect PRINT-12.",
        inquiry=inquiry(
            selector={
                "asset_tag": "PRINT-12",
                "site": "WEST",
            }
        ),
    )

    assert decision is None


def test_non_observe_resource_inquiry_cannot_enter_recovery():
    decision = _recover_literal_resource_observe_read(
        text="Change PRINT-12.",
        inquiry=inquiry(permission_mode="execute"),
    )

    assert decision is None


class ResourceInterpreter:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def interpret(self, *, text, principal):
        self.calls += 1
        return self.result


def kernel_decision(reference="NODE-77", kind="endpoint"):
    return ConversationKernelDecision(
        outcome="information",
        information_needs=(
            InformationNeed(
                target=InformationTarget(
                    kind=kind,
                    source="literal",
                    reference=reference,
                ),
                need="arbitrary state",
                authority="observe",
            ),
        ),
    )


def test_successful_kernel_literal_is_enriched_with_agreed_selector():
    interpreter = ResourceInterpreter(
        inquiry(
            resource_type="endpoint",
            selector={"hostname": "NODE-77"},
        )
    )

    decision = _enrich_literal_resource_selector(
        decision=kernel_decision(),
        text="Inspect NODE-77.",
        principal=object(),
        resource_interpreter=interpreter,
    )

    target = decision.information_needs[0].target
    assert target.reference == "NODE-77"
    assert target.kind == "endpoint"
    assert target.selector == "hostname"
    assert interpreter.calls == 1


def test_selector_enrichment_cannot_rewrite_kernel_target():
    interpreter = ResourceInterpreter(
        inquiry(
            resource_type="endpoint",
            selector={"hostname": "OTHER-NODE"},
        )
    )

    original = kernel_decision()

    decision = _enrich_literal_resource_selector(
        decision=original,
        text="Inspect NODE-77.",
        principal=object(),
        resource_interpreter=interpreter,
    )

    assert decision == original
    assert decision.information_needs[0].target.selector is None


def test_selector_enrichment_rejects_resource_kind_disagreement():
    interpreter = ResourceInterpreter(
        inquiry(
            resource_type="printer",
            selector={"hostname": "NODE-77"},
        )
    )

    original = kernel_decision()

    decision = _enrich_literal_resource_selector(
        decision=original,
        text="Inspect NODE-77.",
        principal=object(),
        resource_interpreter=interpreter,
    )

    assert decision == original
    assert decision.information_needs[0].target.selector is None
