import pytest

from orchestrator.provider_documentation_reader import (
    GovernedProviderDocumentationReader,
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)
from orchestrator.provider_documentation_review import (
    ProviderDocumentationReviewTarget,
)


def target():
    return ProviderDocumentationReviewTarget(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        unsupported_facts=("special governed fact",),
        resource_authority="managed_endpoint",
        connector_id="example_connector",
    )


def test_reader_returns_candidate_evidence_without_semantic_proof():
    class SourceReader:
        def read(self, *, target):
            return (
                ProviderDocumentationSourceRecord(
                    provider_id=target.provider_id,
                    documentation_source=target.documentation_source,
                    source_reference="operation:getExample",
                    content="Example documented field: exampleVersion",
                ),
            )

    class Interpreter:
        def interpret(self, *, target, source):
            return (
                ProviderDocumentationCandidateFinding(
                    provider_id=target.provider_id,
                    documentation_source=target.documentation_source,
                    source_reference=source.source_reference,
                    unsupported_fact="special governed fact",
                    documented_operation="getExample",
                    documented_field="exampleVersion",
                    relevance="possibly_relevant",
                    semantic_proof=False,
                    ambiguity_summary=(
                        "Field name appears relevant, but documentation does not establish "
                        "semantic equivalence to the requested fact."
                    ),
                ),
            )

    result = GovernedProviderDocumentationReader(
        source_reader=SourceReader(),
        interpreter=Interpreter(),
    ).read(target=target())

    assert result.review_only is True
    assert result.governance_owner == "technology-steward"
    assert len(result.findings) == 1
    assert result.findings[0].documented_field == "exampleVersion"
    assert result.findings[0].semantic_proof is False
    assert "does not establish semantic equivalence" in result.interpretation_rule


def test_candidate_finding_cannot_claim_semantic_proof():
    with pytest.raises(PermissionError):
        ProviderDocumentationCandidateFinding(
            provider_id="example_provider",
            documentation_source="Example Provider API documentation",
            source_reference="field:exampleVersion",
            unsupported_fact="special governed fact",
            documented_field="exampleVersion",
            relevance="candidate_evidence",
            semantic_proof=True,
        )


def test_reader_rejects_source_outside_governed_provider_target():
    class SourceReader:
        def read(self, *, target):
            return (
                ProviderDocumentationSourceRecord(
                    provider_id="different_provider",
                    documentation_source=target.documentation_source,
                    source_reference="field:test",
                    content="test",
                ),
            )

    class Interpreter:
        def interpret(self, *, target, source):
            return ()

    reader = GovernedProviderDocumentationReader(
        source_reader=SourceReader(),
        interpreter=Interpreter(),
    )

    with pytest.raises(PermissionError):
        reader.read(target=target())


def test_reader_rejects_findings_for_unrequested_fact():
    class SourceReader:
        def read(self, *, target):
            return (
                ProviderDocumentationSourceRecord(
                    provider_id=target.provider_id,
                    documentation_source=target.documentation_source,
                    source_reference="field:test",
                    content="test",
                ),
            )

    class Interpreter:
        def interpret(self, *, target, source):
            return (
                ProviderDocumentationCandidateFinding(
                    provider_id=target.provider_id,
                    documentation_source=target.documentation_source,
                    source_reference=source.source_reference,
                    unsupported_fact="different fact",
                    documented_field="test",
                    relevance="possibly_relevant",
                ),
            )

    reader = GovernedProviderDocumentationReader(
        source_reader=SourceReader(),
        interpreter=Interpreter(),
    )

    with pytest.raises(PermissionError):
        reader.read(target=target())


def test_reader_does_not_create_mapping_registration_or_execution_authority():
    result = ProviderDocumentationCandidateFinding(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference="field:test",
        unsupported_fact="special governed fact",
        documented_field="test",
        relevance="semantically_ambiguous",
    ).as_context()

    forbidden = {
        "capability_registration",
        "semantic_mapping",
        "derivation",
        "provider_selection",
        "execution_authority",
        "credential",
    }

    assert forbidden.isdisjoint(result)
