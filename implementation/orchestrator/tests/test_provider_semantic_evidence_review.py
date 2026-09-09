import json

from orchestrator.provider_documentation_reader import (
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)
from orchestrator.provider_semantic_evidence_review import (
    GovernedOpenApiSemanticEvidenceReviewer,
    SemanticEvidenceReviewStatus,
)


def source(document):
    return ProviderDocumentationSourceRecord(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference="example:sha256:test",
        content=json.dumps(document),
    )


def finding(field="displayVersion"):
    return ProviderDocumentationCandidateFinding(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference=(
            f"example:sha256:test#components/schemas/Device/properties/{field}"
        ),
        unsupported_fact="operating system display version",
        documented_schema="Device",
        documented_field=field,
        relevance="candidate_evidence",
        semantic_proof=False,
    )


def test_review_becomes_proposal_eligible_only_with_description_and_read_path():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "displayVersion": {
                            "type": "string",
                            "description": "Operating system display version",
                        }
                    }
                }
            }
        },
        "paths": {
            "/v2/device/{deviceUid}": {
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

    review = GovernedOpenApiSemanticEvidenceReviewer().review(
        finding=finding(),
        source=source(document),
    )

    assert review.status is SemanticEvidenceReviewStatus.PROPOSAL_ELIGIBLE
    assert review.proposal_allowed is True
    assert review.semantic_mapping_approved is False
    assert review.response_operations == ("GET /v2/device/{deviceUid}",)


def test_review_remains_ambiguous_without_field_description():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "displayVersion": {"type": "string"}
                    }
                }
            }
        },
        "paths": {
            "/v2/device/{deviceUid}": {
                "get": {
                    "responses": {
                        "200": {
                            "schema": {
                                "$ref": "#/components/schemas/Device"
                            }
                        }
                    }
                }
            }
        },
    }

    review = GovernedOpenApiSemanticEvidenceReviewer().review(
        finding=finding(),
        source=source(document),
    )

    assert review.status is SemanticEvidenceReviewStatus.AMBIGUOUS
    assert review.proposal_allowed is False


def test_review_remains_ambiguous_without_read_only_response_path():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "displayVersion": {
                            "type": "string",
                            "description": "Operating system display version",
                        }
                    }
                }
            }
        },
        "paths": {},
    }

    review = GovernedOpenApiSemanticEvidenceReviewer().review(
        finding=finding(),
        source=source(document),
    )

    assert review.status is SemanticEvidenceReviewStatus.AMBIGUOUS
    assert review.proposal_allowed is False


def test_unrelated_candidate_does_not_gain_semantic_authority():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Bios": {
                    "properties": {
                        "smBiosVersion": {
                            "type": "string",
                            "description": "SMBIOS firmware version",
                        }
                    }
                }
            }
        },
        "paths": {},
    }

    unrelated = ProviderDocumentationCandidateFinding(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference=(
            "example:sha256:test#components/schemas/Bios/properties/smBiosVersion"
        ),
        unsupported_fact="operating system display version",
        documented_schema="Bios",
        documented_field="smBiosVersion",
        relevance="candidate_evidence",
        semantic_proof=False,
    )

    review = GovernedOpenApiSemanticEvidenceReviewer().review(
        finding=unrelated,
        source=source(document),
    )

    assert review.status is not SemanticEvidenceReviewStatus.PROPOSAL_ELIGIBLE
    assert review.semantic_mapping_approved is False
