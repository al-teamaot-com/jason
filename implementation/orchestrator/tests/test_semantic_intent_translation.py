import pytest

from orchestrator.semantic_intent_translation import (
    SemanticIntentTranslation,
)


def test_translation_represents_provider_neutral_read_meaning():
    result = SemanticIntentTranslation(
        resource_type="endpoint",
        resource_selector={
            "hostname": "AOT-50282",
        },
        requested_concepts=(
            "last logged in user",
        ),
        operation="read",
        confidence=0.98,
    )

    assert result.resource_type == "endpoint"
    assert result.resource_selector == {
        "hostname": "AOT-50282",
    }
    assert result.requested_concepts == (
        "last logged in user",
    )


def test_translation_allows_selectorless_bounded_collection_read():
    result = SemanticIntentTranslation(
        resource_type="alert",
        requested_concepts=("alerts",),
        confidence=0.99,
    )

    assert result.resource_selector == {}


def test_translation_cannot_authorize_mutating_operation():
    with pytest.raises(
        PermissionError,
        match="only produce read interpretation",
    ):
        SemanticIntentTranslation(
            resource_type="endpoint",
            requested_concepts=(
                "last logged in user",
            ),
            operation="execute",
        )


@pytest.mark.parametrize(
    "confidence",
    (-0.01, 1.01),
)
def test_translation_rejects_invalid_confidence(
    confidence,
):
    with pytest.raises(
        ValueError,
        match="between zero and one",
    ):
        SemanticIntentTranslation(
            resource_type="endpoint",
            requested_concepts=(
                "last logged in user",
            ),
            confidence=confidence,
        )


def test_translation_requires_bounded_concepts():
    with pytest.raises(
        ValueError,
        match="requested concepts",
    ):
        SemanticIntentTranslation(
            resource_type="endpoint",
            requested_concepts=(),
        )
