#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START LIVE DATTO CROSS-SOURCE SEMANTIC PROPOSAL PROBE =========="

"$PY" - <<'PY'
from orchestrator.https_documentation_transport import (
    GovernedHttpsDocumentationTransport,
)
from orchestrator.html_documentation_source_adapter import (
    GovernedHtmlDocumentationSourceAdapter,
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
from orchestrator.provider_semantic_mapping_proposal import (
    GovernedCrossSourceSemanticMappingProposer,
)
from orchestrator.provider_semantic_statement import (
    GovernedSemanticStatementExtractor,
)

registry = ProviderDocumentationSourceRegistry()
register_provider_documentation_sources(registry)
resolver = GovernedDocumentationSourceResolver(registry=registry)
transport = GovernedHttpsDocumentationTransport(
    timeout_seconds=10,
    max_response_bytes=5_000_000,
)

openapi_target = ProviderDocumentationReviewTarget(
    provider_id="datto_rmm",
    documentation_source="Datto RMM API documentation",
    unsupported_facts=("operating system display version",),
    resource_authority="managed_endpoint",
)

openapi_source = tuple(
    GovernedOpenApiDocumentationSourceAdapter(
        resolver=resolver,
        transport=transport,
    ).read(target=openapi_target)
)[0]

candidate = next(
    item
    for item in GovernedOpenApiDocumentationInterpreter(
        max_findings_per_fact=50
    ).interpret(
        target=openapi_target,
        source=openapi_source,
    )
    if item.documented_schema == "Device"
    and item.documented_field == "displayVersion"
)

structural = GovernedOpenApiCorroboratingEvidenceReviewer().review(
    finding=candidate,
    source=openapi_source,
)

help_target = ProviderDocumentationReviewTarget(
    provider_id="datto_rmm",
    documentation_source="Datto RMM product documentation",
    unsupported_facts=("operating system display version",),
    resource_authority="managed_endpoint",
)

help_source = tuple(
    GovernedHtmlDocumentationSourceAdapter(
        resolver=resolver,
        transport=transport,
    ).read(target=help_target)
)[0]

statement = GovernedSemanticStatementExtractor().extract_windows_display_version(
    source=help_source
)

proposal = GovernedCrossSourceSemanticMappingProposer().propose(
    structural_evidence=structural,
    semantic_statement=statement,
)

print("CROSS_SOURCE_STATUS=proposal_created")
print(f"PROVIDER={proposal.provider_id}")
print(f"CANONICAL_FACT={proposal.canonical_fact}")
print(f"PROVIDER_SCHEMA={proposal.provider_schema}")
print(f"PROVIDER_FIELD={proposal.provider_field}")
print(f"PROPOSAL_STATUS={proposal.proposal_status}")
print(f"APPROVED={proposal.approved}")
print(f"ACTIVE={proposal.active}")
print(f"OPENAPI_EVIDENCE={proposal.openapi_source_reference}")
print(f"SEMANTIC_EVIDENCE={proposal.semantic_source_reference}")
print("REGISTRY_MUTATION_PERFORMED=False")
print("PROVIDER_OPERATION_EXECUTED=False")
print("CREDENTIALS_USED=False")
PY

echo "========== RESULT =========="
echo "Cross-source proposal probe completed."
echo "NO SEMANTIC MAPPING ACTIVATION PERFORMED."
echo "NO REGISTRY MUTATION PERFORMED."
echo "NO PROVIDER OPERATION PERFORMED."
echo "========== END LIVE DATTO CROSS-SOURCE SEMANTIC PROPOSAL PROBE =========="
