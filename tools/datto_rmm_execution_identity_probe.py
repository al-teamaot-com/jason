#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


LOGICAL_SECRET = "datto_rmm.execution"
EXECUTION_SECRET_PATH = "secret/data/connectors/datto-rmm/production/execution"
EXECUTION_FIELDS = frozenset({"api_url", "api_key", "api_secret"})
EXECUTION_BOOTSTRAP = Path(
    "/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prove the staged Datto RMM execution identity can authenticate while "
            "remaining denied from Global Settings-gated account reads. No Datto "
            "component, job, device, site, alert, UDF, policy, or other provider "
            "resource is modified."
        )
    )
    parser.add_argument("--live-proof", action="store_true")
    return parser


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
        raise RuntimeError("Datto RMM harmless containment read failed.") from error


def assess_probe_results(
    *,
    system_status: int,
    account_status: int,
    devices_status: int,
    components_status: int,
) -> Mapping[str, Any]:
    restricted = {
        "account": account_status,
        "account_devices": devices_status,
        "account_components": components_status,
    }
    restricted_denied = all(status == 403 for status in restricted.values())
    authenticated = system_status == 200
    passed = authenticated and restricted_denied
    return {
        "authenticated": authenticated,
        "system_status_http": system_status,
        "global_settings_account_http": account_status,
        "global_settings_devices_http": devices_status,
        "global_settings_components_http": components_status,
        "global_settings_reads_denied": restricted_denied,
        "provider_mutation_requests": 0,
        "component_execution_attempted": False,
        "runtime_execution_activated": False,
        "device_visibility_proven": False,
        "api_component_level_proven": False,
        "requires_named_scope_examples_for_positive_containment": True,
        "status": "pass" if passed else "fail",
    }


def preflight() -> Mapping[str, Any]:
    return {
        "provider": "datto_rmm",
        "logical_secret": LOGICAL_SECRET,
        "network_contacted": False,
        "provider_credentials_used": False,
        "provider_mutation_requests": 0,
        "component_execution_attempted": False,
        "runtime_execution_activated": False,
        "proof_scope": "authentication_and_negative_global_settings_containment",
        "status": "credential_safe_preflight",
    }


def main() -> int:
    args = build_parser().parse_args()
    if not args.live_proof:
        print(json.dumps(preflight(), indent=2, sort_keys=True))
        return 0

    context = ConnectorContext(
        correlation_id="drmm-execution-identity-harmless-proof",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.execution.identity.probe",
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=EXECUTION_BOOTSTRAP / "role-id",
        secret_id_path=EXECUTION_BOOTSTRAP / "secret-id",
        mappings={LOGICAL_SECRET: EXECUTION_SECRET_PATH},
        allowed_fields={LOGICAL_SECRET: EXECUTION_FIELDS},
    )
    credentials = resolver.resolve(LOGICAL_SECRET, context)
    require_durable_credentials(credentials)

    token = acquire_access_token(credentials=credentials)
    try:
        base = credentials["api_url"].rstrip("/")
        system_status = get_status(
            url=f"{base}/api/v2/system/status",
            token_type=token.token_type,
            access_token=token.access_token,
        )
        account_status = get_status(
            url=f"{base}/api/v2/account/",
            token_type=token.token_type,
            access_token=token.access_token,
        )
        devices_status = get_status(
            url=f"{base}/api/v2/account/devices?max=2&page=1",
            token_type=token.token_type,
            access_token=token.access_token,
        )
        components_status = get_status(
            url=f"{base}/api/v2/account/components?max=2&page=1",
            token_type=token.token_type,
            access_token=token.access_token,
        )
    finally:
        token = None

    result = dict(
        assess_probe_results(
            system_status=system_status,
            account_status=account_status,
            devices_status=devices_status,
            components_status=components_status,
        )
    )
    result.update(
        {
            "provider": "datto_rmm",
            "logical_secret": LOGICAL_SECRET,
            "network_contacted": True,
            "provider_credentials_used": True,
            "access_token_persisted": False,
            "provider_response_bodies_printed": False,
            "provider_response_bodies_persisted": False,
            "proof_scope": "authentication_and_negative_global_settings_containment",
        }
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
