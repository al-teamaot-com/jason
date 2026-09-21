#!/usr/bin/env python3

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


class ProvisioningError(RuntimeError):
    """Safe provisioning failure without secret values."""


def request_json(
    *,
    base_url: str,
    path: str,
    method: str,
    payload: Mapping[str, Any] | None = None,
    token: str | None = None,
    allow_empty: bool = False,
    timeout_seconds: float = 15.0,
) -> Mapping[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Vault-Token"] = token
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/v1/{path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read()
    except urllib.error.HTTPError as error:
        raise ProvisioningError(
            f"OpenBao request failed at {path}: HTTP {error.code}."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ProvisioningError(f"OpenBao request failed at {path}.") from error

    if not response_body and allow_empty:
        return {}
    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvisioningError(f"OpenBao returned invalid JSON at {path}.") from error
    if not isinstance(parsed, Mapping):
        raise ProvisioningError(f"OpenBao returned an invalid response at {path}.")
    return parsed


def request_status(
    *,
    base_url: str,
    path: str,
    method: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = 15.0,
) -> int:
    headers = {"Accept": "application/json", "X-Vault-Token": token}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/v1/{path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read()
            return int(response.status)
    except urllib.error.HTTPError as error:
        error.read()
        return int(error.code)
    except (urllib.error.URLError, TimeoutError) as error:
        raise ProvisioningError(f"OpenBao request failed at {path}.") from error


def require_string(data: Mapping[str, Any], key: str, description: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ProvisioningError(f"OpenBao did not return {description}.")
    return value


def require_kv2_data(response: Mapping[str, Any], description: str) -> Mapping[str, Any]:
    outer = response.get("data")
    if not isinstance(outer, Mapping):
        raise ProvisioningError(f"OpenBao returned an invalid {description} record.")
    values = outer.get("data")
    if not isinstance(values, Mapping):
        raise ProvisioningError(f"OpenBao returned an invalid {description} payload.")
    return values


def kv2_version(response: Mapping[str, Any], description: str) -> int:
    outer = response.get("data")
    if not isinstance(outer, Mapping):
        raise ProvisioningError(f"OpenBao returned invalid {description} metadata.")
    metadata = outer.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ProvisioningError(f"OpenBao returned invalid {description} metadata.")
    version = metadata.get("version")
    if not isinstance(version, int) or version < 1:
        raise ProvisioningError(f"OpenBao returned invalid {description} version metadata.")
    return version


def write_private_file(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(value)
            file.write("\n")
    finally:
        os.chmod(path, 0o600)
        os.chown(path, 0, 0)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Provision the separate Jason Datto RMM site-variable OpenBao secret, "
            "least-privilege policy, AppRole, and bootstrap credentials."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--admin-username", default="al-admin")
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("deploy/openbao/config/jason-datto-rmm-site-variables-policy.hcl"),
    )
    parser.add_argument(
        "--credential-dir",
        type=Path,
        default=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-site-variables-approle"
        ),
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if os.geteuid() != 0:
        raise ProvisioningError("This provisioning utility must run as root.")
    if arguments.credential_dir.exists():
        raise ProvisioningError(
            "The Datto RMM site-variable credential directory already exists. "
            "Use the governed rotation process instead of overwriting it."
        )

    try:
        policy_text = arguments.policy_file.read_text(encoding="utf-8")
    except OSError as error:
        raise ProvisioningError("The Datto RMM site-variable policy file is unavailable.") from error

    admin_password = getpass.getpass(
        f"OpenBao password for {arguments.admin_username}: "
    )
    encoded_username = urllib.parse.quote(arguments.admin_username, safe="")
    login = request_json(
        base_url=arguments.base_url,
        path=f"auth/userpass/login/{encoded_username}",
        method="POST",
        payload={"password": admin_password},
    )
    admin_password = ""

    try:
        auth = login["auth"]
        admin_token = require_string(auth, "client_token", "an administrative token")
    except (KeyError, TypeError) as error:
        raise ProvisioningError(
            "OpenBao userpass login returned an invalid response."
        ) from error

    policy_name = "jason-datto-rmm-site-variables"
    role_name = "jason-datto-rmm-site-variables"
    readonly_path = "secret/data/connectors/datto-rmm/production/read-only"
    site_variable_path = "secret/data/connectors/datto-rmm/production/site-variables"

    try:
        if request_status(
            base_url=arguments.base_url,
            path=f"sys/policies/acl/{policy_name}",
            method="GET",
            token=admin_token,
        ) != 404:
            raise ProvisioningError(
                "The Datto RMM site-variable policy already exists; refusing to overwrite it."
            )
        if request_status(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}",
            method="GET",
            token=admin_token,
        ) != 404:
            raise ProvisioningError(
                "The Datto RMM site-variable AppRole already exists; refusing to overwrite it."
            )
        if request_status(
            base_url=arguments.base_url,
            path=site_variable_path,
            method="GET",
            token=admin_token,
        ) != 404:
            raise ProvisioningError(
                "The Datto RMM site-variable secret already exists; refusing to overwrite it."
            )

        readonly_before = request_json(
            base_url=arguments.base_url,
            path=readonly_path,
            method="GET",
            token=admin_token,
        )
        readonly_values = require_kv2_data(readonly_before, "Datto RMM read-only")
        readonly_version_before = kv2_version(readonly_before, "Datto RMM read-only")
        api_url = require_string(readonly_values, "api_url", "the Datto RMM API URL")

        api_key = getpass.getpass("New Datto RMM site-variable API key: ")
        api_secret = getpass.getpass("New Datto RMM site-variable API secret: ")
        if not api_key or not api_secret:
            raise ProvisioningError("Datto RMM site-variable API credentials may not be empty.")
        if api_key == readonly_values.get("api_key"):
            raise ProvisioningError(
                "The site-variable API key matches the read-only identity; identity separation failed."
            )
        if api_secret == readonly_values.get("api_secret"):
            raise ProvisioningError(
                "The site-variable API secret matches the read-only identity; identity separation failed."
            )

        request_json(
            base_url=arguments.base_url,
            path=f"sys/policies/acl/{policy_name}",
            method="POST",
            token=admin_token,
            payload={"policy": policy_text},
            allow_empty=True,
        )
        request_json(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}",
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
        request_json(
            base_url=arguments.base_url,
            path=site_variable_path,
            method="POST",
            token=admin_token,
            payload={
                "data": {
                    "api_url": api_url,
                    "api_key": api_key,
                    "api_secret": api_secret,
                }
            },
        )

        execution_record = request_json(
            base_url=arguments.base_url,
            path=site_variable_path,
            method="GET",
            token=admin_token,
        )
        site_variable_values = require_kv2_data(execution_record, "Datto RMM site-variable")
        if site_variable_values.get("api_url") != api_url:
            raise ProvisioningError("Datto RMM site-variable API URL verification failed.")
        if site_variable_values.get("api_key") != api_key:
            raise ProvisioningError("Datto RMM site-variable API key verification failed.")
        if site_variable_values.get("api_secret") != api_secret:
            raise ProvisioningError("Datto RMM site-variable API secret verification failed.")
        site_variable_version = kv2_version(execution_record, "Datto RMM site-variable")
        if site_variable_version != 1:
            raise ProvisioningError(
                "Datto RMM site-variable secret was not created as a new isolated record."
            )

        role_response = request_json(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}/role-id",
            method="GET",
            token=admin_token,
        )
        role_id = require_string(
            role_response.get("data") or {}, "role_id", "the AppRole RoleID"
        )
        secret_response = request_json(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}/secret-id",
            method="POST",
            token=admin_token,
            payload={
                "metadata": json.dumps(
                    {"connector": "datto-rmm-site-variables", "environment": "production"}
                ),
                "ttl": "2160h",
                "num_uses": 0,
            },
        )
        secret_data = secret_response.get("data") or {}
        secret_id = require_string(secret_data, "secret_id", "the AppRole SecretID")
        secret_id_accessor = require_string(
            secret_data, "secret_id_accessor", "the SecretID accessor"
        )

        approle_login = request_json(
            base_url=arguments.base_url,
            path="auth/approle/login",
            method="POST",
            payload={"role_id": role_id, "secret_id": secret_id},
        )
        try:
            test_auth = approle_login["auth"]
            test_token = require_string(
                test_auth, "client_token", "an execution AppRole test token"
            )
        except (KeyError, TypeError) as error:
            raise ProvisioningError(
                "Datto RMM site-variable AppRole login returned an invalid response."
            ) from error

        try:
            role_read = request_json(
                base_url=arguments.base_url,
                path=site_variable_path,
                method="GET",
                token=test_token,
            )
            role_values = require_kv2_data(role_read, "Datto RMM site-variable AppRole")
            if set(role_values) != {"api_url", "api_key", "api_secret"}:
                raise ProvisioningError(
                    "Datto RMM site-variable AppRole returned an unexpected secret shape."
                )
            readonly_status = request_status(
                base_url=arguments.base_url,
                path=readonly_path,
                method="GET",
                token=test_token,
            )
            if readonly_status != 403:
                raise ProvisioningError(
                    "Datto RMM site-variable AppRole was not denied access to the read-only secret."
                )
        finally:
            try:
                request_json(
                    base_url=arguments.base_url,
                    path="auth/token/revoke-self",
                    method="POST",
                    token=test_token,
                    payload={},
                    allow_empty=True,
                )
            except ProvisioningError:
                pass

        readonly_after = request_json(
            base_url=arguments.base_url,
            path=readonly_path,
            method="GET",
            token=admin_token,
        )
        if kv2_version(readonly_after, "Datto RMM read-only") != readonly_version_before:
            raise ProvisioningError("Datto RMM read-only secret version changed unexpectedly.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=90)
        arguments.credential_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chown(arguments.credential_dir, 0, 0)
        os.chmod(arguments.credential_dir, 0o700)
        write_private_file(arguments.credential_dir / "role-id", role_id)
        write_private_file(arguments.credential_dir / "secret-id", secret_id)
        metadata = {
            "created_at_utc": now.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "policy": policy_name,
            "role_name": role_name,
            "connector_identity": "datto-rmm-site-variables",
            "environment": "production",
            "logical_secret": "datto_rmm.execution",
            "rotation_required": True,
            "secret_id_accessor": secret_id_accessor,
            "secret_id_ttl_seconds": 7776000,
            "service_token_ttl_seconds": 300,
            "service_token_explicit_max_ttl_seconds": 300,
            "service_token_num_uses": 2,
            "runtime_activation": False,
            "provider_write_activation": False,
        }
        write_private_file(
            arguments.credential_dir / "credential-metadata.json",
            json.dumps(metadata, indent=2, sort_keys=True),
        )

        api_key = ""
        api_secret = ""
        print("Datto RMM site-variable secret created as a separate record.")
        print("Datto RMM site-variable least-privilege OpenBao policy installed.")
        print("Datto RMM site-variable AppRole configured and isolation verified.")
        print("Protected bootstrap AppRole credentials created.")
        print("Existing Datto RMM read-only secret remained unchanged.")
        print("Runtime activation: NO")
        print("Provider write activation: NO")
        print("Provider contacted: NO")
        print("No credential, token, host secret path, or provider secret value was displayed.")
    finally:
        if "admin_token" in locals():
            try:
                request_json(
                    base_url=arguments.base_url,
                    path="auth/token/revoke-self",
                    method="POST",
                    token=admin_token,
                    payload={},
                    allow_empty=True,
                )
                print("Temporary administrative token revoked.")
            except ProvisioningError:
                print(
                    "WARNING: Temporary administrative token could not be revoked explicitly.",
                    file=sys.stderr,
                )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
