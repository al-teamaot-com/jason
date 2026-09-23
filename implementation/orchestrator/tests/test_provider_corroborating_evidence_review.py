import json

import pytest

from orchestrator.provider_corroborating_evidence_review import (
    GovernedOpenApiCorroboratingEvidenceReviewer,
)
from orchestrator.provider_documentation_reader import (
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)


def source(document):
    return ProviderDocumentationSourceRecord(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference="example:sha256:test",
        content=json.dumps(document),
    )


def finding():
    return ProviderDocumentationCandidateFinding(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference=(
            "example:sha256:test#components/schemas/Device/properties/releaseName"
        ),
        unsupported_fact="operating system release name",
        documented_schema="Device",
        documented_field="releaseName",
        relevance="candidate_evidence",
        semantic_proof=False,
    )


def test_collects_context_without_semantic_proof():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "description": "Managed endpoint",
                    "properties": {
                        "operatingSystem": {"type": "string"},
                        "releaseName": {
                            "type": "string",
                            "description": "Vendor reported operating system release",
                            "example": "Example Release",
                        },
                        "serialNumber": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/v2/device/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Device"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    evidence = GovernedOpenApiCorroboratingEvidenceReviewer().review(
        finding=finding(),
        source=source(document),
    )

    assert evidence.semantic_proof is False
    assert evidence.schema_description == "Managed endpoint"
    assert evidence.field_type == "string"
    assert evidence.field_example == "Example Release"
    assert evidence.read_only_operations == ("GET /v2/device/{id}",)
    assert "operatingSystem" in evidence.sibling_fields
    assert "serialNumber" in evidence.sibling_fields


def test_missing_candidate_field_fails_closed():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "other": {"type": "string"},
                    }
                }
            }
        },
    }

    with pytest.raises(ValueError):
        GovernedOpenApiCorroboratingEvidenceReviewer().review(
            finding=finding(),
            source=source(document),
        )


def test_sibling_collection_is_bounded():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "releaseName": {"type": "string"},
                        **{
                            f"field{index}": {"type": "string"}
                            for index in range(50)
                        },
                    }
                }
            }
        },
    }

    evidence = GovernedOpenApiCorroboratingEvidenceReviewer(
        max_sibling_fields=5
    ).review(
        finding=finding(),
        source=source(document),
    )

    assert len(evidence.sibling_fields) == 5
