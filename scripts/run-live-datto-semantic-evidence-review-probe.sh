#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START LIVE DATTO SEMANTIC EVIDENCE REVIEW PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: LIVE GOVERNED REVIEW =========="

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
from orchestrator.provider_semantic_evidence_review import (
    GovernedOpenApiSemanticEvidenceReviewer,
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

target = ProviderDocumentationReviewTarget(
    provider_id="datto_rmm",
    documentation_source="Datto RMM API documentation",
    unsupported_facts=("operating system display version",),
    resource_authority="managed_endpoint",
    connector_id="datto_rmm",
)

records = tuple(source_reader.read(target=target))
if not records:
    raise SystemExit("no governed Datto documentation record returned")

source = records[0]

findings = tuple(
    GovernedOpenApiDocumentationInterpreter(
        max_findings_per_fact=50,
    ).interpret(
        target=target,
        source=source,
    )
)

candidate = next(
    (
        item
        for item in findings
        if item.documented_schema == "Device"
        and item.documented_field == "displayVersion"
    ),
    None,
)

if candidate is None:
    print("CANDIDATE_STATUS=not_found")
    print("SEMANTIC_MAPPING_CREATED=False")
    print("CAPABILITY_REGISTRATION_CREATED=False")
    print("PROVIDER_OPERATION_EXECUTED=False")
    print("CREDENTIALS_USED=False")
    raise SystemExit(0)

print("CANDIDATE_STATUS=found")
print(f"CANDIDATE_SCHEMA={candidate.documented_schema}")
print(f"CANDIDATE_FIELD={candidate.documented_field}")
print(f"CANDIDATE_SOURCE_REFERENCE={candidate.source_reference}")
print(f"CANDIDATE_SEMANTIC_PROOF={candidate.semantic_proof}")

review = GovernedOpenApiSemanticEvidenceReviewer().review(
    finding=candidate,
    source=source,
)

print(f"REVIEW_STATUS={review.status.value}")
print(f"PROPOSAL_ALLOWED={review.proposal_allowed}")
print(f"SEMANTIC_MAPPING_APPROVED={review.semantic_mapping_approved}")
print(f"FIELD_TYPE={review.field_type or '-'}")
print(f"FIELD_DESCRIPTION={review.field_description or '-'}")
print(
    "READ_ONLY_RESPONSE_OPERATIONS="
    + (" | ".join(review.response_operations) or "-")
)
print(f"REVIEW_SOURCE_REFERENCE={review.source_reference}")
print(f"REVIEW_RATIONALE={review.rationale}")

print("SEMANTIC_MAPPING_CREATED=False")
print("CAPABILITY_REGISTRATION_CREATED=False")
print("PROVIDER_OPERATION_EXECUTED=False")
print("CREDENTIALS_USED=False")
PY

echo "========== SECTION 3: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live Datto semantic-evidence review completed."
echo "The result may permit proposal creation but cannot approve or activate a semantic mapping."
echo "NO DATTO OPERATIONAL API CALL PERFORMED."
echo "NO CAPABILITY OR EVIDENCE REGISTRY MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE DATTO SEMANTIC EVIDENCE REVIEW PROBE =========="
