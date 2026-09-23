#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO OPENAPI OS EVIDENCE INSPECTION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

if ! docker ps --format '{{.Names}}' | grep -qx 'jason-runtime'; then
  echo "ERROR: jason-runtime is not running."
  exit 20
fi

echo "========== SECTION 2: FETCH PLATFORM-SPECIFIC OPENAPI DOCUMENT READ-ONLY =========="
docker exec -i jason-runtime python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials

context = ConnectorContext(
    correlation_id="diagnostic-datto-openapi-os-evidence",
    principal_id="diagnostic-readonly",
    organization_id="aot",
    client_id=None,
    capability="datto_rmm.device.audit.get",
    mode="observe",
)
resolver = OpenBaoSecretResolver(
    base_url=os.environ.get("JASON_OPENBAO_URL", "http://openbao:8200"),
    role_id_path=Path(os.environ.get("JASON_OPENBAO_ROLE_ID_PATH", "/run/jason-secrets/openbao/role_id")),
    secret_id_path=Path(os.environ.get("JASON_OPENBAO_SECRET_ID_PATH", "/run/jason-secrets/openbao/secret_id")),
)
credentials = resolver.resolve("datto_rmm.readonly", context)
require_durable_credentials(credentials)
token = acquire_access_token(credentials=credentials)
base = str(credentials["api_url"]).rstrip("/")
if base.endswith("/api"):
    base = base[:-4]
url = base + "/api/v3/api-docs/Datto-RMM"
req = Request(
    url,
    headers={
        "Authorization": f"{token.token_type} {token.access_token}",
        "Accept": "application/json",
    },
    method="GET",
)
with urlopen(req, timeout=30) as response:
    document = json.loads(response.read().decode("utf-8"))

print("OPENAPI_FETCH=PASS")
print(f"OPENAPI_VERSION={document.get('openapi', 'unknown')}")
paths = document.get("paths", {})
components = document.get("components", {}).get("schemas", {})

interesting_paths = (
    "/v2/device/{deviceUid}",
    "/v2/audit/device/{deviceUid}",
    "/v2/audit/device/{deviceUid}/software",
)
needles = ("operating", "windows", "os", "version", "build", "release", "display")


def resolve_schema(schema: Any) -> Any:
    if not isinstance(schema, Mapping):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return components.get(ref.rsplit("/", 1)[-1], schema)
    return schema


def walk_schema(schema: Any, pointer: str = "", seen: set[int] | None = None):
    schema = resolve_schema(schema)
    if not isinstance(schema, Mapping):
        return
    if seen is None:
        seen = set()
    marker = id(schema)
    if marker in seen:
        return
    seen.add(marker)
    properties = schema.get("properties", {})
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            child_pointer = pointer + "/" + str(name)
            normalized = "".join(ch for ch in str(name).casefold() if ch.isalnum())
            if any(needle in normalized for needle in needles):
                child_schema = resolve_schema(child)
                typ = child_schema.get("type", "") if isinstance(child_schema, Mapping) else ""
                fmt = child_schema.get("format", "") if isinstance(child_schema, Mapping) else ""
                print(f"SCHEMA_FIELD {child_pointer} type={typ or 'unspecified'} format={fmt or 'unspecified'}")
            walk_schema(child, child_pointer, seen)
    items = schema.get("items")
    if items is not None:
        walk_schema(items, pointer + "[]", seen)
    for key in ("allOf", "oneOf", "anyOf"):
        values = schema.get(key)
        if isinstance(values, list):
            for index, child in enumerate(values):
                walk_schema(child, f"{pointer}/{key}/{index}", seen)


for path in interesting_paths:
    operation = paths.get(path, {}).get("get") if isinstance(paths.get(path), Mapping) else None
    if not isinstance(operation, Mapping):
        print(f"PATH {path} GET=NOT_DOCUMENTED")
        continue
    print(f"PATH {path} GET=DOCUMENTED")
    summary = str(operation.get("summary") or operation.get("description") or "").strip().replace("\n", " ")
    if summary:
        print(f"SUMMARY {path} = {summary[:240]}")
    responses = operation.get("responses", {})
    response = responses.get("200") or responses.get(200)
    if not isinstance(response, Mapping):
        print(f"RESPONSE_SCHEMA {path} = unavailable")
        continue
    content = response.get("content", {})
    media = content.get("application/json", {}) if isinstance(content, Mapping) else {}
    schema = media.get("schema") if isinstance(media, Mapping) else None
    if not isinstance(schema, Mapping):
        print(f"RESPONSE_SCHEMA {path} = unavailable")
        continue
    ref = schema.get("$ref")
    if ref:
        print(f"RESPONSE_SCHEMA {path} = {ref}")
    else:
        print(f"RESPONSE_SCHEMA {path} = inline")
    walk_schema(schema, path)
PY

echo "========== RESULT =========="
echo "Datto platform-specific OpenAPI inspection complete."
echo "Only operation metadata and OS/version/build/release-related schema field names were printed."
echo "No credentials, tokens, provider data values, source changes, deployment changes, or provider mutations were performed."
echo "========== END DATTO OPENAPI OS EVIDENCE INSPECTION =========="
