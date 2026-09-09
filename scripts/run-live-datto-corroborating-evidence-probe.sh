#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START LIVE DATTO CORROBORATING EVIDENCE PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: LIVE GOVERNED CORROBORATION =========="

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
from orchestrator.provider_corroborating_evidence_review import (
    GovernedOpenApiCorroboratingEvidenceReviewer,
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

reader = GovernedOpenApiDocumentationSourceAdapter(
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

records = tuple(reader.read(target=target))
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
    raise SystemExit(0)

evidence = GovernedOpenApiCorroboratingEvidenceReviewer(
    max_sibling_fields=40,
).review(
    finding=candidate,
    source=source,
)

print("CANDIDATE_STATUS=found")
print(f"SCHEMA={evidence.documented_schema}")
print(f"FIELD={evidence.documented_field}")
print(f"FIELD_TYPE={evidence.field_type or '-'}")
print(f"SCHEMA_DESCRIPTION={evidence.schema_description or '-'}")
print(f"FIELD_DESCRIPTION={evidence.field_description or '-'}")
print(f"FIELD_EXAMPLE={evidence.field_example!r}")
print(f"FIELD_DEFAULT={evidence.field_default!r}")
print(
    "FIELD_ENUM="
    + (" | ".join(str(item) for item in evidence.field_enum) or "-")
)
print(
    "SIBLING_FIELDS="
    + (" | ".join(evidence.sibling_fields) or "-")
)
print(
    "READ_ONLY_RESPONSE_OPERATIONS="
    + (" | ".join(evidence.read_only_operations) or "-")
)
print(f"SOURCE_REFERENCE={evidence.source_reference}")
print(f"SEMANTIC_PROOF={evidence.semantic_proof}")

print("SEMANTIC_MAPPING_CREATED=False")
print("CAPABILITY_REGISTRATION_CREATED=False")
print("PROVIDER_OPERATION_EXECUTED=False")
print("CREDENTIALS_USED=False")
PY

echo "========== SECTION 3: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live Datto corroborating-evidence review completed."
echo "Context was collected from authoritative documentation only."
echo "Corroborating context does not establish semantic equivalence."
echo "NO DATTO OPERATIONAL API CALL PERFORMED."
echo "NO SEMANTIC MAPPING OR CAPABILITY REGISTRATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE DATTO CORROBORATING EVIDENCE PROBE =========="
