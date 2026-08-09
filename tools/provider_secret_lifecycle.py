#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import provider_secret_kv_write as kv
    from tools import provider_secret_provision as base
except ModuleNotFoundError:
    import provider_secret_kv_write as kv
    import provider_secret_provision as base

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

ACTIONS = (
    "status",
    "create",
    "update",
    "verify",
    "rotate-identity",
    "deactivate",
    "reactivate",
)


class LifecycleError(RuntimeError):
    """Safe lifecycle error that must never contain secret values."""


def _metadata(provider: str) -> dict[str, Any]:
    path = Path(base.PROVIDERS[provider]["credential_dir"]) / "credential-metadata.json"
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError("Provider AppRole metadata is unreadable.") from exc
    if not isinstance(parsed, dict):
        raise LifecycleError("Provider AppRole metadata has an invalid shape.")
    return parsed


def _credential_state(provider: str) -> dict[str, Any]:
    directory = Path(base.PROVIDERS[provider]["credential_dir"])
    role_id = directory / "role-id"
    secret_id = directory / "secret-id"
    metadata = directory / "credential-metadata.json"
    present = directory.is_dir()
    complete = present and role_id.is_file() and secret_id.is_file() and metadata.is_file()
    return {
        "credential_dir": str(directory),
        "directory_present": present,
        "artifacts_complete": complete,
        "role_id_present": role_id.is_file(),
        "secret_id_present": secret_id.is_file(),
        "metadata_present": metadata.is_file(),
    }


