#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO AUDIT OS EVIDENCE INSPECTION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

docker ps --filter name='^jason-runtime$' --format 'NAMES\tSTATUS\tIMAGE'
if ! docker ps --format '{{.Names}}' | grep -qx 'jason-runtime'; then
  echo "ERROR: jason-runtime is not running."
  exit 20
fi

echo "========== SECTION 2: GOVERNED DATTO AUDIT READ FOR AOT-50282 =========="
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
            segment = key.replace("~", "~0").replace("/", "~1")
            child_pointer = f"{pointer}/{segment}"
            yield child_pointer, key, child
            yield from walk(child, child_pointer)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_pointer = f"{pointer}/{index}"
            yield child_pointer, str(index), child
            yield from walk(child, child_pointer)


def preview(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = repr(value)
        return text if len(text) <= 220 else text[:217] + "..."
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
        correlation_id="diagnostic-datto-audit-os",
        principal_id="diagnostic-readonly",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.device.audit.get",
        mode="observe",
    ),
    arguments={
        "hostname": "AOT-50282",
        "requested_facts": ["operating system display version"],
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
    },
)
result = connector.execute(request)
data = result.data

if not isinstance(data, Mapping):
    print("AUDIT_RESULT_MAPPING=False")
    raise SystemExit(0)

matches = data.get("resource_matches", ())
print(f"RESOURCE_MATCH_COUNT={len(matches) if isinstance(matches, (list, tuple)) else 'unknown'}")
print(f"RESOLVED_RESOURCE_ID_PRESENT={bool(data.get('resolved_resource_id'))}")
provider_data = data.get("provider_data")
print(f"AUDIT_PROVIDER_DATA_PRESENT={isinstance(provider_data, Mapping)}")
if not isinstance(provider_data, Mapping):
    raise SystemExit(0)

print("-- AUDIT OS / RELEASE / BUILD RELATED FIELDS --")
needles = (
    "operating",
    "windows",
    "os",
    "version",
    "build",
    "release",
    "edition",
    "product",
    "caption",
    "servicepack",
)
seen = 0
for pointer, key, value in walk(provider_data):
    normalized = "".join(ch for ch in key.casefold() if ch.isalnum())
    if not normalized:
        continue
    if any(needle in normalized for needle in needles):
        print(f"FIELD {pointer} = {preview(value)}")
        seen += 1

print(f"RELEVANT_FIELD_COUNT={seen}")
PY

echo "========== SECTION 3: INTERPRETATION GATE =========="
echo "If the audit payload exposes an authoritative Windows release/display-version field, map only that documented/audited field into the Semantic Knowledge Registry."
echo "If it exposes only OS name/build data, keep Windows Display Version unresolved unless a separate governed derivation rule is approved."

echo "========== RESULT =========="
echo "Datto audit OS evidence inspection complete."
echo "This was a read-only governed provider call. No credentials, tokens, source changes, deployment changes, or provider mutations were performed."
echo "========== END DATTO AUDIT OS EVIDENCE INSPECTION =========="
