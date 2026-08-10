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
from connectors.datto_rmm.connector import DattoRmmConnector


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
            raise ConnectorTransportError(
                "Bounded Datto RMM discovery permits GET only."
            )
        query = urllib.parse.urlencode(
            {key: value for key, value in (params or {}).items() if value is not None}
        )
        request_url = f"{url}?{query}" if query else url
        req = urllib.request.Request(request_url, headers=dict(headers), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ConnectorTransportError(
                f"Datto RMM discovery failed with HTTP {exc.code}."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError("Datto RMM discovery failed.") from exc
        try:
            payload = __import__("json").loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ConnectorTransportError(
                "Datto RMM discovery returned invalid JSON."
            ) from exc
        if not isinstance(payload, Mapping):
            raise ConnectorTransportError(
                "Datto RMM discovery returned an unexpected shape."
            )
        return payload


def _safe_identity(record: Mapping[str, Any]) -> Mapping[str, str]:
    aliases = {
        "hostname": ("hostname", "name"),
        "serial_number": ("serialNumber", "serial_number"),
        "device_uid": ("uid", "deviceUid", "device_uid"),
    }
    safe: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            value = record.get(name)
            if isinstance(value, (str, int)) and str(value).strip():
                safe[canonical] = str(value).strip()
                break
    return safe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover at most one Datto RMM device through the governed read "
            "boundary while printing only approved identity attributes."
        )
    )
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--search", required=False, default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.live_read:
        print(
            json.dumps(
                {
                    "provider": "datto_rmm",
                    "capability": "datto_rmm.device.search",
                    "maximum_records": 1,
                    "search_supplied": bool(args.search),
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

    context = ConnectorContext(
        correlation_id="datto-convergence-candidate-discovery",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.device.search",
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/role-id"
        ),
        secret_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/secret-id"
        ),
    )
    audit = SanitizedAudit()
    connector = DattoRmmConnector(
        secrets=resolver,
        transport=UrlLibJsonTransport(),
        audit=audit,
    )
    result = connector.execute(
        ConnectorRequest(
            context=context,
            arguments={"search": args.search, "page": 1, "max": 1},
        )
    )

    devices = result.data.get("devices")
    if not isinstance(devices, list):
        raise SystemExit("DENIED: Datto response did not contain a device collection")
    if len(devices) > 1:
        raise SystemExit("DENIED: provider returned more than one device")

    candidate: Mapping[str, Any] | None = None
    if devices:
        record = devices[0]
        if not isinstance(record, Mapping):
            raise SystemExit("DENIED: device record has an unexpected shape")
        safe_identity = _safe_identity(record)
        if "device_uid" not in safe_identity:
            raise SystemExit("DENIED: device record has no stable external ID")
        candidate = {"identity_attributes": safe_identity}

    print(
        json.dumps(
            {
                "provider": result.provider,
                "capability": result.capability,
                "maximum_records": 1,
                "candidate_count": len(devices),
                "candidate": candidate,
                "audit_events": audit.events,
                "network_contacted": True,
                "provider_credentials_used": True,
                "access_token_persisted": False,
                "raw_provider_payload_persisted": False,
                "raw_provider_payload_printed": False,
                "status": "pass",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
