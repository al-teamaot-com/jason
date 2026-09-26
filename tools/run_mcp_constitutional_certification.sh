#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SOURCE_REVISION="$(git rev-parse HEAD)"
BASE_RUNTIME_IMAGE="${JASON_MCP_CERT_BASE_RUNTIME_IMAGE:-jason-mcp:generic-governed-8f1e864947a2}"
RUNTIME_IMAGE="jason-mcp:constitutional-runtime-${SOURCE_REVISION:0:12}"
CERT_IMAGE="jason-mcp:constitutional-cert-${SOURCE_REVISION:0:12}"
EVIDENCE_PATH="${JASON_MCP_CERT_EVIDENCE_PATH:-}"

TESTS=(
  /opt/jason-src/implementation/mcp_service/tests/test_generic_governed_execution_contract.py
  /opt/jason-src/implementation/mcp_service/tests/test_authority_grant_admin.py
  /opt/jason-src/implementation/mcp_service/tests/test_contract_client_context.py
  /opt/jason-src/implementation/mcp_service/tests/test_read_authority_admin.py
  /opt/jason-src/implementation/mcp_service/tests/test_capability_discovery.py
  /opt/jason-src/implementation/mcp_service/tests/test_governed_read_failure_contract.py
  /opt/jason-src/implementation/mcp_service/tests/test_ticket_work_lifecycle_contract.py
)

docker build --build-arg "BASE_IMAGE=$BASE_RUNTIME_IMAGE" -f infrastructure/jason-mcp/Dockerfile -t "$RUNTIME_IMAGE" .
docker build --build-arg "BASE_IMAGE=$RUNTIME_IMAGE" -f infrastructure/jason-mcp/Dockerfile.certification -t "$CERT_IMAGE" .

docker run --rm --entrypoint python "$CERT_IMAGE" -m pytest -q -p no:cacheprovider "${TESTS[@]}"

printf 'MCP_CONSTITUTIONAL_CERTIFICATION=PASS\n'
printf 'SOURCE_REVISION=%s\n' "$SOURCE_REVISION"
printf 'RUNTIME_IMAGE=%s\n' "$RUNTIME_IMAGE"
printf 'CERT_IMAGE=%s\n' "$CERT_IMAGE"

if [[ -n "$EVIDENCE_PATH" ]]; then
  mkdir -p "$(dirname "$EVIDENCE_PATH")"
  python3 - "$EVIDENCE_PATH" "$SOURCE_REVISION" "$BASE_RUNTIME_IMAGE" "$RUNTIME_IMAGE" "$CERT_IMAGE" <<'PY'
import json
import sys
from pathlib import Path

path, source_revision, base_image, runtime_image, cert_image = sys.argv[1:]
payload = {
    "schema_version": "1.0",
    "status": "pass",
    "source_revision": source_revision,
    "base_runtime_image": base_image,
    "runtime_image": runtime_image,
    "certification_image": cert_image,
    "suite": "mcp-constitutional-production-equivalent",
    "tested_contracts": [
        "generic-governed-execution",
        "authority-grant-admin",
        "client-context",
        "read-authority-admin",
        "capability-discovery",
        "governed-read-failure",
        "ticket-work-lifecycle",
    ],
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(path)
PY
fi