def _atomic_private_file(path: Path, value: str) -> None:
    tmp = path.with_name(path.name + ".new")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.write("\n")
        os.chown(tmp, 0, 0)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _new_secret_id(
    *, address: str, admin_token: str, provider: str
) -> tuple[str, str]:
    spec = base.PROVIDERS[provider]
    response = base.api_request(
        address,
        f"auth/approle/role/{spec['role_name']}/secret-id",
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
    data = response.get("data") or {}
    return (
        base.require_string(data, "secret_id", "the AppRole SecretID"),
        base.require_string(data, "secret_id_accessor", "the SecretID accessor"),
    )


def _revoke_secret_id_accessor(
    *, address: str, admin_token: str, provider: str, accessor: str
) -> None:
    spec = base.PROVIDERS[provider]
    base.api_request(
        address,
        f"auth/approle/role/{spec['role_name']}/secret-id-accessor/destroy",
        method="POST",
        token=admin_token,
        payload={"secret_id_accessor": accessor},
        allow_empty=True,
    )


def _write_rotation_metadata(provider: str, accessor: str) -> None:
    spec = base.PROVIDERS[provider]
    directory = Path(spec["credential_dir"])
    metadata = _metadata(provider)
    now = datetime.now(timezone.utc)
    metadata.update(
        {
            "created_at_utc": now.isoformat(),
            "expires_at_utc": (now + timedelta(days=90)).isoformat(),
            "secret_id_accessor": accessor,
            "rotation_required": True,
            "last_identity_rotation_utc": now.isoformat(),
            "service_token_ttl_seconds": 300,
            "service_token_explicit_max_ttl_seconds": 300,
            "service_token_num_uses": 2,
        }
    )
    _atomic_private_file(
        directory / "credential-metadata.json",
        json.dumps(metadata, indent=2, sort_keys=True),
    )


def rotate_identity(*, address: str, admin_token: str, provider: str) -> dict[str, Any]:
    state = _credential_state(provider)
    if not state["artifacts_complete"]:
        raise LifecycleError("Provider AppRole artifacts are incomplete; use reactivate or create.")
    metadata = _metadata(provider)
    old_accessor = metadata.get("secret_id_accessor")
    if not isinstance(old_accessor, str) or not old_accessor:
        raise LifecycleError("Current AppRole SecretID accessor is unavailable.")

    spec = base.PROVIDERS[provider]
    # Re-assert the canonical policy/role configuration before issuing a new identity.
    base.configure_read_approle(
        address=address,
        admin_token=admin_token,
        provider=provider,
    )
    new_secret_id, new_accessor = _new_secret_id(
        address=address,
        admin_token=admin_token,
        provider=provider,
    )
    directory = Path(spec["credential_dir"])
    _atomic_private_file(directory / "secret-id", new_secret_id)
    _write_rotation_metadata(provider, new_accessor)
    new_secret_id = ""
    _revoke_secret_id_accessor(
        address=address,
        admin_token=admin_token,
        provider=provider,
        accessor=old_accessor,
    )
    return {
        "provider": provider,
        "action": "rotate-identity",
        "old_identity_revoked": True,
        "new_identity_installed": True,
        "secret_values_printed": False,
        "status": "pass",
    }


def deactivate(*, address: str, admin_token: str, provider: str) -> dict[str, Any]:
    spec = base.PROVIDERS[provider]
    directory = Path(spec["credential_dir"])
    metadata = _metadata(provider)
    accessor = metadata.get("secret_id_accessor")
    if isinstance(accessor, str) and accessor:
        try:
            _revoke_secret_id_accessor(
                address=address,
                admin_token=admin_token,
                provider=provider,
                accessor=accessor,
            )
        except base.ProvisionError:
            # Deleting the role below is the authoritative fail-closed action.
            pass

    base.api_request(
        address,
        f"auth/approle/role/{spec['role_name']}",
        method="DELETE",
        token=admin_token,
        allow_empty=True,
    )

    if directory.exists():
        for name in ("secret-id", "role-id", "credential-metadata.json"):
            path = directory / name
            if path.exists():
                path.unlink()
        try:
            directory.rmdir()
        except OSError as exc:
            raise LifecycleError("Provider AppRole directory could not be retired cleanly.") from exc

    return {
        "provider": provider,
        "action": "deactivate",
        "runtime_access_active": False,
        "kv_history_preserved": True,
        "provider_secret_destroyed": False,
        "status": "pass",
    }


def reactivate(*, address: str, admin_token: str, provider: str) -> dict[str, Any]:
    state = _credential_state(provider)
    if state["directory_present"]:
        raise LifecycleError("Provider credential directory already exists; use verify or rotate-identity.")
    version = kv.current_version(
        address,
        str(base.PROVIDERS[provider]["secret_path"]),
        admin_token,
    )
    if version < 1:
        raise LifecycleError("Provider secret does not exist; use create instead.")
    identity = base.configure_read_approle(
        address=address,
        admin_token=admin_token,
        provider=provider,
    )
    return {
        "provider": provider,
        "action": "reactivate",
        "runtime_access_active": True,
        "credential_dir": identity["credential_dir"],
        "kv_version": version,
        "provider_secret_reentered": False,
        "status": "pass",
    }


def verify(provider: str) -> dict[str, Any]:
    from connectors.core.contracts import ConnectorContext
    from connectors.core.openbao_secrets import OpenBaoSecretResolver

    spec = base.PROVIDERS[provider]
    directory = Path(spec["credential_dir"])
    state = _credential_state(provider)
    if not state["artifacts_complete"]:
        raise LifecycleError("Provider AppRole artifacts are incomplete or inactive.")
    resolver = OpenBaoSecretResolver(
        base_url=base.DEFAULT_ADDRESS,
        role_id_path=directory / "role-id",
        secret_id_path=directory / "secret-id",
    )
    context = ConnectorContext(
        correlation_id=f"provider-secret-verify-{provider}",
        principal_id="provider-secret-lifecycle",
        organization_id="aot",
        client_id=None,
        capability=f"{provider}.secret.verify",
        mode="observe",
    )
    values = dict(resolver.resolve(str(spec["logical_name"]), context))
    try:
        expected = set(spec["fields"])
        if set(values) != expected:
            raise LifecycleError("Provider secret field contract mismatch.")
        return {
            "provider": provider,
            "action": "verify",
            "runtime_access_active": True,
            "field_contract_valid": True,
            "secret_values_printed": False,
            "runtime_token_persisted": False,
            "status": "pass",
        }
    finally:
        values.clear()


def status(*, address: str, admin_token: str, provider: str) -> dict[str, Any]:
    spec = base.PROVIDERS[provider]
    state = _credential_state(provider)
    version = kv.current_version(address, str(spec["secret_path"]), admin_token)
    metadata = _metadata(provider) if state["metadata_present"] else {}
    return {
        "provider": provider,
        "action": "status",
        "logical_name": spec["logical_name"],
        "kv_version": version,
        "secret_present": version > 0,
        "runtime_access_active": bool(state["artifacts_complete"]),
        "approle_artifacts": state,
        "identity_expires_at_utc": metadata.get("expires_at_utc"),
        "secret_values_printed": False,
        "status": "pass",
    }


def create_or_update(
    *, address: str, admin_token: str, provider: str, action: str
) -> dict[str, Any]:
    current = kv.current_version(
        address,
        str(base.PROVIDERS[provider]["secret_path"]),
        admin_token,
    )
    if action == "create" and current != 0:
        raise LifecycleError("Provider secret already exists; use update.")
    if action == "update" and current == 0:
        raise LifecycleError("Provider secret does not exist; use create.")
    identity = base.configure_read_approle(
        address=address,
        admin_token=admin_token,
        provider=provider,
    )
    values = base.collect_values(provider)
    try:
        version = kv.write_provider_secret_cas(
            address=address,
            admin_token=admin_token,
            provider=provider,
            values=values,
        )
    finally:
        values.clear()
    return {
        "provider": provider,
        "action": action,
        "kv_version_written": version,
        "credential_dir": identity["credential_dir"],
        "runtime_authentication": "approle",
        "runtime_token_persisted": False,
        "secret_values_printed": False,
        "status": "pass",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Canonical lifecycle manager for governed provider secrets."
    )
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("provider", choices=sorted(base.PROVIDERS))
    parser.add_argument("--address", default=base.DEFAULT_ADDRESS)
    parser.add_argument("--admin-username", default=base.DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--check-only", action="store_true")
    return parser


def _check_only(action: str, provider: str) -> dict[str, Any]:
    spec = base.PROVIDERS[provider]
    return {
        "provider": provider,
        "action": action,
        "logical_name": spec["logical_name"],
        "secret_path": spec["secret_path"],
        "runtime_authentication": "approle",
        "kv_write_semantics": "kv_v2_compare_and_set",
        "deactivation_semantics": "revoke_runtime_identity_preserve_kv_history",
        "runtime_token_persisted": False,
        "network_contacted": False,
        "secret_entered": False,
        "status": "pass",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_only:
        print(json.dumps(_check_only(args.action, args.provider), indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("DENIED: provider secret lifecycle operations must run as root")
    if args.action == "verify":
        print(json.dumps(verify(args.provider), indent=2, sort_keys=True))
        return 0

    admin_password = getpass.getpass(f"OpenBao password for {args.admin_username}: ")
    admin_token: str | None = None
    try:
        admin_token = base.admin_login(args.address, args.admin_username, admin_password)
        admin_password = ""
        if args.action in {"create", "update"}:
            result = create_or_update(
                address=args.address,
                admin_token=admin_token,
                provider=args.provider,
                action=args.action,
            )
        elif args.action == "rotate-identity":
            result = rotate_identity(
                address=args.address, admin_token=admin_token, provider=args.provider
            )
        elif args.action == "deactivate":
            result = deactivate(
                address=args.address, admin_token=admin_token, provider=args.provider
            )
        elif args.action == "reactivate":
            result = reactivate(
                address=args.address, admin_token=admin_token, provider=args.provider
            )
        elif args.action == "status":
            result = status(
                address=args.address, admin_token=admin_token, provider=args.provider
            )
        else:
            raise LifecycleError("Unsupported lifecycle action.")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (LifecycleError, base.ProvisionError) as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    finally:
        admin_password = ""
        if admin_token:
            try:
                base.revoke_admin_token(args.address, admin_token)
                print("[PASS] Temporary administrative token revoked.")
            except base.ProvisionError:
                print(
                    "[WARN] Temporary administrative token could not be revoked explicitly.",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
