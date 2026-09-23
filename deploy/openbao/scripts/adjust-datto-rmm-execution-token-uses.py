#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping


ROLE_NAME = "jason-datto-rmm-execution"
POLICY_NAME = "jason-datto-rmm-execution"
APPROVED_TOKEN_USES = 2
TRANSIENT_TOKEN_USES = 3
EXECUTION_PATH = "secret/data/connectors/datto-rmm/production/execution"

LEGACY_POLICY = '''
path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}
'''

APPROVED_POLICY = '''
path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}

path "auth/token/revoke-self" {
  capabilities = ["update"]
}
'''


class AdjustmentError(RuntimeError):
    """Safe adjustment failure that must not expose credentials or tokens."""


def request_json(
    *,
    base_url: str,
    path: str,
    method: str,
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    allow_empty: bool = False,
    timeout_seconds: float = 15.0,
) -> Mapping[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["X-Vault-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/{path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            if not raw and allow_empty:
                return {}
            if not raw:
                raise AdjustmentError(f"OpenBao returned an empty response at {path}.")
            parsed = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        error.read()
        raise AdjustmentError(
            f"OpenBao request failed at {path}: HTTP {int(error.code)}."
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise AdjustmentError(f"OpenBao request failed at {path}.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdjustmentError(f"OpenBao returned invalid JSON at {path}.") from error

    if not isinstance(parsed, Mapping):
        raise AdjustmentError(f"OpenBao returned an invalid response at {path}.")
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
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/{path.lstrip('/')}",
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
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise AdjustmentError(f"OpenBao request failed at {path}.") from error


def normalize_policy(value: str) -> str:
    lines: list[str] = []
    for raw_line in value.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_policy_text(response: Mapping[str, Any]) -> str:
    candidates: list[str] = []

    policy = response.get("policy")
    if isinstance(policy, str) and policy:
        candidates.append(policy)

    data = response.get("data")
    if isinstance(data, Mapping):
        for key in ("policy", "rules"):
            value = data.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

    if not candidates:
        raise AdjustmentError("Execution AppRole policy text was unavailable.")

    normalized = {normalize_policy(value) for value in candidates}
    if len(normalized) != 1:
        raise AdjustmentError("Execution AppRole policy response was inconsistent.")

    return candidates[0]


def validate_policy_transition(policy_text: str) -> str:
    normalized = normalize_policy(policy_text)
    legacy = normalize_policy(LEGACY_POLICY)
    approved = normalize_policy(APPROVED_POLICY)
    if normalized == legacy:
        return "legacy_missing_self_revoke"
    if normalized == approved:
        return "approved"
    raise AdjustmentError(
        "Execution AppRole policy drifted outside the approved self-revocation repair boundary."
    )


def desired_role_payload(*, token_num_uses: int = APPROVED_TOKEN_USES) -> Mapping[str, Any]:
    return {
        "bind_secret_id": True,
        "secret_id_ttl": "2160h",
        "secret_id_num_uses": 0,
        "token_policies": [POLICY_NAME],
        "token_no_default_policy": True,
        "token_ttl": "5m",
        "token_max_ttl": "5m",
        "token_explicit_max_ttl": "5m",
        "token_num_uses": token_num_uses,
        "token_type": "service",
    }


def validate_role_data(data: Mapping[str, Any], *, allowed_token_uses: set[int]) -> int:
    exact = {
        "bind_secret_id": True,
        "secret_id_ttl": 7776000,
        "secret_id_num_uses": 0,
        "token_no_default_policy": True,
        "token_ttl": 300,
        "token_max_ttl": 300,
        "token_explicit_max_ttl": 300,
    }
    for key, expected in exact.items():
        if data.get(key) != expected:
            raise AdjustmentError(
                f"Execution AppRole field {key} does not match the approved containment contract."
            )

    if data.get("token_policies") != [POLICY_NAME]:
        raise AdjustmentError("Execution AppRole policy binding drifted from approved source.")

    if data.get("token_type") not in ("service", "default-service"):
        raise AdjustmentError("Execution AppRole token type drifted from approved source.")

    uses = data.get("token_num_uses")
    if not isinstance(uses, int) or uses not in allowed_token_uses:
        raise AdjustmentError("Execution AppRole token use budget is outside the approved transition.")
    return uses


def require_string(mapping: Mapping[str, Any], key: str, description: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise AdjustmentError(f"OpenBao did not return {description}.")
    return value


def read_role(*, base_url: str, admin_token: str) -> Mapping[str, Any]:
    response = request_json(
        base_url=base_url,
        path=f"auth/approle/role/{ROLE_NAME}",
        method="GET",
        token=admin_token,
    )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise AdjustmentError("Execution AppRole read returned an invalid response.")
    return data


def read_policy(*, base_url: str, admin_token: str) -> str:
    response = request_json(
        base_url=base_url,
        path=f"sys/policies/acl/{POLICY_NAME}",
        method="GET",
        token=admin_token,
    )
    return extract_policy_text(response)


def update_metadata(path: Path) -> None:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdjustmentError("Execution bootstrap metadata is unavailable or invalid.") from error
    if not isinstance(metadata, dict):
        raise AdjustmentError("Execution bootstrap metadata has an invalid shape.")

    current = metadata.get("service_token_num_uses")
    if current not in (APPROVED_TOKEN_USES, TRANSIENT_TOKEN_USES):
        raise AdjustmentError("Execution bootstrap metadata token use budget is unexpected.")

    metadata["service_token_num_uses"] = APPROVED_TOKEN_USES
    metadata.pop("token_use_budget_adjustment", None)
    metadata["self_revoke_policy_repair"] = (
        "execution policy explicitly grants update on auth/token/revoke-self; "
        "two token uses cover one KV read and explicit self-revocation"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".credential-metadata.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.chown(tmp_name, 0, 0)
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair the staged Datto execution AppRole so its no-default-policy token can "
            "explicitly revoke itself after one execution-secret read, while restoring the "
            "approved two-use token budget. This does not contact Datto or activate runtime execution."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8200")
    parser.add_argument("--admin-username", default="al-admin")
    parser.add_argument(
        "--credential-dir",
        type=Path,
        default=Path("/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle"),
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("deploy/openbao/config/jason-datto-rmm-execution-policy.hcl"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    if os.geteuid() != 0:
        raise AdjustmentError("This adjustment utility must run as root.")

    role_id_path = args.credential_dir / "role-id"
    secret_id_path = args.credential_dir / "secret-id"
    metadata_path = args.credential_dir / "credential-metadata.json"
    for path in (role_id_path, secret_id_path, metadata_path):
        if not path.is_file() or path.stat().st_size <= 0:
            raise AdjustmentError("Execution bootstrap material is incomplete.")

    try:
        approved_policy_text = args.policy_file.read_text(encoding="utf-8")
    except OSError as error:
        raise AdjustmentError("Approved execution policy source is unavailable.") from error
    if normalize_policy(approved_policy_text) != normalize_policy(APPROVED_POLICY):
        raise AdjustmentError("Approved execution policy source does not match the repair contract.")

    password = getpass.getpass(f"OpenBao password for {args.admin_username}: ")
    login = request_json(
        base_url=args.base_url,
        path="auth/userpass/login/" + urllib.parse.quote(args.admin_username, safe=""),
        method="POST",
        payload={"password": password},
    )
    password = ""
    auth = login.get("auth")
    if not isinstance(auth, Mapping):
        raise AdjustmentError("OpenBao administrative login returned an invalid response.")
    admin_token = require_string(auth, "client_token", "an administrative token")

    try:
        before_role = read_role(base_url=args.base_url, admin_token=admin_token)
        before_uses = validate_role_data(
            before_role,
            allowed_token_uses={APPROVED_TOKEN_USES, TRANSIENT_TOKEN_USES},
        )
        before_policy = read_policy(base_url=args.base_url, admin_token=admin_token)
        before_policy_state = validate_policy_transition(before_policy)

        if before_policy_state == "legacy_missing_self_revoke":
            request_json(
                base_url=args.base_url,
                path=f"sys/policies/acl/{POLICY_NAME}",
                method="POST",
                token=admin_token,
                payload={"policy": approved_policy_text},
                allow_empty=True,
            )

        if before_uses == TRANSIENT_TOKEN_USES:
            request_json(
                base_url=args.base_url,
                path=f"auth/approle/role/{ROLE_NAME}",
                method="POST",
                token=admin_token,
                payload=desired_role_payload(),
                allow_empty=True,
            )

        after_policy = read_policy(base_url=args.base_url, admin_token=admin_token)
        if validate_policy_transition(after_policy) != "approved":
            raise AdjustmentError("Execution AppRole self-revocation policy repair did not persist.")

        after_role = read_role(base_url=args.base_url, admin_token=admin_token)
        validate_role_data(after_role, allowed_token_uses={APPROVED_TOKEN_USES})

        role_id = role_id_path.read_text(encoding="utf-8").strip()
        secret_id = secret_id_path.read_text(encoding="utf-8").strip()
        if not role_id or not secret_id:
            raise AdjustmentError("Execution bootstrap identity is empty.")

        approle_login = request_json(
            base_url=args.base_url,
            path="auth/approle/login",
            method="POST",
            payload={"role_id": role_id, "secret_id": secret_id},
        )
        test_auth = approle_login.get("auth")
        if not isinstance(test_auth, Mapping):
            raise AdjustmentError("Execution AppRole login returned an invalid response.")
        test_token = require_string(test_auth, "client_token", "an execution test token")

        execution = request_json(
            base_url=args.base_url,
            path=EXECUTION_PATH,
            method="GET",
            token=test_token,
        )
        outer = execution.get("data")
        values = outer.get("data") if isinstance(outer, Mapping) else None
        if not isinstance(values, Mapping) or set(values) != {"api_url", "api_key", "api_secret"}:
            raise AdjustmentError("Execution AppRole secret-read proof returned an unexpected shape.")

        revoke_status = request_status(
            base_url=args.base_url,
            path="auth/token/revoke-self",
            method="POST",
            token=test_token,
            payload={},
        )
        if revoke_status not in (200, 204):
            raise AdjustmentError(
                "Execution AppRole test token could not revoke itself after one KV read."
            )

        post_revoke_status = request_status(
            base_url=args.base_url,
            path=EXECUTION_PATH,
            method="GET",
            token=test_token,
        )
        if post_revoke_status != 403:
            raise AdjustmentError("Execution test token remained usable after revoke-self.")

        update_metadata(metadata_path)

        print("Execution AppRole policy now explicitly permits only self-revocation in addition to the execution-secret read.")
        print("Execution AppRole token-use budget is restored to the approved value of 2.")
        print("One execution KV read plus explicit revoke-self was proven.")
        print("Post-revoke execution secret access was denied.")
        print("Datto provider contacted: NO")
        print("Runtime activation: NO")
        print("Provider write activation: NO")
        print("Component execution: NO")
        print("No credential or token value was displayed.")
        return 0
    finally:
        try:
            request_json(
                base_url=args.base_url,
                path="auth/token/revoke-self",
                method="POST",
                token=admin_token,
                payload={},
                allow_empty=True,
            )
            print("Temporary administrative token revoked.")
        except AdjustmentError:
            print("Temporary administrative token revocation could not be confirmed.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AdjustmentError as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
