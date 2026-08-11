from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib import error, parse, request


PROVIDERS: dict[str, dict[str, object]] = {
    "aws_ses": {
        "logical_name": "aws_ses.sendmail",
        "secret_path": "secret/data/connectors/aws-ses/production/sendmail",
        "fields": ("access_key_id", "secret_access_key", "session_token"),
        "required_fields": ("access_key_id", "secret_access_key"),
        "policy_name": "jason-aws-ses-sendmail-read",
        "role_name": "jason-aws-ses-sendmail-read",
        "connector_identity": "aws-ses-sendmail",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/aws-ses-sendmail-approle"
        ),
    },
    "datto_rmm": {
        "logical_name": "datto_rmm.readonly",
        "secret_path": "secret/data/connectors/datto-rmm/production/read-only",
        "fields": ("api_url", "api_key", "api_secret"),
        "policy_name": "jason-datto-rmm-read",
        "role_name": "jason-datto-rmm-read",
        "connector_identity": "datto-rmm-read",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle"
        ),
    },
    "it_glue": {
        "logical_name": "it_glue.readonly",
        "secret_path": "secret/data/connectors/it-glue/production/read-only",
        "fields": ("api_key",),
        "policy_name": "jason-itglue-read",
        "role_name": "jason-itglue-read",
        "connector_identity": "itglue-read",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle"
        ),
    },
    "microsoft_graph": {
        "logical_name": "microsoft_graph.directory_read",
        "secret_path": "secret/data/connectors/microsoft-graph/production/directory-read",
        "fields": (
            "private_key_pem",
            "certificate_pem",
            "certificate_thumbprint",
            "generation",
        ),
        "policy_name": "jason-microsoft-graph-directory-read",
        "role_name": "jason-microsoft-graph-directory-read",
        "connector_identity": "microsoft-graph-directory-read",
        "credential_dir": Path(
            "/opt/jason/bootstrap/secrets/openbao/microsoft-graph-directory-read-approle"
        ),
    },
}

DEFAULT_ADDRESS = "http://127.0.0.1:8200"
DEFAULT_ADMIN_USERNAME = "al-admin"


class ProvisionError(RuntimeError):
    """Safe provisioning failure that must never contain secret values."""


