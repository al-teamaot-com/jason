import json

from orchestrator.openapi_documentation_interpreter import (
    GovernedOpenApiDocumentationInterpreter,
)
from orchestrator.provider_documentation_reader import (
    ProviderDocumentationSourceRecord,
)
from orchestrator.provider_documentation_review import (
    ProviderDocumentationReviewTarget,
)


def target(fact="operating system display version"):
    return ProviderDocumentationReviewTarget(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        unsupported_facts=(fact,),
        resource_authority="managed_endpoint",
    )


def source(document):
    return ProviderDocumentationSourceRecord(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        source_reference="example-openapi:sha256:test",
        content=json.dumps(document),
    )


def test_interpreter_finds_relevant_schema_property_without_semantic_proof():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "DeviceSystemInfo": {
                    "properties": {
                        "displayVersion": {
                            "type": "string",
                            "description": "Operating system display version",
                        }
                    }
                }
            }
        },
    }

    findings = GovernedOpenApiDocumentationInterpreter().interpret(
        target=target(),
        source=source(document),
    )

    matching = [
        item
        for item in findings
        if item.documented_field == "displayVersion"
    ]

    assert len(matching) == 1
    assert matching[0].semantic_proof is False
    assert matching[0].relevance == "candidate_evidence"


def test_interpreter_can_surface_relevant_operation():
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/v2/device/{deviceUid}": {
                "get": {
                    "summary": (
                        "Fetch operating system information for a managed device"
                    ),
                    "responses": {"200": {"description": "Device system information"}},
                }
            }
        },
    }

    findings = GovernedOpenApiDocumentationInterpreter().interpret(
        target=target(),
        source=source(document),
    )

    assert any(
        item.documented_operation == "GET /v2/device/{deviceUid}"
        for item in findings
    )
    assert all(item.semantic_proof is False for item in findings)


def test_interpreter_does_not_emit_unrelated_fields():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Device": {
                    "properties": {
                        "serialNumber": {
                            "type": "string",
                            "description": "Hardware serial number",
                        }
                    }
                }
            }
        },
    }

    findings = GovernedOpenApiDocumentationInterpreter().interpret(
        target=target(),
        source=source(document),
    )

    assert not any(
        item.documented_field == "serialNumber"
        for item in findings
    )


def test_interpreter_is_not_tied_to_windows_or_datto():
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "PrinterSupply": {
                    "properties": {
                        "tonerLevel": {
                            "type": "integer",
                            "description": "Current toner level percentage",
                        }
                    }
                }
            }
        },
    }

    findings = GovernedOpenApiDocumentationInterpreter().interpret(
        target=target("printer toner level"),
        source=source(document),
    )

    assert any(
        item.documented_field == "tonerLevel"
        for item in findings
    )


def test_interpreter_caps_findings_per_fact():
    properties = {
        f"versionField{index}": {
            "type": "string",
            "description": "system version",
        }
        for index in range(20)
    }

    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "System": {
                    "properties": properties,
                }
            }
        },
    }

    findings = GovernedOpenApiDocumentationInterpreter(
        max_findings_per_fact=3
    ).interpret(
        target=target("system version"),
        source=source(document),
    )

    assert len(findings) <= 3
