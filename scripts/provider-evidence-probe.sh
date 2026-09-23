#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Provider Evidence Probe

Purpose:
  Prove what structured data Jason can retrieve through an existing governed,
  provider-neutral read capability.

Current supported resource:
  endpoint

Usage:
  provider-evidence-probe.sh \
    --provider datto_rmm \
    --resource endpoint \
    --selector hostname=AOT-50282

Options:
  --provider NAME          Expected resolved provider. Required.
  --resource NAME          Canonical resource type. Required.
  --selector KEY=VALUE     Resource selector. Repeatable. Required.
  --require-path POINTER   Require an evidence JSON Pointer. Repeatable.
  --filter TEXT            Print only evidence paths containing TEXT.
  --format table|json      Output format. Default: table.
  --principal ID           Jason principal. Default: person-al.
  --container NAME         Runtime container. Default: jason-runtime.
  --include-udf            Include Datto UDF contents. Off by default.
  --help                   Show this help.

Examples:
  ./scripts/provider-evidence-probe.sh \
    --provider datto_rmm \
    --resource endpoint \
    --selector hostname=AOT-50282

  ./scripts/provider-evidence-probe.sh \
    --provider datto_rmm \
    --resource endpoint \
    --selector hostname=AOT-50282 \
    --filter ipaddress \
    --require-path /intIpAddress \
    --require-path /extIpAddress

Important:
  --provider is an assertion about the expected resolved provider. It does not
  give the probe authority to choose or bypass Jason's provider resolution.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

provider=""
resource=""
principal="person-al"
container_name="jason-runtime"
output_format="table"
filter_text=""
include_udf="false"

