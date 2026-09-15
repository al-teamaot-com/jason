#!/usr/bin/env python3

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


class RecoveryError(RuntimeError):
    """Safe recovery failure without exposing credential values."""


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
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RecoveryError(
            f"OpenBao request failed at {path}: HTTP {error.code}."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RecoveryError(f"OpenBao request failed at {path}.") from error
    if not raw and allow_empty:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryError(f"OpenBao returned invalid JSON at {path}.") from error
    if not isinstance(parsed, Mapping):
        raise RecoveryError(f"OpenBao returned an invalid response at {path}.")
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
        raise RecoveryError(f"OpenBao request failed at {path}.") from error


def require_string(data: Mapping[str, Any], key: str, description: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RecoveryError(f"OpenBao did not return {description}.")
    return value


def require_kv2_data(response: Mapping[str, Any], description: str) -> Mapping[str, Any]:
    outer = response.get("data")
    if not isinstance(outer, Mapping):
        raise RecoveryError(f"OpenBao returned an invalid {description} record.")
    values = outer.get("data")
    if not isinstance(values, Mapping):
        raise RecoveryError(f"OpenBao returned an invalid {description} payload.")
    return values


def kv2_version(response: Mapping[str, Any], description: str) -> int:
    outer = response.get("data")
    if not isinstance(outer, Mapping):
        raise RecoveryError(f"OpenBao returned invalid {description} metadata.")
    metadata = outer.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RecoveryError(f"OpenBao returned invalid {description} metadata.")
    version = metadata.get("version")
    if not isinstance(version, int) or version < 1:
        raise RecoveryError(f"OpenBao returned invalid {description} version metadata.")
    return version


def write_private_file(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.write("\n")
    finally:
        os.chmod(path, 0o600)
        os.chown(path, 0, 0)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recover the approved Datto RMM execution credential staging after "
            "the initial CAS-required KV write failed."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--admin-username", default="al-admin")
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("deploy/openbao/config/jason-datto-rmm-execution-policy.hcl"),
    )
    parser.add_argument(
        "--credential-dir",
        type=Path,
        default=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle"
        ),
    )
    return parser.parse_args()


def normalize_policy(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


def extract_existing_policy_text(response: Mapping[str, Any]) -> str:
    """Return the policy text from supported OpenBao ACL-policy response shapes.

    OpenBao's ACL policy read endpoint returns the policy document in the top-level
    ``policy`` field.  A nested ``data.rules`` form is accepted only as a
    compatibility fallback.  If both forms are present they must agree exactly
    after normalization, otherwise recovery fails closed.
    """

    candidates: list[str] = []

    policy = response.get("policy")
    if isinstance(policy, str) and policy:
        candidates.append(policy)

    data = response.get("data")
    if isinstance(data, Mapping):
        rules = data.get("rules")
        if isinstance(rules, str) and rules:
            candidates.append(rules)

    if not candidates:
        raise RecoveryError("Existing Datto execution policy rules were unavailable.")

    normalized = {normalize_policy(value) for value in candidates}
    if len(normalized) != 1:
        raise RecoveryError("Existing Datto execution policy response was inconsistent.")

    return candidates[0]


def require_existing_policy_matches(
    *, base_url: str, token: str, policy_name: str, policy_text: str
) -> None:
    response = request_json(
        base_url=base_url,
        path=f"sys/policies/acl/{policy_name}",
        method="GET",
        token=token,
    )
    existing_policy = extract_existing_policy_text(response)
    if normalize_policy(existing_policy) != normalize_policy(policy_text):
        raise RecoveryError(
            "Existing Datto execution policy does not match the approved source; refusing recovery."
        )


def require_existing_approle_matches(
    *, base_url: str, token: str, role_name: str, policy_name: str
) -> None:
    response = request_json(
        base_url=base_url,
        path=f"auth/approle/role/{role_name}",
        method="GET",
        token=token,
    )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise RecoveryError("Existing Datto execution AppRole response was invalid.")
    exact = {
        "bind_secret_id": True,
        "secret_id_ttl": 7776000,
        "secret_id_num_uses": 0,
        "token_no_default_policy": True,
        "token_ttl": 300,
        "token_max_ttl": 300,
        "token_explicit_max_ttl": 300,
        "token_num_uses": 2,
    }
    for key, expected in exact.items():
        if data.get(key) != expected:
            raise RecoveryError(
                f"Existing Datto execution AppRole field {key} does not match approved source."
            )
    policies = data.get("token_policies")
    if policies != [policy_name]:
        raise RecoveryError(
            "Existing Datto execution AppRole policy binding does not match approved source."
        )
    token_type = data.get("token_type")
    if token_type not in ("service", "default-service"):
        raise RecoveryError(
            "Existing Datto execution AppRole token type does not match approved source."
        )


def main() -> int:
    arguments = parse_arguments()
    if os.geteuid() != 0:
        raise RecoveryError("This recovery utility must run as root.")
    if arguments.credential_dir.exists():
        raise RecoveryError(
            "The Datto execution bootstrap directory already exists; refusing recovery overwrite."
        )
    try:
        policy_text = arguments.policy_file.read_text(encoding="utf-8")
    except OSError as error:
        raise RecoveryError("The approved Datto execution policy file is unavailable.") from error

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
        raise RecoveryError("OpenBao userpass login returned an invalid response.") from error

    policy_name = "jason-datto-rmm-execution"
    role_name = "jason-datto-rmm-execution"
    readonly_path = "secret/data/connectors/datto-rmm/production/read-only"
    execution_path = "secret/data/connectors/datto-rmm/production/execution"
    temp_dir = arguments.credential_dir.parent / (
        f".{arguments.credential_dir.name}.staging-{os.getpid()}"
    )
    test_token: str | None = None

    try:
        config = request_json(
            base_url=arguments.base_url,
            path="secret/config",
            method="GET",
            token=admin_token,
        )
        config_data = config.get("data")
        if not isinstance(config_data, Mapping) or config_data.get("cas_required") is not True:
            raise RecoveryError(
                "OpenBao secret/ KV engine is not in the CAS-required state proven by the incident diagnostic."
            )

        require_existing_policy_matches(
            base_url=arguments.base_url,
            token=admin_token,
            policy_name=policy_name,
            policy_text=policy_text,
        )
        require_existing_approle_matches(
            base_url=arguments.base_url,
            token=admin_token,
            role_name=role_name,
            policy_name=policy_name,
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

        execution_status = request_status(
            base_url=arguments.base_url,
            path=execution_path,
            method="GET",
            token=admin_token,
        )
        if execution_status not in (200, 404):
            raise RecoveryError(
                "Datto execution secret state could not be proven safely."
            )

        api_key = getpass.getpass("New Datto RMM execution API key: ")
        api_secret = getpass.getpass("New Datto RMM execution API secret: ")
        if not api_key or not api_secret:
            raise RecoveryError("Datto RMM execution API credentials may not be empty.")
        if api_key == readonly_values.get("api_key"):
            raise RecoveryError(
                "The execution API key matches the read-only identity; identity separation failed."
            )
        if api_secret == readonly_values.get("api_secret"):
            raise RecoveryError(
                "The execution API secret matches the read-only identity; identity separation failed."
            )

        if execution_status == 404:
            request_json(
                base_url=arguments.base_url,
                path=execution_path,
                method="POST",
                token=admin_token,
                payload={
                    "options": {"cas": 0},
                    "data": {
                        "api_url": api_url,
                        "api_key": api_key,
                        "api_secret": api_secret,
                    },
                },
            )

        execution_record = request_json(
            base_url=arguments.base_url,
            path=execution_path,
            method="GET",
            token=admin_token,
        )
        execution_values = require_kv2_data(execution_record, "Datto RMM execution")
        if execution_values.get("api_url") != api_url:
            raise RecoveryError("Datto RMM execution API URL verification failed.")
        if execution_values.get("api_key") != api_key:
            raise RecoveryError("Datto RMM execution API key verification failed.")
        if execution_values.get("api_secret") != api_secret:
            raise RecoveryError("Datto RMM execution API secret verification failed.")
        if kv2_version(execution_record, "Datto RMM execution") != 1:
            raise RecoveryError(
                "Datto RMM execution secret is not an isolated version-1 record."
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
                    {"connector": "datto-rmm-execution", "environment": "production"}
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
            raise RecoveryError(
                "Datto RMM execution AppRole login returned an invalid response."
            ) from error

        role_read = request_json(
            base_url=arguments.base_url,
            path=execution_path,
            method="GET",
            token=test_token,
        )
        role_values = require_kv2_data(role_read, "Datto RMM execution AppRole")
        if set(role_values) != {"api_url", "api_key", "api_secret"}:
            raise RecoveryError(
                "Datto RMM execution AppRole returned an unexpected secret shape."
            )
        readonly_status = request_status(
            base_url=arguments.base_url,
            path=readonly_path,
            method="GET",
            token=test_token,
        )
        if readonly_status != 403:
            raise RecoveryError(
                "Datto RMM execution AppRole was not denied access to the read-only secret."
            )

        readonly_after = request_json(
            base_url=arguments.base_url,
            path=readonly_path,
            method="GET",
            token=admin_token,
        )
        if kv2_version(readonly_after, "Datto RMM read-only") != readonly_version_before:
            raise RecoveryError("Datto RMM read-only secret version changed unexpectedly.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=90)
        temp_dir.mkdir(parents=False, exist_ok=False, mode=0o700)
        os.chown(temp_dir, 0, 0)
        os.chmod(temp_dir, 0o700)
        write_private_file(temp_dir / "role-id", role_id)
        write_private_file(temp_dir / "secret-id", secret_id)
        metadata = {
            "created_at_utc": now.isoformat(),
            "expires_at_utc": expires_at.isoformat(),
            "policy": policy_name,
            "role_name": role_name,
            "connector_identity": "datto-rmm-execution",
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
            "recovered_from_cas_required_partial_stage": True,
        }
        write_private_file(
            temp_dir / "credential-metadata.json",
            json.dumps(metadata, indent=2, sort_keys=True),
        )
        os.rename(temp_dir, arguments.credential_dir)

        api_key = ""
        api_secret = ""
        print("Existing Datto execution policy verified against approved source.")
        print("Existing Datto execution AppRole verified against approved source.")
        print("CAS-required execution secret staging completed safely.")
        print("Datto execution AppRole isolation verified.")
        print("Protected bootstrap AppRole credentials created atomically.")
        print("Existing Datto RMM read-only secret remained unchanged.")
        print("Runtime activation: NO")
        print("Provider write activation: NO")
        print("Provider contacted: NO")
        print("No credential, token, host secret path, or provider secret value was displayed.")
    finally:
        if test_token:
            try:
                request_json(
                    base_url=arguments.base_url,
                    path="auth/token/revoke-self",
                    method="POST",
                    token=test_token,
                    payload={},
                    allow_empty=True,
                )
            except RecoveryError:
                pass
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
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
            except RecoveryError:
                print(
                    "WARNING: Temporary administrative token could not be revoked explicitly.",
                    file=sys.stderr,
                )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
