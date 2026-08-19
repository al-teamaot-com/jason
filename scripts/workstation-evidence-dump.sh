#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Workstation Evidence Dump

Purpose:
  Collect every directly workstation-related Datto RMM read surface currently
  documented in the official v2 API, plus immediate site/network context.

Usage:
  workstation-evidence-dump.sh --hostname AOT-50282 [options]

Options:
  --hostname NAME          Exact Datto hostname. Required.
  --output PATH            JSON output path. Default: /tmp/jason-workstation-evidence-<hostname>.json
  --container NAME         Runtime container. Default: jason-runtime
  --include-site-context   Also collect site settings and site variables.
  --print-json             Print the full JSON after the summary.
  --help                   Show this help.

Safety:
  This tool performs GET requests only. It never runs components, quick jobs,
  scripts, mutations, writes, semantic mappings, or AI interpretation.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

hostname=""
container_name="jason-runtime"
output_path=""
include_site_context="false"
print_json="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostname)
            [[ $# -ge 2 ]] || fail "--hostname requires a value"
            hostname="$2"
            shift 2
            ;;
        --output)
            [[ $# -ge 2 ]] || fail "--output requires a path"
            output_path="$2"
            shift 2
            ;;
        --container)
            [[ $# -ge 2 ]] || fail "--container requires a value"
            container_name="$2"
            shift 2
            ;;
        --include-site-context)
            include_site_context="true"
            shift
            ;;
        --print-json)
            print_json="true"
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

[[ -n "$hostname" ]] || fail "--hostname is required"

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

if [[ -z "$output_path" ]]; then
    safe_hostname="$(printf '%s' "$hostname" | tr -c 'A-Za-z0-9._-' '_')"
    output_path="/tmp/jason-workstation-evidence-${safe_hostname}.json"
fi

output_dir="$(dirname "$output_path")"
mkdir -p "$output_dir"
tmp_path="${output_path}.tmp.$$"
trap 'rm -f "$tmp_path"' EXIT

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
host_python="$repo_root/.venv/bin/python"
if [[ ! -x "$host_python" ]]; then
    host_python="$(command -v python3 || true)"
fi
[[ -n "$host_python" ]] || fail "host Python is unavailable for evidence sanitization"

docker exec -i \
    -e "PROBE_HOSTNAME=$hostname" \
    -e "PROBE_INCLUDE_SITE_CONTEXT=$include_site_context" \
    "$container_name" \
    python - <<'PY' | \
    PYTHONPATH="$repo_root/implementation${PYTHONPATH:+:$PYTHONPATH}" \
    "$host_python" -c '
import json
import sys
from orchestrator.evidence_sanitization import sanitize_evidence_tree

evidence = json.load(sys.stdin)
safe = sanitize_evidence_tree(evidence)
json.dump(safe, sys.stdout, indent=2, ensure_ascii=False, default=str)
sys.stdout.write("\n")
' > "$tmp_path"
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from jason_runtime.composition import RuntimeSettings
from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


HOSTNAME = os.environ["PROBE_HOSTNAME"].strip()
INCLUDE_SITE_CONTEXT = (
    os.environ.get("PROBE_INCLUDE_SITE_CONTEXT", "false").strip().casefold()
    in {"1", "true", "yes", "on"}
)
MAX_PAGES = 100
MAX_PAGE_SIZE = 250

if not HOSTNAME:
    raise SystemExit("ERROR: hostname is empty")

settings = RuntimeSettings.from_env()
transport = UrlLibJsonHttpTransport()
context = ConnectorContext(
    correlation_id="workstation-evidence-dump",
    principal_id="diagnostic-readonly",
    organization_id="aot",
    client_id=None,
    capability="datto_rmm.device.search",
    mode="observe",
)
secrets = OpenBaoSecretResolver(
    base_url=settings.openbao_url,
    role_id_path=settings.openbao_role_id_path,
    secret_id_path=settings.openbao_secret_id_path,
)
credentials = secrets.resolve("datto_rmm.readonly", context)
require_durable_credentials(credentials)
token = acquire_access_token(credentials=credentials)
base_url = str(credentials["api_url"]).rstrip("/")
headers = {
    "Authorization": f"{token.token_type} {token.access_token}",
    "Accept": "application/json",
}


def api_url(path_or_url: str) -> str:
    value = path_or_url.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/api/"):
        return base_url + value
    if value.startswith("/v2/"):
        return base_url + "/api" + value
    return urljoin(base_url + "/api/", value.lstrip("/"))


def get(path_or_url: str, params: Mapping[str, Any] | None = None) -> Any:
    return transport.request(
        method="GET",
        url=api_url(path_or_url),
        headers=headers,
        params=params,
        json=None,
        timeout_seconds=30,
    )


def capture(name: str, path: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = get(path, params=params)
        return {
            "status": "available",
            "method": "GET",
            "path": path,
            "payload": payload,
        }
    except Exception as exc:  # diagnostic must preserve partial evidence
        return {
            "status": "unavailable",
            "method": "GET",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def next_page_url(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    details = payload.get("pageDetails")
    if not isinstance(details, Mapping):
        return None
    value = details.get("nextPageUrl")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def capture_pages(name: str, path: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    initial_params = dict(params or {})
    initial_params.setdefault("max", MAX_PAGE_SIZE)
    pages: list[Any] = []
    urls_seen: set[str] = set()
    current_path = path
    current_params: Mapping[str, Any] | None = initial_params

    try:
        for _ in range(MAX_PAGES):
            payload = get(current_path, params=current_params)
            pages.append(payload)
            nxt = next_page_url(payload)
            if not nxt:
                return {
                    "status": "available",
                    "method": "GET",
                    "path": path,
                    "pages": pages,
                    "page_count": len(pages),
                    "complete": True,
                }
            normalized = api_url(nxt)
            if normalized in urls_seen:
                return {
                    "status": "partial",
                    "method": "GET",
                    "path": path,
                    "pages": pages,
                    "page_count": len(pages),
                    "complete": False,
                    "warning": "pagination nextPageUrl repeated",
                }
            urls_seen.add(normalized)
            current_path = normalized
            current_params = None

        return {
            "status": "partial",
            "method": "GET",
            "path": path,
            "pages": pages,
            "page_count": len(pages),
            "complete": False,
            "warning": f"pagination exceeded {MAX_PAGES} pages",
        }
    except Exception as exc:
        return {
            "status": "partial" if pages else "unavailable",
            "method": "GET",
            "path": path,
            "pages": pages,
            "page_count": len(pages),
            "complete": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def iter_records(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "pageDetails":
                continue
            if isinstance(child, Sequence) and not isinstance(child, (str, bytes, bytearray)):
                for item in child:
                    if isinstance(item, Mapping):
                        yield item
            elif isinstance(child, Mapping):
                yield from iter_records(child)


def records_from_pages(section: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for page in section.get("pages", ()) if isinstance(section, Mapping) else ():
        result.extend(iter_records(page))
    return result


def first_scalar(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def exact_device_search(hostname: str) -> Mapping[str, Any]:
    search = capture_pages(
        "device_discovery",
        "/api/v2/account/devices",
        params={"hostname": hostname, "max": 100},
    )
    if search["status"] not in {"available", "partial"}:
        raise RuntimeError(f"device discovery failed: {search.get('error', 'unknown error')}")
    candidates: list[Mapping[str, Any]] = []
    for record in records_from_pages(search):
        if first_scalar(record, "hostname", "name").casefold() == hostname.casefold():
            candidates.append(record)
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one exact Datto hostname match for {hostname}; found {len(candidates)}"
        )
    return candidates[0]


def extract_alert_uids(section: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for record in records_from_pages(section):
        uid = first_scalar(record, "uid", "alertUid", "alert_uid")
        if uid and uid not in seen:
            seen.add(uid)
            found.append(uid)
    return found


def filter_device_records(section: Mapping[str, Any], *, uid: str, hostname: str) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for record in records_from_pages(section):
        record_uid = first_scalar(record, "uid", "deviceUid", "device_uid")
        record_hostname = first_scalar(record, "hostname", "name")
        if record_uid == uid or (record_hostname and record_hostname.casefold() == hostname.casefold()):
            fingerprint = json.dumps(record, sort_keys=True, default=str)
            if fingerprint not in seen:
                seen.add(fingerprint)
                matches.append(record)
    return matches


discovery_record = exact_device_search(HOSTNAME)
device_uid = first_scalar(discovery_record, "uid", "deviceUid", "device_uid")
site_uid = first_scalar(discovery_record, "siteUid", "site_uid")

if not device_uid:
    raise SystemExit("ERROR: exact Datto device did not expose a durable UID")

sections: dict[str, Any] = {}
sections["device"] = capture("device", f"/api/v2/device/{device_uid}")

# Official Datto RMM v2 workstation/device read surfaces.
sections["patches"] = capture_pages("patches", f"/api/v2/device/{device_uid}/patches")
sections["patch_management_policies"] = capture(
    "patch_management_policies",
    f"/api/v2/device/{device_uid}/site/patch-management",
)
sections["alerts_open"] = capture_pages(
    "alerts_open",
    f"/api/v2/device/{device_uid}/alerts/open",
)
sections["alerts_resolved"] = capture_pages(
    "alerts_resolved",
    f"/api/v2/device/{device_uid}/alerts/resolved",
)
sections["audit"] = capture("audit", f"/api/v2/audit/device/{device_uid}")
sections["software"] = capture_pages(
    "software",
    f"/api/v2/audit/device/{device_uid}/software",
)

# Expand each alert to the dedicated alert detail resource.
alert_details: dict[str, Any] = {}
for alert_uid in extract_alert_uids(sections["alerts_open"]) + extract_alert_uids(sections["alerts_resolved"]):
    if alert_uid in alert_details:
        continue
    alert_details[alert_uid] = capture(
        f"alert_{alert_uid}",
        f"/api/v2/alert/{alert_uid}",
    )
sections["alert_details"] = {
    "status": "available",
    "method": "GET",
    "path": "/api/v2/alert/{alertUid}",
    "alerts": alert_details,
    "count": len(alert_details),
}

# Immediate site context that can add workstation/network information.
if site_uid:
    sections["site"] = capture("site", f"/api/v2/site/{site_uid}")
    site_network = capture_pages(
        "site_network_interfaces",
        f"/api/v2/site/{site_uid}/devices/network-interface",
    )
    sections["site_network_interfaces"] = {
        **site_network,
        "matching_device_records": filter_device_records(
            site_network,
            uid=device_uid,
            hostname=HOSTNAME,
        ),
    }
    if INCLUDE_SITE_CONTEXT:
        sections["site_settings"] = capture(
            "site_settings",
            f"/api/v2/site/{site_uid}/settings",
        )
        sections["site_variables"] = capture_pages(
            "site_variables",
            f"/api/v2/site/{site_uid}/variables",
        )
else:
    sections["site"] = {
        "status": "not_applicable",
        "reason": "device discovery record did not expose siteUid",
    }
    sections["site_network_interfaces"] = {
        "status": "not_applicable",
        "reason": "device discovery record did not expose siteUid",
    }

coverage = [
    {"method": "GET", "path": "/v2/device/{deviceUid}", "section": "device", "attempted": True},
    {"method": "GET", "path": "/v2/device/{deviceUid}/patches", "section": "patches", "attempted": True},
    {"method": "GET", "path": "/v2/device/{deviceUid}/site/patch-management", "section": "patch_management_policies", "attempted": True},
    {"method": "GET", "path": "/v2/device/{deviceUid}/alerts/open", "section": "alerts_open", "attempted": True},
    {"method": "GET", "path": "/v2/device/{deviceUid}/alerts/resolved", "section": "alerts_resolved", "attempted": True},
    {"method": "GET", "path": "/v2/audit/device/{deviceUid}", "section": "audit", "attempted": True},
    {"method": "GET", "path": "/v2/audit/device/{deviceUid}/software", "section": "software", "attempted": True},
    {"method": "GET", "path": "/v2/alert/{alertUid}", "section": "alert_details", "attempted": True, "condition": "for alert UIDs discovered on this device"},
    {"method": "GET", "path": "/v2/site/{siteUid}", "section": "site", "attempted": bool(site_uid), "condition": "when siteUid is present"},
    {"method": "GET", "path": "/v2/site/{siteUid}/devices/network-interface", "section": "site_network_interfaces", "attempted": bool(site_uid), "condition": "filtered back to the target workstation"},
    {"method": "GET", "path": "/v2/site/{siteUid}/settings", "section": "site_settings", "attempted": bool(site_uid and INCLUDE_SITE_CONTEXT), "condition": "--include-site-context"},
    {"method": "GET", "path": "/v2/site/{siteUid}/variables", "section": "site_variables", "attempted": bool(site_uid and INCLUDE_SITE_CONTEXT), "condition": "--include-site-context"},
    {"method": "GET", "path": "/v2/job/{jobUid} and result/stdout/stderr endpoints", "attempted": False, "reason": "current documented API requires a known jobUid and does not provide a device-to-all-jobs enumeration from hostname/deviceUid alone"},
    {"method": "PUT", "path": "/v2/device/{deviceUid}/quickjob", "attempted": False, "reason": "write/action endpoint intentionally excluded from a read-only evidence dump"},
    {"method": "GET", "path": "/v2/activity-logs", "attempted": False, "reason": "site/account activity stream is not a workstation-specific evidence surface in the current documented query contract"},
]

output = {
    "schema": "jason.workstation_evidence_dump.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "provider": "datto_rmm",
    "provider_documentation": {
        "human": "https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm",
        "openapi": "https://vidal-api.centrastage.net/api/v3/api-docs/Datto-RMM",
        "api_version": "v2",
    },
    "request": {
        "hostname": HOSTNAME,
        "mode": "read_only_diagnostic",
        "include_site_context": INCLUDE_SITE_CONTEXT,
    },
    "identity": {
        "hostname": HOSTNAME,
        "device_uid": device_uid,
        "site_uid": site_uid or None,
        "discovery_record": discovery_record,
    },
    "coverage": coverage,
    "sections": sections,
    "control": {
        "http_methods_used": ["GET"],
        "provider_mutation_performed": False,
        "quick_job_executed": False,
        "component_executed": False,
        "semantic_mapping_used": False,
        "ai_interpretation_used": False,
    },
}

print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
PY

mv "$tmp_path" "$output_path"
trap - EXIT

"$host_python" - "$output_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
sections = data.get("sections", {})
identity = data.get("identity", {})

print("========== WORKSTATION EVIDENCE DUMP ==========")
print("DUMP_STATUS=PASS")
print(f"PROVIDER={data.get('provider')}")
print(f"HOSTNAME={identity.get('hostname')}")
print(f"DEVICE_UID_PRESENT={bool(identity.get('device_uid'))}")
print(f"SITE_UID_PRESENT={bool(identity.get('site_uid'))}")
print(f"OUTPUT={path}")
print("---------- SECTION STATUS ----------")
for name in sorted(sections):
    section = sections[name]
    if isinstance(section, dict):
        status = section.get("status", "unknown")
        pages = section.get("page_count")
        suffix = f" pages={pages}" if pages is not None else ""
        print(f"{name}: {status}{suffix}")
    else:
        print(f"{name}: unknown")
print("---------- CONTROL ----------")
control = data.get("control", {})
for key in sorted(control):
    print(f"{key}={control[key]}")
print("========== END WORKSTATION EVIDENCE DUMP ==========")
PY

if [[ "$print_json" == "true" ]]; then
    cat "$output_path"
fi
