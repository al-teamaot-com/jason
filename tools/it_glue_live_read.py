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
from connectors.core.resource_gateway import ResourceOperation, ResourceQuery
from connectors.it_glue.connector import ItGlueConnector
from connectors.kaseya_resource_catalog import build_kaseya_resource_registry
from connectors.provider_resource_adapters import translate_it_glue_resource


class SanitizedAudit:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        self.events.append(event_type)


class UrlLibJsonTransport:
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
            raise ConnectorTransportError("Bounded IT Glue live proof permits GET only.")
        query = urllib.parse.urlencode(
            {key: value for key, value in (params or {}).items() if value is not None}
        )
        request_url = f"{url}?{query}" if query else url
        req = urllib.request.Request(
            request_url,
            headers=dict(headers),
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ConnectorTransportError(
                f"IT Glue read failed with HTTP {exc.code}."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError("IT Glue read failed.") from exc
        try:
            payload = __import__("json").loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConnectorTransportError("IT Glue returned invalid JSON.") from exc
        if not isinstance(payload, Mapping):
            raise ConnectorTransportError("IT Glue returned an unexpected shape.")
        return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded governed IT Glue Organizations read (page size 1) "
            "without printing credentials or raw provider records."
        )
    )
    parser.add_argument("--live-read", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.live_read:
        print(
            json.dumps(
                {
                    "provider": "it_glue",
                    "logical_secret": "it_glue.readonly",
                    "capability": "it_glue.entity.query",
                    "entity": "Organizations",
                    "maximum_records": 1,
                    "network_contacted": False,
                    "provider_credentials_used": False,
                    "raw_provider_payload_persisted": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    registry = build_kaseya_resource_registry()
    query = ResourceQuery(
        provider="it_glue",
        resource_type="entity",
        operation=ResourceOperation.QUERY,
        organization_id="aot",
        filters={"entity": "Organizations"},
        page_size=1,
    )
    registry.authorize(query)
    invocation = translate_it_glue_resource(query)

    if invocation.capability != "it_glue.entity.query":
        raise SystemExit("DENIED: unexpected IT Glue capability translation")
    if invocation.arguments.get("page_size") != 1:
        raise SystemExit("DENIED: IT Glue query is not bounded to one record")

    context = ConnectorContext(
        correlation_id="itglue-first-live-read",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability=invocation.capability,
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/role-id"
        ),
        secret_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/secret-id"
        ),
    )
    audit = SanitizedAudit()
    connector = ItGlueConnector(
        secrets=resolver,
        transport=UrlLibJsonTransport(),
        audit=audit,
    )
    result = connector.execute(
        ConnectorRequest(context=context, arguments=invocation.arguments)
    )

    top_level_keys = sorted(str(key) for key in result.data.keys())
    data = result.data.get("data")
    if not isinstance(data, list):
        raise SystemExit("DENIED: IT Glue response did not contain a JSON:API data collection")
    if len(data) > 1:
        raise SystemExit("DENIED: provider returned more than the bounded one-record limit")

    print(
        json.dumps(
            {
                "provider": result.provider,
                "capability": result.capability,
                "entity": "Organizations",
                "maximum_records": 1,
                "collection_counts": {"data": len(data)},
                "network_contacted": True,
                "provider_credentials_used": True,
                "raw_provider_payload_persisted": False,
                "raw_provider_payload_printed": False,
                "response_top_level_keys": top_level_keys,
                "audit_events": audit.events,
                "status": "pass",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
