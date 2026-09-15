#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))

from connectors.core.contracts import ConnectorContext, ConnectorRequest, ConnectorTransportError
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials
from connectors.datto_rmm.connector import DattoRmmConnector


READ_BOOTSTRAP = Path("/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle")
EXECUTION_BOOTSTRAP = Path(
    "/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle"
)
EXECUTION_LOGICAL_SECRET = "datto_rmm.execution"
EXECUTION_SECRET_PATH = "secret/data/connectors/datto-rmm/production/execution"
EXECUTION_FIELDS = frozenset({"api_url", "api_key", "api_secret"})


class SanitizedAudit:
    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        return None


class GetOnlyJsonTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        if method != "GET" or json is not None:
            raise ConnectorTransportError("Device Visibility probe permits GET only.")
        query = urllib.parse.urlencode(
            {key: value for key, value in (params or {}).items() if value is not None}
        )
        request_url = f"{url}?{query}" if query else url
        request = urllib.request.Request(
            request_url,
            headers=dict(headers),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            error.read()
            raise ConnectorTransportError(
                f"Datto RMM read failed with HTTP {int(error.code)}."
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ConnectorTransportError("Datto RMM read failed.") from error
        try:
            payload = __import__("json").loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ConnectorTransportError("Datto RMM returned invalid JSON.") from error
        if not isinstance(payload, Mapping):
            raise ConnectorTransportError("Datto RMM returned an unexpected shape.")
        return payload


def get_status(*, url: str, token_type: str, access_token: str) -> int:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"{token_type} {access_token}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15.0) as response:
            response.read()
            return int(response.status)
    except urllib.error.HTTPError as error:
        error.read()
        return int(error.code)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Datto RMM Device Visibility probe request failed.") from error


def assess_device_visibility(records: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    resolved = [record for record in records if record.get("readonly_resolution") == "unique"]
    positive = [
        record
        for record in resolved
        if record.get("execution_site_http") == 200
        and record.get("execution_device_http") == 200
    ]
    negative = [
        record
        for record in resolved
        if record.get("execution_site_http") == 200
        and record.get("execution_device_http") in (403, 404)
    ]
    unexpected = [
        record
        for record in resolved
        if record.get("execution_site_http") not in (200,)
        or record.get("execution_device_http") not in (200, 403, 404)
    ]
    passed = bool(positive) and bool(negative) and not unexpected
    return {
        "resolved_candidate_count": len(resolved),
        "visible_candidate_count": len(positive),
        "hidden_candidate_count": len(negative),
        "unexpected_candidate_count": len(unexpected),
        "positive_visibility_proven": bool(positive),
        "negative_visibility_proven": bool(negative),
        "device_visibility_proven": passed,
        "status": "pass" if passed else "inconclusive",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve named Datto devices through the existing read-only identity, then "
            "use the separate execution identity for GET-only site/device checks. The "
            "probe prints labels and HTTP statuses only; it never prints provider IDs, "
            "credentials, tokens, or provider response bodies."
        )
    )
    parser.add_argument("--live-proof", action="store_true")
    parser.add_argument("--candidate", action="append", default=[])
    return parser


def preflight(candidates: list[str]) -> Mapping[str, Any]:
    return {
        "provider": "datto_rmm",
        "proof_scope": "device_visibility_positive_negative_get_only",
        "candidate_count": len(candidates),
        "network_contacted": False,
        "provider_credentials_used": False,
        "provider_mutation_requests": 0,
        "component_execution_attempted": False,
        "runtime_execution_activated": False,
        "provider_ids_printed": False,
        "provider_response_bodies_printed": False,
        "provider_response_bodies_persisted": False,
        "status": "credential_safe_preflight",
    }


def resolve_candidate(
    *,
    connector: DattoRmmConnector,
    label: str,
) -> Mapping[str, str]:
    context = ConnectorContext(
        correlation_id="drmm-execution-device-visibility-proof",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.device.search",
        mode="observe",
    )
    result = connector.execute(
        ConnectorRequest(
            context=context,
            arguments={"hostname": label},
        )
    )
    data = result.data
    if not isinstance(data, Mapping):
        return {"resolution": "invalid"}
    matches = data.get("resource_matches")
    if not isinstance(matches, list):
        return {"resolution": "invalid"}
    if data.get("discovery_complete") is False:
        return {"resolution": "incomplete"}
    if len(matches) == 0:
        return {"resolution": "zero"}
    if len(matches) != 1:
        return {"resolution": "ambiguous"}
    match = matches[0]
    if not isinstance(match, Mapping):
        return {"resolution": "invalid"}
    resource_id = str(
        data.get("resolved_resource_id") or match.get("resource_id") or ""
    ).strip()
    site_id = str(match.get("site_id") or "").strip()
    if not resource_id or not site_id:
        return {"resolution": "missing_durable_identity"}
    return {
        "resolution": "unique",
        "resource_id": resource_id,
        "site_id": site_id,
    }


def main() -> int:
    args = build_parser().parse_args()
    candidates = []
    seen = set()
    for raw in args.candidate:
        label = str(raw).strip()
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            candidates.append(label)

    if not args.live_proof:
        print(json.dumps(preflight(candidates), indent=2, sort_keys=True))
        return 0

    if len(candidates) < 2:
        raise SystemExit("DENIED: at least two named candidate devices are required")

    read_resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=READ_BOOTSTRAP / "role-id",
        secret_id_path=READ_BOOTSTRAP / "secret-id",
    )
    read_connector = DattoRmmConnector(
        secrets=read_resolver,
        transport=GetOnlyJsonTransport(),
        audit=SanitizedAudit(),
    )

    resolved_candidates: list[tuple[str, Mapping[str, str]]] = []
    records: list[dict[str, Any]] = []
    for label in candidates:
        resolution = resolve_candidate(connector=read_connector, label=label)
        state = str(resolution.get("resolution") or "invalid")
        record: dict[str, Any] = {
            "label": label,
            "readonly_resolution": state,
            "execution_site_http": None,
            "execution_device_http": None,
        }
        records.append(record)
        if state == "unique":
            resolved_candidates.append((label, resolution))

    if len(resolved_candidates) < 2:
        result = dict(assess_device_visibility(records))
        result.update(
            {
                "provider": "datto_rmm",
                "proof_scope": "device_visibility_positive_negative_get_only",
                "candidate_count": len(candidates),
                "candidates": records,
                "network_contacted": True,
                "provider_credentials_used": True,
                "provider_mutation_requests": 0,
                "component_execution_attempted": False,
                "runtime_execution_activated": False,
                "provider_ids_printed": False,
                "provider_response_bodies_printed": False,
                "provider_response_bodies_persisted": False,
            }
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    execution_context = ConnectorContext(
        correlation_id="drmm-execution-device-visibility-proof",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.execution.device_visibility.probe",
        mode="observe",
    )
    execution_resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=EXECUTION_BOOTSTRAP / "role-id",
        secret_id_path=EXECUTION_BOOTSTRAP / "secret-id",
        mappings={EXECUTION_LOGICAL_SECRET: EXECUTION_SECRET_PATH},
        allowed_fields={EXECUTION_LOGICAL_SECRET: EXECUTION_FIELDS},
    )
    credentials = execution_resolver.resolve(EXECUTION_LOGICAL_SECRET, execution_context)
    require_durable_credentials(credentials)
    token = acquire_access_token(credentials=credentials)
    try:
        base = credentials["api_url"].rstrip("/")
        record_by_label = {record["label"]: record for record in records}
        for label, resolution in resolved_candidates:
            site_id = resolution["site_id"]
            resource_id = resolution["resource_id"]
            record = record_by_label[label]
            record["execution_site_http"] = get_status(
                url=f"{base}/api/v2/site/{site_id}",
                token_type=token.token_type,
                access_token=token.access_token,
            )
            record["execution_device_http"] = get_status(
                url=f"{base}/api/v2/device/{resource_id}",
                token_type=token.token_type,
                access_token=token.access_token,
            )
    finally:
        token = None

    assessment = dict(assess_device_visibility(records))
    assessment.update(
        {
            "provider": "datto_rmm",
            "proof_scope": "device_visibility_positive_negative_get_only",
            "candidate_count": len(candidates),
            "candidates": records,
            "network_contacted": True,
            "provider_credentials_used": True,
            "provider_mutation_requests": 0,
            "component_execution_attempted": False,
            "runtime_execution_activated": False,
            "provider_ids_printed": False,
            "provider_response_bodies_printed": False,
            "provider_response_bodies_persisted": False,
        }
    )
    print(json.dumps(assessment, indent=2, sort_keys=True))
    return 0 if assessment["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
