import pytest

from orchestrator.provider_corroborating_evidence_review import CorroboratingEvidence
from orchestrator.provider_semantic_mapping_proposal import (
    GovernedCrossSourceSemanticMappingProposer,
)
from orchestrator.provider_semantic_statement import (
    AuthoritativeSemanticStatement,
)


def evidence():
    return CorroboratingEvidence(
        provider_id="example_provider",
        unsupported_fact="operating system display version",
        documented_schema="Device",
        documented_field="displayVersion",
        schema_description="Device data",
        field_description=None,
        field_type="string",
        field_example=None,
        field_default=None,
        field_enum=(),
        sibling_fields=("operatingSystem",),
        read_only_operations=("GET /v2/device/{id}",),
        source_reference="openapi:sha256:test#Device/displayVersion",
        semantic_proof=False,
    )


def statement():
    return AuthoritativeSemanticStatement(
        provider_id="example_provider",
        canonical_fact="operating system display version",
        vendor_term="Windows Display Version",
        statement=(
            'Windows Display Version displays the "friendly name" used to '
            "identify the current build of Windows 10 devices."
        ),
        source_reference="help:sha256:test",
    )


def test_cross_source_evidence_can_create_unapproved_proposal():
    proposal = GovernedCrossSourceSemanticMappingProposer().propose(
        structural_evidence=evidence(),
        semantic_statement=statement(),
    )

    assert proposal.provider_field == "displayVersion"
    assert proposal.approved is False
    assert proposal.active is False
    assert proposal.proposal_status == "pending_technology_steward_review"


def test_provider_mismatch_fails_closed():
    bad = AuthoritativeSemanticStatement(
        provider_id="different_provider",
        canonical_fact="operating system display version",
        vendor_term="Windows Display Version",
        statement="authoritative definition",
        source_reference="help:test",
    )

    with pytest.raises(PermissionError):
        GovernedCrossSourceSemanticMappingProposer().propose(
            structural_evidence=evidence(),
            semantic_statement=bad,
        )


def test_fact_mismatch_fails_closed():
    bad = AuthoritativeSemanticStatement(
        provider_id="example_provider",
        canonical_fact="bios version",
        vendor_term="BIOS Version",
        statement="authoritative definition",
        source_reference="help:test",
    )

    with pytest.raises(PermissionError):
        GovernedCrossSourceSemanticMappingProposer().propose(
            structural_evidence=evidence(),
            semantic_statement=bad,
        )
