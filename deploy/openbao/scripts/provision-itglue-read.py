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
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            response_body = response.read()
    except urllib.error.HTTPError as error:
        safe_detail = f"HTTP {error.code}"
        raise ProvisioningError(
            f"OpenBao request failed at {path}: {safe_detail}."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ProvisioningError(
            f"OpenBao request failed at {path}."
        ) from error

    if not response_body and allow_empty:
        return {}

    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvisioningError(
            f"OpenBao returned invalid JSON at {path}."
        ) from error

    if not isinstance(parsed, Mapping):
        raise ProvisioningError(
            f"OpenBao returned an invalid response at {path}."
        )

    return parsed


def require_string(
    data: Mapping[str, Any],
    key: str,
    description: str,
) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value:
        raise ProvisioningError(
            f"OpenBao did not return {description}."
        )

    return value


def write_private_file(path: Path, value: str) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )

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
            "Provision the Jason IT Glue read-only OpenBao "
            "policy, AppRole, and bootstrap credentials."
        )
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8200",
    )
    parser.add_argument(
        "--admin-username",
        default="al-admin",
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path(
            "deploy/openbao/config/"
            "jason-itglue-read-policy.hcl"
        ),
    )
    parser.add_argument(
        "--credential-dir",
        type=Path,
        default=Path(
            "/opt/jason/bootstrap/secrets/openbao/"
            "itglue-read-approle"
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if os.geteuid() != 0:
        raise ProvisioningError(
            "This provisioning utility must run as root."
        )

    if arguments.credential_dir.exists():
        raise ProvisioningError(
            "The IT Glue read credential directory already exists. "
            "Use the governed rotation process instead of overwriting it."
        )

    try:
        policy_text = arguments.policy_file.read_text(
            encoding="utf-8"
        )
    except OSError as error:
        raise ProvisioningError(
            "The IT Glue read policy file is unavailable."
        ) from error

    password = getpass.getpass(
        f"OpenBao password for {arguments.admin_username}: "
    )

    encoded_username = urllib.parse.quote(
        arguments.admin_username,
        safe="",
    )

    login = request_json(
        base_url=arguments.base_url,
        path=f"auth/userpass/login/{encoded_username}",
        method="POST",
        payload={"password": password},
    )
    password = ""

    try:
        auth = login["auth"]
        admin_token = require_string(
            auth,
            "client_token",
            "an administrative token",
        )
    except (KeyError, TypeError) as error:
        raise ProvisioningError(
            "OpenBao userpass login returned an invalid response."
        ) from error

    policy_name = "jason-itglue-read"
    role_name = "jason-itglue-read"

    try:
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

        role_response = request_json(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}/role-id",
            method="GET",
            token=admin_token,
        )
        role_id = require_string(
            role_response.get("data") or {},
            "role_id",
            "the AppRole RoleID",
        )

        secret_response = request_json(
            base_url=arguments.base_url,
            path=f"auth/approle/role/{role_name}/secret-id",
            method="POST",
            token=admin_token,
            payload={
                "metadata": json.dumps(
                    {
                        "connector": "itglue-read",
                        "environment": "production",
                    }
                ),
                "ttl": "2160h",
                "num_uses": 0,
            },
        )

        secret_data = secret_response.get("data") or {}
        secret_id = require_string(
            secret_data,
            "secret_id",
            "the AppRole SecretID",
        )
        secret_id_accessor = require_string(
            secret_data,
            "secret_id_accessor",
            "the SecretID accessor",
        )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=90)

        arguments.credential_dir.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )
        os.chown(arguments.credential_dir, 0, 0)
        os.chmod(arguments.credential_dir, 0o700)

        write_private_file(
            arguments.credential_dir / "role-id",
            role_id,
        )
        write_private_file(
            arguments.credential_dir / "secret-id",
            secret_id,
        )

        metadata = {
            "created_at_utc": now.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "policy": policy_name,
            "role_name": role_name,
            "connector_identity": "itglue-read",
            "environment": "production",
            "rotation_required": True,
            "secret_id_accessor": secret_id_accessor,
            "secret_id_ttl_seconds": 7776000,
            "service_token_ttl_seconds": 300,
            "service_token_explicit_max_ttl_seconds": 300,
            "service_token_num_uses": 2,
        }

        write_private_file(
            arguments.credential_dir
            / "credential-metadata.json",
            json.dumps(metadata, indent=2, sort_keys=True),
        )

        print("IT Glue read-only policy installed.")
        print("IT Glue read-only AppRole configured.")
        print("Bootstrap credential files created.")
        print(
            f"Credential directory: "
            f"{arguments.credential_dir}"
        )
        print("No credential or token value was displayed.")

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
                    "WARNING: Temporary administrative token "
                    "could not be revoked explicitly.",
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
