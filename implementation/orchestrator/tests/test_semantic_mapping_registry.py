import json
from pathlib import Path

import pytest

from orchestrator.semantic_mapping_approval import (
    GovernedSemanticMappingApprover,
    SemanticMappingApprovalDecision,
)
from orchestrator.semantic_mapping_registry import (
    ApprovedSemanticMapping,
    JsonSemanticMappingRegistryLoader,
    SemanticMappingRegistry,
)
from orchestrator.provider_semantic_mapping_proposal import (
    SemanticMappingProposal,
)


def proposal():
    return SemanticMappingProposal(
        provider_id="example_provider",
        canonical_fact="example canonical fact",
        provider_schema="Example",
        provider_field="exampleField",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
    )


def test_approval_creates_active_versioned_mapping():
    mapping = GovernedSemanticMappingApprover().approve(
        proposal=proposal(),
        decision=SemanticMappingApprovalDecision(
            decision="approve",
            approver="project-owner",
            authority_role="technology-steward",
            decision_basis="cross-source authoritative evidence",
        ),
        mapping_id="example-mapping",
        version=1,
        resource_authority="example_resource",
        capability_names=("endpoint.device.read",),
    )

    assert mapping.active is True
    assert mapping.approval_status == "approved"
    assert mapping.version == 1


def test_non_steward_cannot_approve_mapping():
    with pytest.raises(PermissionError):
        GovernedSemanticMappingApprover().approve(
            proposal=proposal(),
            decision=SemanticMappingApprovalDecision(
                decision="approve",
                approver="someone",
                authority_role="operator",
                decision_basis="test",
            ),
            mapping_id="example",
            version=1,
            resource_authority="example",
            capability_names=("endpoint.device.read",),
        )


def test_registry_resolves_active_mapping_by_fact_and_authority():
    mapping = ApprovedSemanticMapping(
        mapping_id="example",
        version=1,
        provider_id="example_provider",
        canonical_fact="example fact",
        provider_schema="Example",
        provider_field="exampleField",
        resource_authority="example_resource",
        approval_status="approved",
        approved_by="project-owner",
        approval_basis="test",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=("endpoint.device.read",),
        active=True,
    )

    resolved = SemanticMappingRegistry((mapping,)).resolve_active(
        canonical_fact="example fact",
        resource_authority="example_resource",
    )

    assert resolved.provider_field == "exampleField"


def test_loader_reads_machine_readable_registry(tmp_path):
    path = tmp_path / "approved.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mappings": [
                    {
                        "mapping_id": "example",
                        "version": 1,
                        "provider_id": "example_provider",
                        "canonical_fact": "example fact",
                        "provider_schema": "Example",
                        "provider_field": "exampleField",
                        "resource_authority": "example_resource",
                        "approval_status": "approved",
                        "approved_by": "project-owner",
                        "approval_basis": "test",
                        "openapi_source_reference": "openapi:test",
                        "semantic_source_reference": "help:test",
                        "capability_names": ["endpoint.device.read"],
                        "active": True,
                    }
                ],
            }
        )
    )

    registry = JsonSemanticMappingRegistryLoader(path).load()

    assert (
        registry.resolve_active(
            canonical_fact="example fact",
        ).provider_field
        == "exampleField"
    )


def test_active_mapping_must_be_approved():
    with pytest.raises(PermissionError):
        ApprovedSemanticMapping(
            mapping_id="example",
            version=1,
            provider_id="example_provider",
            canonical_fact="example fact",
            provider_schema="Example",
            provider_field="exampleField",
            resource_authority="example_resource",
            approval_status="deprecated",
            approved_by="project-owner",
            approval_basis="test",
            openapi_source_reference="openapi:test",
            semantic_source_reference="help:test",
            capability_names=("endpoint.device.read",),
            active=True,
        )
