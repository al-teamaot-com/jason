import pytest

from orchestrator.semantic_intent_translation import (
    SemanticIntentTranslation,
)


def test_translation_contains_semantic_fact_obligations_only():
    result = SemanticIntentTranslation(
        requested_concepts=(
            "last logged in user",
        ),
        confidence=0.98,
    )

    assert result.requested_concepts == (
        "last logged in user",
    )
    assert result.operation == "read"


def test_translation_requires_concepts():
    with pytest.raises(
        ValueError,
        match="requested concepts",
    ):
        SemanticIntentTranslation(
            requested_concepts=(),
        )


def test_translation_cannot_authorize_mutation():
    with pytest.raises(
        PermissionError,
        match="only produce read",
    ):
        SemanticIntentTranslation(
            requested_concepts=(
                "open alerts",
            ),
            operation="execute",
        )


@pytest.mark.parametrize(
    "confidence",
    (-0.01, 1.01),
)
def test_invalid_confidence_is_rejected(
    confidence,
):
    with pytest.raises(
        ValueError,
        match="between zero and one",
    ):
        SemanticIntentTranslation(
            requested_concepts=(
                "open alerts",
            ),
            confidence=confidence,
        )
