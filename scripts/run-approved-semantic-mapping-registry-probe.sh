#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START APPROVED SEMANTIC MAPPING REGISTRY PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: LOAD GOVERNED REGISTRY =========="

"$PY" - <<'PY'
from pathlib import Path

from orchestrator.semantic_mapping_registry import (
    JsonSemanticMappingRegistryLoader,
)

registry = JsonSemanticMappingRegistryLoader(
    Path("config/semantic_mappings/approved.json")
).load()

mapping = registry.resolve_active(
    canonical_fact="operating system display version",
    resource_authority="managed_endpoint",
    provider_id="datto_rmm",
)

print("MAPPING_STATUS=resolved")
print(f"MAPPING_ID={mapping.mapping_id}")
print(f"MAPPING_VERSION={mapping.version}")
print(f"PROVIDER={mapping.provider_id}")
print(f"CANONICAL_FACT={mapping.canonical_fact}")
print(f"PROVIDER_SCHEMA={mapping.provider_schema}")
print(f"PROVIDER_FIELD={mapping.provider_field}")
print(f"RESOURCE_AUTHORITY={mapping.resource_authority}")
print(f"APPROVAL_STATUS={mapping.approval_status}")
print(f"APPROVED_BY={mapping.approved_by}")
print(f"ACTIVE={mapping.active}")
print(f"OPENAPI_EVIDENCE={mapping.openapi_source_reference}")
print(f"SEMANTIC_EVIDENCE={mapping.semantic_source_reference}")

print("PROVIDER_OPERATION_EXECUTED=False")
print("RUNTIME_ACTIVATION_PERFORMED=False")
print("DEPLOYMENT_PERFORMED=False")
PY

echo "========== RESULT =========="
echo "Approved semantic mapping is durable as governed machine-readable data."
echo "The registry is generic and is not a question-specific execution script."
echo "NO PROVIDER OPERATION PERFORMED."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END APPROVED SEMANTIC MAPPING REGISTRY PROBE =========="
