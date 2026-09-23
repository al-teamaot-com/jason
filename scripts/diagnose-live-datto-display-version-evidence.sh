#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE DATTO DISPLAY VERSION EVIDENCE DIAGNOSTIC =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

docker ps --filter name='^jason-runtime$' --format 'NAMES\tSTATUS\tIMAGE'

if ! docker ps --format '{{.Names}}' | grep -qx 'jason-runtime'; then
  echo "ERROR: jason-runtime is not running."
  exit 20
fi

echo "========== SECTION 2: GOVERNED READ + SANITIZED STRUCTURAL EVIDENCE =========="
docker exec -i jason-runtime python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.connector import DattoRmmConnector


class NullAudit:
    def record(self, event_type, context, details):
        return None


def walk(value: Any, pointer: str = ""):
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_pointer = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            yield child_pointer, key, child
            yield from walk(child, child_pointer)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            yield child_pointer, str(index), child
            yield from walk(child, child_pointer)


def scalar_preview(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = repr(value)
        return text if len(text) <= 180 else text[:177] + "..."
    return f"<{type(value).__name__}>"


secrets = OpenBaoSecretResolver(
    base_url=os.environ.get("JASON_OPENBAO_URL", "http://openbao:8200"),
    role_id_path=Path(os.environ.get("JASON_OPENBAO_ROLE_ID_PATH", "/run/jason-secrets/openbao/role_id")),
    secret_id_path=Path(os.environ.get("JASON_OPENBAO_SECRET_ID_PATH", "/run/jason-secrets/openbao/secret_id")),
)
connector = DattoRmmConnector(
    secrets=secrets,
    transport=UrlLibJsonHttpTransport(),
    audit=NullAudit(),
)
request = ConnectorRequest(
    context=ConnectorContext(
        correlation_id="diagnostic-display-version",
        principal_id="diagnostic-readonly",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.device.search",
        mode="observe",
    ),
    arguments={
        "hostname": "AOT-50282",
        "requested_facts": ["operating system display version"],
        "evidence_contexts": {
            "operating system display version": ["operating_system", "windows_release"]
        },
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
    },
)
result = connector.execute(request)
data = result.data

matches = data.get("resource_matches", []) if isinstance(data, Mapping) else []
print(f"RESOURCE_MATCH_COUNT={len(matches) if isinstance(matches, (list, tuple)) else 'unknown'}")
print(f"RESOLVED_RESOURCE_ID_PRESENT={bool(data.get('resolved_resource_id')) if isinstance(data, Mapping) else False}")

provider_data = data.get("provider_data") if isinstance(data, Mapping) else None
if not isinstance(provider_data, Mapping):
    print("PROVIDER_DATA_PRESENT=False")
    raise SystemExit(0)
print("PROVIDER_DATA_PRESENT=True")

semantic = provider_data.get("semantic_evidence")
print(f"SEMANTIC_EVIDENCE_PRESENT={isinstance(semantic, Mapping)}")
if isinstance(semantic, Mapping):
    for pointer, key, value in walk(semantic, "/semantic_evidence"):
        if not isinstance(value, (Mapping, list, tuple)):
            print(f"SEMANTIC {pointer} = {scalar_preview(value)}")

print("-- RELEVANT PROVIDER FIELDS --")
needles = ("display", "version", "build", "operating", "windows", "os")
for pointer, key, value in walk(provider_data):
    normalized = "".join(ch for ch in key.casefold() if ch.isalnum())
    if not normalized:
        continue
    if any(needle in normalized for needle in needles):
        print(f"FIELD {pointer} = {scalar_preview(value)}")
PY

echo "========== RESULT =========="
echo "Diagnostic complete. No source, deployment, credential, or provider mutation was performed."
echo "The output is limited to endpoint match state, semantic evidence, and OS/version/build-related provider fields."
echo "========== END LIVE DATTO DISPLAY VERSION EVIDENCE DIAGNOSTIC =========="
