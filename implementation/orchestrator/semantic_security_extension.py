from __future__ import annotations

from .semantic_knowledge_registry import (
    SemanticConcept,
    SemanticKnowledgeRegistry,
    SemanticLifecycleState,
    SemanticProvenance,
    SemanticTermBinding,
)


def _activate_concept(
    registry: SemanticKnowledgeRegistry,
    concept_id: str,
) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_concept(concept_id, state)


def _activate_term(
    registry: SemanticKnowledgeRegistry,
    *,
    term: str,
) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_term(
            term=term,
            scope="global",
            target=state,
        )


def extend_trusted_security_semantics(
    registry: SemanticKnowledgeRegistry,
) -> SemanticKnowledgeRegistry:
    """Add security facts whose meaning must remain provider-neutral.

    The concepts describe what a human may ask about. They do not authorize a
    provider, capability, credential, secret disclosure, or execution path.

    ``bitlocker recovery key`` is intentionally semantic knowledge only. No
    general endpoint-read capability declares coverage for that secret-like fact,
    so recognizing the phrase cannot by itself authorize recovery-key retrieval.
    """

    provenance = SemanticProvenance(
        source="project-jason-security-semantics",
        evidence=(
            "governed semantic distinction between BitLocker operational state "
            "and BitLocker recovery material; Datto RMM UDFs are treated as "
            "plain-text provider evidence rather than credential authority"
        ),
    )

    concepts = (
        SemanticConcept(
            concept_id="security.bitlocker.status",
            canonical_label="bitlocker status",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("bitlocker", "udf"),
            provenance=provenance,
            review_interval_days=90,
            retirement_criteria=(
                "retire when superseded by a governed endpoint-encryption "
                "status concept with equivalent or stronger evidence semantics"
            ),
        ),
        SemanticConcept(
            concept_id="security.bitlocker.recovery_key",
            canonical_label="bitlocker recovery key",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("bitlocker", "recovery"),
            provenance=provenance,
            review_interval_days=90,
            retirement_criteria=(
                "retire when recovery material is represented by a dedicated "
                "governed secret/recovery-material model"
            ),
        ),
    )

    for concept in concepts:
        registry.add_concept(concept)
        _activate_concept(registry, concept.concept_id)

    terms = {
        "security.bitlocker.status": (
            "bitlocker status",
            "bitlocker state",
            "bitlocker encryption status",
            "bitlocker udf status",
        ),
        "security.bitlocker.recovery_key": (
            "bitlocker recovery key",
            "bitlocker recovery code",
            "bitlocker unlock code",
            "bitlocker unlock key",
        ),
    }

    for concept_id, aliases in terms.items():
        for term in aliases:
            registry.add_term(
                SemanticTermBinding(
                    term=term,
                    concept_id=concept_id,
                    provenance=provenance,
                )
            )
            _activate_term(registry, term=term)

    return registry
