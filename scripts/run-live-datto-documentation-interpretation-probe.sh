#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START LIVE DATTO DOCUMENTATION INTERPRETATION PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: BOUNDED DOCUMENTATION READ AND INTERPRETATION =========="

"$PY" - <<'PY'
from orchestrator.https_documentation_transport import (
    GovernedHttpsDocumentationTransport,
)
from orchestrator.openapi_documentation_interpreter import (
    GovernedOpenApiDocumentationInterpreter,
)
from orchestrator.openapi_documentation_source_adapter import (
    GovernedOpenApiDocumentationSourceAdapter,
)
from orchestrator.provider_documentation_reader import (
    GovernedProviderDocumentationReader,
)
from orchestrator.provider_documentation_review import (
    ProviderDocumentationReviewTarget,
)
from orchestrator.provider_documentation_source_catalog import (
    register_provider_documentation_sources,
)
from orchestrator.provider_documentation_source_registry import (
    GovernedDocumentationSourceResolver,
    ProviderDocumentationSourceRegistry,
)

registry = ProviderDocumentationSourceRegistry()
register_provider_documentation_sources(registry)

source_reader = GovernedOpenApiDocumentationSourceAdapter(
    resolver=GovernedDocumentationSourceResolver(registry=registry),
    transport=GovernedHttpsDocumentationTransport(
        timeout_seconds=10,
        max_response_bytes=5_000_000,
    ),
    max_document_bytes=5_000_000,
)

reader = GovernedProviderDocumentationReader(
    source_reader=source_reader,
    interpreter=GovernedOpenApiDocumentationInterpreter(
        max_findings_per_fact=25,
    ),
)

target = ProviderDocumentationReviewTarget(
    provider_id="datto_rmm",
    documentation_source="Datto RMM API documentation",
    unsupported_facts=("operating system display version",),
    resource_authority="managed_endpoint",
    connector_id="datto_rmm",
)

try:
    result = reader.read(target=target)
except Exception as exc:
    print("DOCUMENTATION_INTERPRETATION_STATUS=unavailable")
    print(f"DOCUMENTATION_INTERPRETATION_ERROR_TYPE={type(exc).__name__}")
    print(f"DOCUMENTATION_INTERPRETATION_ERROR={exc}")
else:
    print("DOCUMENTATION_INTERPRETATION_STATUS=available")
    print(f"DOCUMENTATION_FINDING_COUNT={len(result.findings)}")
    print(f"DOCUMENTATION_REVIEW_ONLY={result.review_only}")
    print(f"DOCUMENTATION_REVIEW_OWNER={result.governance_owner}")

    for index, finding in enumerate(result.findings, start=1):
        print(
            f"FINDING[{index}]_OPERATION="
            f"{finding.documented_operation or '-'}"
        )
        print(
            f"FINDING[{index}]_SCHEMA="
            f"{finding.documented_schema or '-'}"
        )
        print(
            f"FINDING[{index}]_FIELD="
            f"{finding.documented_field or '-'}"
        )
        print(
            f"FINDING[{index}]_RELEVANCE="
            f"{finding.relevance}"
        )
        print(
            f"FINDING[{index}]_SEMANTIC_PROOF="
            f"{finding.semantic_proof}"
        )
        print(
            f"FINDING[{index}]_SOURCE_REFERENCE="
            f"{finding.source_reference}"
        )
        print(
            f"FINDING[{index}]_AMBIGUITY="
            f"{finding.ambiguity_summary or '-'}"
        )

print("SEMANTIC_MAPPING_CREATED=False")
print("CAPABILITY_REGISTRATION_CREATED=False")
print("PROVIDER_OPERATION_EXECUTED=False")
print("CREDENTIALS_USED=False")
PY

echo "========== SECTION 3: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live Datto OpenAPI documentation interpretation probe completed."
echo "Findings are candidate evidence only."
echo "NO SEMANTIC EQUIVALENCE WAS ESTABLISHED."
echo "NO DATTO OPERATIONAL API CALL PERFORMED."
echo "NO CAPABILITY OR EVIDENCE REGISTRY MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE DATTO DOCUMENTATION INTERPRETATION PROBE =========="
