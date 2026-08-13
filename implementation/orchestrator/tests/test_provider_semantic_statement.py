import pytest

from orchestrator.provider_documentation_reader import (
    ProviderDocumentationSourceRecord,
)
from orchestrator.provider_semantic_statement import (
    GovernedSemanticStatementExtractor,
    SemanticStatementQuery,
)


def source(text):
    return ProviderDocumentationSourceRecord(
        provider_id="example_provider",
        documentation_source="Example documentation",
        source_reference="example:sha256:test",
        content=text,
    )


def test_generic_extractor_uses_governed_query_not_provider_specific_method():
    result = GovernedSemanticStatementExtractor().extract(
        source=source(
            "Release Name The friendly name used for supported operating systems."
        ),
        query=SemanticStatementQuery(
            canonical_fact="operating system release name",
            vendor_term="Release Name",
            required_phrases=("friendly name", "operating systems"),
        ),
    )

    assert result.canonical_fact == "operating system release name"
    assert result.vendor_term == "Release Name"
    assert result.semantic_mapping_approved is False


def test_generic_extractor_fails_when_required_evidence_is_missing():
    with pytest.raises(ValueError):
        GovernedSemanticStatementExtractor().extract(
            source=source("Release Name is shown here."),
            query=SemanticStatementQuery(
                canonical_fact="operating system release name",
                vendor_term="Release Name",
                required_phrases=("friendly name",),
            ),
        )
