#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START LIVE DATTO DOCUMENTATION READ PROBE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: BOUNDED DOCUMENTATION READ =========="

"$PY" - <<'PY'
import json

from orchestrator.https_documentation_transport import (
    GovernedHttpsDocumentationTransport,
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

registry = ProviderDocumentationSourceRegistry()
register_provider_documentation_sources(registry)

adapter = GovernedOpenApiDocumentationSourceAdapter(
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

try:
    records = tuple(adapter.read(target=target))
except Exception as exc:
    print("DOCUMENTATION_READ_STATUS=unavailable")
    print(f"DOCUMENTATION_READ_ERROR_TYPE={type(exc).__name__}")
    print(f"DOCUMENTATION_READ_ERROR={exc}")
else:
    print("DOCUMENTATION_READ_STATUS=available")
    print(f"DOCUMENTATION_RECORD_COUNT={len(records)}")

    for index, record in enumerate(records, start=1):
        print(
            f"DOCUMENTATION_RECORD[{index}]_SOURCE_REFERENCE="
            f"{record.source_reference}"
        )
        print(
            f"DOCUMENTATION_RECORD[{index}]_BYTES="
            f"{len(record.content.encode('utf-8'))}"
        )

        try:
            parsed = json.loads(record.content)
        except json.JSONDecodeError:
            print(
                f"DOCUMENTATION_RECORD[{index}]_JSON_VALID=False"
            )
        else:
            print(
                f"DOCUMENTATION_RECORD[{index}]_JSON_VALID=True"
            )
            print(
                f"DOCUMENTATION_RECORD[{index}]_OPENAPI_VERSION="
                f"{parsed.get('openapi', parsed.get('swagger', '-'))}"
            )

            paths = parsed.get("paths", {})
            schemas = (
                parsed.get("components", {})
                .get("schemas", {})
            )

            print(
                f"DOCUMENTATION_RECORD[{index}]_PATH_COUNT="
                f"{len(paths) if isinstance(paths, dict) else 0}"
            )
            print(
                f"DOCUMENTATION_RECORD[{index}]_SCHEMA_COUNT="
                f"{len(schemas) if isinstance(schemas, dict) else 0}"
            )

print("SEMANTIC_MAPPING_CREATED=False")
print("PROVIDER_OPERATION_EXECUTED=False")
print("CREDENTIALS_USED=False")
PY

echo "========== SECTION 3: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live Datto documentation retrieval probe completed."
echo "The probe reads only the governed documentation source."
echo "A retrieval failure is preserved as evidence and does not trigger fallback."
echo "NO DATTO OPERATIONAL API CALL PERFORMED."
echo "NO SEMANTIC MAPPING OR REGISTRY MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END LIVE DATTO DOCUMENTATION READ PROBE =========="