declare -a selectors=()
declare -a required_paths=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --provider)
            [[ $# -ge 2 ]] || fail "--provider requires a value"
            provider="$2"
            shift 2
            ;;
        --resource)
            [[ $# -ge 2 ]] || fail "--resource requires a value"
            resource="$2"
            shift 2
            ;;
        --selector)
            [[ $# -ge 2 ]] || fail "--selector requires KEY=VALUE"
            selectors+=("$2")
            shift 2
            ;;
        --require-path)
            [[ $# -ge 2 ]] || fail "--require-path requires a JSON Pointer"
            required_paths+=("$2")
            shift 2
            ;;
        --filter)
            [[ $# -ge 2 ]] || fail "--filter requires a value"
            filter_text="$2"
            shift 2
            ;;
        --format)
            [[ $# -ge 2 ]] || fail "--format requires table or json"
            output_format="$2"
            shift 2
            ;;
        --principal)
            [[ $# -ge 2 ]] || fail "--principal requires a value"
            principal="$2"
            shift 2
            ;;
        --container)
            [[ $# -ge 2 ]] || fail "--container requires a value"
            container_name="$2"
            shift 2
            ;;
        --include-udf)
            include_udf="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$provider" ]] || fail "--provider is required"
[[ -n "$resource" ]] || fail "--resource is required"
[[ ${#selectors[@]} -gt 0 ]] || fail "at least one --selector is required"

case "$output_format" in
    table|json)
        ;;
    *)
        fail "--format must be table or json"
        ;;
esac

# Version 1 intentionally proves one canonical resource. The acquisition request
# remains provider-neutral and is executed by the Central Orchestrator.
case "$resource" in
    endpoint)
        ;;
    *)
        fail "unsupported canonical resource in probe version 1: $resource"
        ;;
esac

if ! docker inspect "$container_name" >/dev/null 2>&1; then
    fail "runtime container does not exist: $container_name"
fi

runtime_status="$(
    docker inspect "$container_name" \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}'
)"

if [[ "$runtime_status" != "healthy" && "$runtime_status" != "running" ]]; then
    fail "runtime container is not healthy/running: $runtime_status"
fi

repo="/home/al/projects/jason"
host_python="$repo/.venv/bin/python"

if [[ ! -x "$host_python" ]]; then
    host_python="$(command -v python3 || true)"
fi

[[ -n "$host_python" ]] || fail "host Python is unavailable"

selectors_json="$(
    "$host_python" - "${selectors[@]}" <<'PY'
import json
import re
import sys

result = {}

for item in sys.argv[1:]:
    if "=" not in item:
        raise SystemExit(
            f"ERROR: invalid selector {item!r}; expected KEY=VALUE"
        )

    key, value = item.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        raise SystemExit(
            f"ERROR: invalid selector key {key!r}"
        )

    if not value:
        raise SystemExit(
            f"ERROR: selector value is empty for {key!r}"
        )

    if key in result:
        raise SystemExit(
            f"ERROR: duplicate selector key {key!r}"
        )

    result[key] = value

print(
    json.dumps(
        result,
        separators=(",", ":"),
    )
)
PY
)"

required_paths_json="$(
    "$host_python" - "${required_paths[@]}" <<'PY'
import json
import sys

paths = []

for item in sys.argv[1:]:
    value = item.strip()

    if not value.startswith("/"):
        raise SystemExit(
            f"ERROR: required path must be an absolute JSON Pointer: {value!r}"
        )

    paths.append(value)

print(
    json.dumps(
        paths,
        separators=(",", ":"),
    )
)
PY
)"

docker exec -i \
    -e "PROBE_PROVIDER=$provider" \
    -e "PROBE_RESOURCE=$resource" \
    -e "PROBE_PRINCIPAL=$principal" \
    -e "PROBE_SELECTORS_JSON=$selectors_json" \
    -e "PROBE_REQUIRED_PATHS_JSON=$required_paths_json" \
    -e "PROBE_FORMAT=$output_format" \
    -e "PROBE_FILTER=$filter_text" \
    -e "PROBE_INCLUDE_UDF=$include_udf" \
    "$container_name" \
    python - <<'PY'
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections.abc import Mapping
from typing import Any

from jason_runtime.composition import (
    RuntimeSettings,
    build_runtime_application,
)
from orchestrator.teams_conversation_flow import (
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


expected_provider = os.environ["PROBE_PROVIDER"].strip()
resource = os.environ["PROBE_RESOURCE"].strip()
principal_id = os.environ["PROBE_PRINCIPAL"].strip()
output_format = os.environ["PROBE_FORMAT"].strip()
filter_text = os.environ.get("PROBE_FILTER", "").strip().casefold()
include_udf = (
    os.environ.get("PROBE_INCLUDE_UDF", "false")
    .strip()
    .casefold()
    in {"1", "true", "yes", "on"}
)

try:
    selectors = json.loads(
        os.environ["PROBE_SELECTORS_JSON"]
    )
    required_paths = tuple(
        json.loads(
            os.environ["PROBE_REQUIRED_PATHS_JSON"]
        )
    )
except json.JSONDecodeError as exc:
    fail(f"probe input JSON is invalid: {exc}")

if not isinstance(selectors, dict) or not selectors:
    fail("selectors must be a non-empty object")

if resource != "endpoint":
    fail(f"unsupported canonical resource: {resource}")

settings = RuntimeSettings.from_env()
application = build_runtime_application(settings)

outer_ingress = getattr(
    application.ingress,
    "ingress",
    None,
)
flow = getattr(
    outer_ingress,
    "flow",
    None,
)

if flow is None:
    fail("production Teams conversation flow is unavailable")

connection = None

try:
    connection = sqlite3.connect(
        f"file:{settings.bindings_db}?mode=ro",
        uri=True,
    )

    rows = connection.execute(
        """
        SELECT microsoft_tenant_id, microsoft_object_id
        FROM microsoft_identity_bindings
        WHERE jason_identity_id = ?
          AND status = 'active'
        ORDER BY microsoft_tenant_id, microsoft_object_id
        """,
        (principal_id,),
    ).fetchall()
except sqlite3.Error as exc:
    fail(f"identity binding database read failed: {exc}")
finally:
    if connection is not None:
        connection.close()

if len(rows) != 1:
    fail(
        "expected exactly one active Microsoft identity binding "
        f"for {principal_id}; found {len(rows)}"
    )

tenant_id, object_id = map(str, rows[0])

identity = TeamsConversationPrincipalEvidence(
    microsoft_tenant_id=tenant_id,
    microsoft_object_id=object_id,
    authentication_assurance="botframework-authenticated",
    conversation_id="provider-evidence-probe",
    message_id="provider-evidence-probe",
)

principal = flow.identity_binder.bind(identity)

if principal is None:
    fail("identity did not bind to an active Jason principal")

if any(
    key in selectors
    for key in (
        "resource_id",
        "device_uid",
    )
):
    capability_name = "endpoint.device.read"
else:
    capability_name = "endpoint.device.search"

arguments = {
    **selectors,
    # A non-empty provider-neutral fact request causes endpoint search to resolve
    # one durable resource and return the exact endpoint record. The probe does
    # not use the fact semantically.
    "requested_facts": ("hostname",),
    "result_intent": "inspect",
    "completeness_requirement": "sufficient",
}

intent = ConversationIntent(
    capability_name=capability_name,
    arguments=arguments,
    execution_mode="deterministic",
    permission_mode="observe",
    risk="low",
)

request = flow.request_factory.build(
    principal=principal,
    intent=intent,
    identity=identity,
)

result = flow.orchestrator.execute(request)

if result.status.value != "succeeded":
    fail(
        "governed resource read failed; "
        f"status={result.status.value}; "
        f"reason_codes={','.join(result.reason_codes)}"
    )

resolved_provider = str(
    result.provider_id or ""
).strip()

output_provider = str(
    result.output.get("provider", "")
).strip()

if not resolved_provider:
    fail("orchestration result has no provider provenance")

if output_provider != resolved_provider:
    fail(
        "connector output provider does not match "
        "orchestration provider provenance"
    )

if resolved_provider != expected_provider:
    fail(
        "resolved provider did not match expected provider; "
        f"expected={expected_provider}; "
        f"resolved={resolved_provider}"
    )

data = result.output.get("data")

if not isinstance(data, Mapping):
    fail("provider result data is not an object")

raw_provider_data = data.get("provider_data")

if isinstance(raw_provider_data, Mapping):
    provider_data = dict(raw_provider_data)
    provider_data_path = "/data/provider_data"
else:
    provider_data = dict(data)
    provider_data_path = "/data"

resource_matches = data.get("resource_matches", ())

if isinstance(resource_matches, (list, tuple)):
    match_count = len(resource_matches)
else:
    match_count = 0

resource_id_present = bool(
    data.get("resolved_resource_id")
    or provider_data.get("uid")
    or provider_data.get("id")
)

sensitive_key = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|"
    r"api[-_]?key|private[-_]?key)",
    flags=re.IGNORECASE,
)


def escape_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def scalar_preview(value: Any) -> str:
    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ) or value is None:
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    return json.dumps(
        str(value),
        ensure_ascii=False,
    )


def resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer in {"", "/"}:
        return document

    if not pointer.startswith("/"):
        raise LookupError(
            f"JSON Pointer is not absolute: {pointer}"
        )

    current = document

    for raw_segment in pointer.split("/")[1:]:
        segment = (
            raw_segment
            .replace("~1", "/")
            .replace("~0", "~")
        )

        if isinstance(current, Mapping):
            if segment not in current:
                raise LookupError(
                    f"evidence path does not exist: {pointer}"
                )
            current = current[segment]
            continue

        if isinstance(current, (list, tuple)):
            try:
                index = int(segment)
            except ValueError as exc:
                raise LookupError(
                    f"invalid array index in evidence path: {pointer}"
                ) from exc

            if index < 0 or index >= len(current):
                raise LookupError(
                    f"array index outside evidence path: {pointer}"
                )

            current = current[index]
            continue

        raise LookupError(
            f"evidence path traverses a scalar: {pointer}"
        )

    return current


def sanitize_tree(
    value: Any,
    *,
    key_name: str | None = None,
    depth: int = 0,
) -> Any:
    if key_name and sensitive_key.search(key_name):
        return "[REDACTED]"

    if depth > 10:
        return "[MAX_DEPTH_REACHED]"

    if isinstance(value, Mapping):
        sanitized = {}

        for raw_key in sorted(
            value,
            key=lambda item: str(item).casefold(),
        ):
            key = str(raw_key)

            if key.casefold() == "udf" and not include_udf:
                child = value[raw_key]
                count = (
                    len(child)
                    if isinstance(child, Mapping)
                    else 0
                )
                sanitized[key] = (
                    f"[OMITTED_UDF_OBJECT keys={count}; "
                    "use --include-udf to include]"
                )
                continue

            if key.casefold() == "semantic_evidence":
                sanitized[key] = (
                    "[OMITTED_DERIVED_ADAPTER_VIEW]"
                )
                continue

            sanitized[key] = sanitize_tree(
                value[raw_key],
                key_name=key,
                depth=depth + 1,
            )

        return sanitized

    if isinstance(value, (list, tuple)):
        maximum = 50
        items = [
            sanitize_tree(
                child,
                depth=depth + 1,
            )
            for child in value[:maximum]
        ]

        if len(value) > maximum:
            items.append(
                f"[TRUNCATED remaining={len(value) - maximum}]"
            )

        return items

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ) or value is None:
        return value

    return str(value)