def api_request(
    address: str,
    api_path: str,
    *,
    method: str,
    payload: Mapping[str, Any] | None = None,
    token: str | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Vault-Token"] = token
    req = request.Request(
        f"{address.rstrip('/')}/v1/{api_path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ProvisionError("OpenBao rejected the provisioning identity.") from exc
        raise ProvisionError(
            f"OpenBao provisioning request failed with HTTP {exc.code}."
        ) from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ProvisionError("OpenBao is unavailable.") from exc
    if not raw and allow_empty:
        return {}
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProvisionError("OpenBao returned malformed JSON.") from exc
    if not isinstance(parsed, dict):
        raise ProvisionError("OpenBao returned an invalid response.")
    return parsed


def require_string(data: Mapping[str, Any], key: str, description: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ProvisionError(f"OpenBao did not return {description}.")
    return value


def provider_policy_text(provider: str) -> str:
    secret_path = str(PROVIDERS[provider]["secret_path"])
    return (
        f'path "{secret_path}" {{\n'
        '  capabilities = ["read"]\n'
        '}\n\n'
        'path "auth/token/revoke-self" {\n'
        '  capabilities = ["update"]\n'
        '}\n'
    )


def _collect_microsoft_graph_values() -> dict[str, str]:
    key_path = Path(
        input("microsoft_graph private key PEM path: ").strip()
    )
    certificate_path = Path(
        input("microsoft_graph certificate PEM path: ").strip()
    )
    try:
        private_key_pem = key_path.read_text(encoding="utf-8").strip()
        certificate_pem = certificate_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProvisionError("Microsoft certificate source file is unavailable.") from exc
    if "PRIVATE KEY" not in private_key_pem:
        raise ProvisionError("Microsoft private key PEM is invalid.")
    if "BEGIN CERTIFICATE" not in certificate_pem:
        raise ProvisionError("Microsoft certificate PEM is invalid.")
    try:
        der = ssl.PEM_cert_to_DER_cert(certificate_pem)
    except ValueError as exc:
        raise ProvisionError("Microsoft certificate PEM could not be parsed.") from exc
    thumbprint = hashlib.sha1(der).hexdigest().upper()
    return {
        "private_key_pem": private_key_pem,
        "certificate_pem": certificate_pem,
        "certificate_thumbprint": thumbprint,
        "generation": f"sha1:{thumbprint}",
    }


def collect_values(provider: str) -> dict[str, str]:
    if provider == "microsoft_graph":
        return _collect_microsoft_graph_values()
    values: dict[str, str] = {}
    spec = PROVIDERS[provider]
    required_fields = set(spec.get("required_fields", spec["fields"]))
    for field in tuple(spec["fields"]):
        if field.endswith("url"):
            value = input(f"{provider} {field}: ").strip()
        else:
            value = getpass.getpass(f"{provider} {field}: ").strip()
        if not value and field in required_fields:
            raise ProvisionError(f"Required provider field is empty: {field}")
        if value:
            values[field] = value
    return values


def write_private_file(path: Path, value: str) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.write("\n")
    finally:
        os.chmod(path, 0o600)
        os.chown(path, 0, 0)


def admin_login(address: str, username: str, password: str) -> str:
    encoded_username = parse.quote(username, safe="")
    response = api_request(
        address,
        f"auth/userpass/login/{encoded_username}",
        method="POST",
        payload={"password": password},
    )
    auth = response.get("auth")
    if not isinstance(auth, Mapping):
        raise ProvisionError("OpenBao userpass login returned an invalid response.")
    return require_string(auth, "client_token", "an administrative token")


def configure_read_approle(
    *,
    address: str,
    admin_token: str,
    provider: str,
) -> dict[str, object]:
    spec = PROVIDERS[provider]
    policy_name = str(spec["policy_name"])
    role_name = str(spec["role_name"])
    credential_dir = Path(spec["credential_dir"])

    api_request(
        address,
        f"sys/policies/acl/{policy_name}",
        method="POST",
        token=admin_token,
        payload={"policy": provider_policy_text(provider)},
        allow_empty=True,
    )
    api_request(
        address,
        f"auth/approle/role/{role_name}",
        method="POST",
        token=admin_token,
        payload={
            "bind_secret_id": True,
            "secret_id_ttl": "2160h",
            "secret_id_num_uses": 0,
            "token_policies": [policy_name],
            "token_no_default_policy": True,
            "token_ttl": "5m",
            "token_max_ttl": "5m",
            "token_explicit_max_ttl": "5m",
            "token_num_uses": 2,
            "token_type": "service",
        },
        allow_empty=True,
    )

    if credential_dir.exists():
        role_id_path = credential_dir / "role-id"
        secret_id_path = credential_dir / "secret-id"
        if not role_id_path.is_file() or not secret_id_path.is_file():
            raise ProvisionError(
                "Existing AppRole credential directory is incomplete; use governed rotation."
            )
        return {
            "credential_dir": str(credential_dir),
            "credentials_created": False,
        }

    role_response = api_request(
        address,
        f"auth/approle/role/{role_name}/role-id",
        method="GET",
        token=admin_token,
    )
    role_id = require_string(
        role_response.get("data") or {},
        "role_id",
        "the AppRole RoleID",
    )
    secret_response = api_request(
        address,
        f"auth/approle/role/{role_name}/secret-id",
        method="POST",
        token=admin_token,
        payload={
            "metadata": json.dumps(
                {
                    "connector": str(spec["connector_identity"]),
                    "environment": "production",
                }
            ),
            "ttl": "2160h",
            "num_uses": 0,
        },
    )
    secret_data = secret_response.get("data") or {}
    secret_id = require_string(secret_data, "secret_id", "the AppRole SecretID")
    accessor = require_string(
        secret_data,
        "secret_id_accessor",
        "the SecretID accessor",
    )

    credential_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chown(credential_dir, 0, 0)
    os.chmod(credential_dir, 0o700)
    write_private_file(credential_dir / "role-id", role_id)
    write_private_file(credential_dir / "secret-id", secret_id)

    now = datetime.now(timezone.utc)
    metadata = {
        "created_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(days=90)).isoformat(),
        "policy": policy_name,
        "role_name": role_name,
        "connector_identity": str(spec["connector_identity"]),
        "environment": "production",
        "rotation_required": True,
        "secret_id_accessor": accessor,
        "secret_id_ttl_seconds": 7776000,
        "service_token_ttl_seconds": 300,
        "service_token_explicit_max_ttl_seconds": 300,
        "service_token_num_uses": 2,
    }
    write_private_file(
        credential_dir / "credential-metadata.json",
        json.dumps(metadata, indent=2, sort_keys=True),
    )
    return {
        "credential_dir": str(credential_dir),
        "credentials_created": True,
    }


def write_provider_secret(
    *,
    address: str,
    admin_token: str,
    provider: str,
    values: Mapping[str, str],
) -> None:
    spec = PROVIDERS[provider]
    expected = tuple(spec["fields"])
    required = tuple(spec.get("required_fields", expected))
    missing = [field for field in required if not values.get(field)]
    unexpected = sorted(set(values) - set(expected))
    if missing:
        raise ProvisionError("Missing provider fields: " + ", ".join(missing))
    if unexpected:
        raise ProvisionError("Unexpected provider fields: " + ", ".join(unexpected))
    api_request(
        address,
        str(spec["secret_path"]),
        method="POST",
        token=admin_token,
        payload={"data": {field: values[field] for field in expected if field in values}},
        allow_empty=True,
    )


def revoke_admin_token(address: str, admin_token: str) -> None:
    api_request(
        address,
        "auth/token/revoke-self",
        method="POST",
        token=admin_token,
        payload={},
        allow_empty=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Provision a provider secret and provider-specific read-only OpenBao AppRole "
            "without printing credential values."
        )
    )
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--admin-username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = PROVIDERS[args.provider]
    if args.check_only:
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "logical_name": spec["logical_name"],
                    "secret_path": spec["secret_path"],
                    "fields": list(spec["fields"]),
                    "required_fields": list(spec.get("required_fields", spec["fields"])),
                    "policy_name": spec["policy_name"],
                    "role_name": spec["role_name"],
                    "credential_dir": str(spec["credential_dir"]),
                    "runtime_authentication": "approle",
                    "runtime_token_persisted": False,
                    "network_contacted": False,
                    "secret_entered": False,
                    "status": "pass",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if os.geteuid() != 0:
        raise SystemExit("DENIED: provisioning must run as root")

    admin_password = getpass.getpass(
        f"OpenBao password for {args.admin_username}: "
    )
    admin_token: str | None = None
    values: dict[str, str] = {}
    try:
        admin_token = admin_login(args.address, args.admin_username, admin_password)
        admin_password = ""
        identity = configure_read_approle(
            address=args.address,
            admin_token=admin_token,
            provider=args.provider,
        )
        values = collect_values(args.provider)
        write_provider_secret(
            address=args.address,
            admin_token=admin_token,
            provider=args.provider,
            values=values,
        )
        values.clear()
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "logical_name": spec["logical_name"],
                    "secret_path": spec["secret_path"],
                    "credential_dir": identity["credential_dir"],
                    "approle_credentials_created": identity["credentials_created"],
                    "runtime_authentication": "approle",
                    "runtime_token_persisted": False,
                    "secret_values_printed": False,
                    "provider_contacted": False,
                    "status": "pass",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    finally:
        admin_password = ""
        values.clear()
        if admin_token:
            try:
                revoke_admin_token(args.address, admin_token)
                print("[PASS] Temporary administrative token revoked.")
            except ProvisionError:
                print(
                    "[WARN] Temporary administrative token could not be revoked explicitly.",
                    file=os.sys.stderr,
                )
