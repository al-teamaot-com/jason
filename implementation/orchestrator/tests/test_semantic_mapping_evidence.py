import pytest

from orchestrator.semantic_mapping_evidence import (
    GovernedSemanticMappingEvidenceProjector,
)
from orchestrator.semantic_mapping_registry import (
    ApprovedSemanticMapping,
    SemanticMappingRegistry,
)


def mapping(
    *,
    canonical_fact="operating system release name",
    provider_field="releaseName",
    capability_names=("endpoint.device.search",),
):
    return ApprovedSemanticMapping(
        mapping_id="example-release",
        version=1,
        provider_id="example_provider",
        canonical_fact=canonical_fact,
        provider_schema="Device",
        provider_field=provider_field,
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative cross-source evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=capability_names,
        active=True,
    )


def projector(*mappings):
    return GovernedSemanticMappingEvidenceProjector(
        registry=SemanticMappingRegistry(mappings),
    )


def test_projects_only_approved_direct_provider_field():
    data = {
        "resource_matches": [
            {
                "resource_id": "device-1",
                "hostname": "EXAMPLE-1",
            }
        ],
        "resolved_resource_id": "device-1",
        "provider_data": {
            "hostname": "EXAMPLE-1",
            "releaseName": "24H2",
        },
    }

    result = projector(mapping()).project(
        provider_id="example_provider",
        capability_name="endpoint.device.search",
        data=data,
        requested_facts=("operating system release name",),
    )

    assert (
        result["provider_data"]["semantic_evidence"][
            "operating_system_release_name"
        ]
        == "24H2"
    )


def test_mapping_bound_to_other_capability_is_not_projected():
    result = projector(
        mapping(capability_names=("endpoint.device.read",))
    ).project(
        provider_id="example_provider",
        capability_name="endpoint.device.search",
        data={
            "provider_data": {
                "releaseName": "24H2",
            }
        },
        requested_facts=("operating system release name",),
    )

    assert "semantic_evidence" not in result["provider_data"]


def test_missing_provider_field_is_not_inferred():
    result = projector(mapping()).project(
        provider_id="example_provider",
        capability_name="endpoint.device.search",
        data={
            "provider_data": {
                "somethingElse": "24H2",
            }
        },
        requested_facts=("operating system release name",),
    )

    assert "semantic_evidence" not in result["provider_data"]


def test_conflicting_existing_semantic_evidence_fails_closed():
    with pytest.raises(LookupError):
        projector(mapping()).project(
            provider_id="example_provider",
            capability_name="endpoint.device.search",
            data={
                "provider_data": {
                    "releaseName": "24H2",
                    "semantic_evidence": {
                        "operating_system_release_name": "23H2",
                    },
                }
            },
            requested_facts=("operating system release name",),
        )