def flatten(
    value: Any,
    *,
    pointer: str = "",
    key_name: str | None = None,
    depth: int = 0,
):
    if key_name and sensitive_key.search(key_name):
        yield pointer or "/", "[REDACTED]"
        return

    if depth > 10:
        yield pointer or "/", "[MAX_DEPTH_REACHED]"
        return

    if isinstance(value, Mapping):
        if not value:
            yield pointer or "/", "<empty object>"
            return

        for raw_key in sorted(
            value,
            key=lambda item: str(item).casefold(),
        ):
            key = str(raw_key)
            child_pointer = (
                f"{pointer}/{escape_pointer_segment(key)}"
            )

            if key.casefold() == "udf" and not include_udf:
                child = value[raw_key]
                count = (
                    len(child)
                    if isinstance(child, Mapping)
                    else 0
                )
                yield (
                    child_pointer,
                    f"<omitted UDF object keys={count}; "
                    "use --include-udf to include>",
                )
                continue

            if key.casefold() == "semantic_evidence":
                yield (
                    child_pointer,
                    "<omitted derived adapter view>",
                )
                continue

            yield from flatten(
                value[raw_key],
                pointer=child_pointer,
                key_name=key,
                depth=depth + 1,
            )

        return

    if isinstance(value, (list, tuple)):
        yield pointer or "/", f"<array count={len(value)}>"

        for index, child in enumerate(value[:50]):
            yield from flatten(
                child,
                pointer=f"{pointer}/{index}",
                depth=depth + 1,
            )

        if len(value) > 50:
            yield (
                pointer or "/",
                f"<truncated remaining={len(value) - 50}>",
            )

        return

    yield pointer or "/", value


required_results = []

for pointer in required_paths:
    try:
        value = resolve_pointer(
            provider_data,
            pointer,
        )
    except LookupError as exc:
        fail(str(exc))

    required_results.append(
        {
            "path": pointer,
            "value": value,
        }
    )

sanitized = sanitize_tree(provider_data)
rows = list(flatten(provider_data))

if filter_text:
    rows = [
        (path, value)
        for path, value in rows
        if filter_text in path.casefold()
    ]

    if not rows:
        fail(
            "no provider evidence paths matched filter: "
            + filter_text
        )

if output_format == "json":
    print(
        json.dumps(
            {
                "probe_status": "PASS",
                "mode": "production_central_orchestrator",
                "principal": principal_id,
                "canonical_resource": resource,
                "canonical_capability": capability_name,
                "selectors": selectors,
                "expected_provider": expected_provider,
                "resolved_provider": resolved_provider,
                "provider_data_path": provider_data_path,
                "resource_match_count": match_count,
                "resource_id_present": resource_id_present,
                "required_paths": required_results,
                "provider_data": sanitized,
                "semantic_interpretation_performed": False,
                "semantic_mapping_required": False,
                "provider_mutation_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
else:
    print("========== PROVIDER EVIDENCE PROBE ==========")
    print("PROBE_STATUS=PASS")
    print("MODE=production_central_orchestrator")
    print(f"PRINCIPAL={principal_id}")
    print(f"CANONICAL_RESOURCE={resource}")
    print(f"CANONICAL_CAPABILITY={capability_name}")
    print(
        "SELECTORS="
        + json.dumps(
            selectors,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    print(f"EXPECTED_PROVIDER={expected_provider}")
    print(f"RESOLVED_PROVIDER={resolved_provider}")
    print(f"PROVIDER_DATA_PATH={provider_data_path}")
    print(f"RESOURCE_MATCH_COUNT={match_count}")
    print(f"RESOURCE_ID_PRESENT={resource_id_present}")

    for item in required_results:
        print(
            "REQUIRED_PATH=PASS "
            f"path={item['path']} "
            f"value={scalar_preview(item['value'])}"
        )

    print("---------- AVAILABLE PROVIDER DATA ----------")

    for path, value in rows:
        print(
            f"{path:<58} "
            f"{scalar_preview(value)}"
        )

    print("---------- CONTROL STATEMENTS ----------")
    print("SEMANTIC_INTERPRETATION_PERFORMED=False")
    print("SEMANTIC_MAPPING_REQUIRED=False")
    print("PROVIDER_MUTATION_PERFORMED=False")
    print("========== END PROVIDER EVIDENCE PROBE ==========")
PY
