from types import SimpleNamespace

from orchestrator.conversation_experience import (
    _recover_literal_resource_observe_read,
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
