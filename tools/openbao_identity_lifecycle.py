#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import hmac
import json
import os
import pwd
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import provider_secret_provision as base
except ModuleNotFoundError:
    import provider_secret_provision as base

ADDRESS = os.getenv("JASON_OPENBAO_URL", "http://127.0.0.1:8200").rstrip("/")
STATE_ROOT = Path("/var/lib/jason/openclaw/identity-lifecycle")
ROLE_MAP = STATE_ROOT / "role-map.json"
LIFECYCLE_CREDENTIAL_DIR = Path(
    "/var/lib/jason/runtime-secrets/openbao/identity-lifecycle-approle"
)
POLICY_NAME = "jason-identity-lifecycle"
ROLE_NAME = "jason-identity-lifecycle"
ROLE_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
ROOT_UID = 0
ROOT_GID = 0
INIT_FILE = Path("/opt/jason/bootstrap/secrets/openbao/init.json")


class IdentityLifecycleError(RuntimeError):
    """Bounded error that must never contain credential values."""


@dataclass(frozen=True, slots=True)
class IdentityProfile:
    provider: str
    source_dir: Path
    staged_runtime_secret_id: Path | None = None


PROFILES: dict[str, IdentityProfile] = {
    "autotask_read": IdentityProfile(
        provider="autotask_read",
        source_dir=Path("/opt/jason/bootstrap/secrets/openbao/autotask-read-approle"),
        staged_runtime_secret_id=Path(
            "/run/jason-runtime-credentials/openbao/autotask/secret_id"
        ),
    ),
    "dnsfilter": IdentityProfile(
        provider="dnsfilter",
        source_dir=Path(
            "/var/lib/jason/runtime-secrets/openbao/dnsfilter-read-approle"
        ),
    ),
}


def _read_private(path: Path, label: str) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise IdentityLifecycleError(f"{label} unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o007:
            raise IdentityLifecycleError(f"{label} protection invalid")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            value = handle.read().strip()
    finally:
        os.close(fd)
    if not value:
        raise IdentityLifecycleError(f"{label} unavailable")
    return value


def _write_private_like(
    path: Path, value: str, template: Path | None = None, *,
    approved_owner_uids: frozenset[int] | None = None,
) -> None:
    if not value:
        raise IdentityLifecycleError("refusing to write empty protected identity")
    source = template or path
    if approved_owner_uids is None:
        approved_owner_uids = frozenset({ROOT_UID})
    try:
        info = os.lstat(source)
    except OSError as exc:
        raise IdentityLifecycleError("protected identity template unavailable") from exc
    if (not stat.S_ISREG(info.st_mode)
            or info.st_uid not in approved_owner_uids
            or info.st_mode & 0o007):
        raise IdentityLifecycleError("protected identity template is not approved")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".identity-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(name, info.st_uid, info.st_gid)
        os.chmod(name, stat.S_IMODE(info.st_mode))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _write_root_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".identity-json-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(name, ROOT_UID, ROOT_GID)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _api(
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    return base.api_request(
        ADDRESS,
        path,
        method=method,
        token=token,
        payload=payload,
        allow_empty=allow_empty,
    )


def _list_approle_names(admin_token: str) -> list[str]:
    response = _api("auth/approle/role", method="LIST", token=admin_token)
    raw = (response.get("data") or {}).get("keys") or []
    names = sorted({str(value) for value in raw if ROLE_RE.fullmatch(str(value))})
    if not names or len(names) > 256:
        raise IdentityLifecycleError("OpenBao AppRole inventory is unavailable or unbounded")
    return names


def discover_role_name(admin_token: str, profile: IdentityProfile) -> str:
    """Discover the exact role by protected RoleID equality; never print RoleIDs."""
    local_role_id = _read_private(profile.source_dir / "role-id", "provider RoleID")
    matches: list[str] = []
    for role_name in _list_approle_names(admin_token):
        try:
            response = _api(
                f"auth/approle/role/{role_name}/role-id",
                method="GET",
                token=admin_token,
            )
            observed = str((response.get("data") or {}).get("role_id") or "")
        except Exception:
            continue
        if observed and hmac.compare_digest(observed, local_role_id):
            matches.append(role_name)
    local_role_id = ""
    if len(matches) != 1:
        raise IdentityLifecycleError(
            "provider AppRole could not be uniquely identified from protected RoleID"
        )
    return matches[0]


def lifecycle_policy_text(role_map: Mapping[str, str]) -> str:
    lines: list[str] = []
    for provider in sorted(role_map):
        if provider not in PROFILES:
            raise IdentityLifecycleError("identity lifecycle role map contains unknown provider")
        role = str(role_map[provider])
        if not ROLE_RE.fullmatch(role):
            raise IdentityLifecycleError("identity lifecycle role name is invalid")
        root = f"auth/approle/role/{role}"
        lines.extend(
            [
                f'path "{root}/secret-id" {{ capabilities=["update"] }}',
                f'path "{root}/secret-id/lookup" {{ capabilities=["update"] }}',
                f'path "{root}/secret-id-accessor/destroy" {{ capabilities=["update"] }}',
            ]
        )
    lines.append('path "auth/token/revoke-self" { capabilities=["update"] }')
    return "\n".join(lines) + "\n"


def _private_file(
    path: Path, value: str, *, uid: int | None = None, gid: int | None = None,
    mode: int = 0o600,
) -> None:
    if uid is None:
        uid = ROOT_UID
    if gid is None:
        gid = ROOT_GID
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.write("\n")
        os.chown(path, uid, gid)
        os.chmod(path, mode)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _lifecycle_bootstrapped() -> bool:
    return (
        ROLE_MAP.is_file()
        and (LIFECYCLE_CREDENTIAL_DIR / "role-id").is_file()
        and (LIFECYCLE_CREDENTIAL_DIR / "secret-id").is_file()
    )


def bootstrap(admin_token: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise PermissionError("OpenBao identity lifecycle bootstrap must run as root")
    if _lifecycle_bootstrapped():
        raise IdentityLifecycleError("identity lifecycle is already bootstrapped")
    discovered = {
        provider: discover_role_name(admin_token, profile)
        for provider, profile in sorted(PROFILES.items())
    }
    _api(
        f"sys/policies/acl/{POLICY_NAME}",
        method="POST",
        token=admin_token,
        payload={"policy": lifecycle_policy_text(discovered)},
        allow_empty=True,
    )
    _api(
        f"auth/approle/role/{ROLE_NAME}",
        method="POST",
        token=admin_token,
        payload={
            "bind_secret_id": True,
            "secret_id_ttl": "2160h",
            "secret_id_num_uses": 0,
            "token_policies": [POLICY_NAME],
            "token_no_default_policy": True,
            "token_ttl": "5m",
            "token_max_ttl": "5m",
            "token_explicit_max_ttl": "5m",
            "token_num_uses": 12,
            "token_type": "service",
        },
        allow_empty=True,
    )
    role_resp = _api(
        f"auth/approle/role/{ROLE_NAME}/role-id", method="GET", token=admin_token
    )
    secret_resp = _api(
        f"auth/approle/role/{ROLE_NAME}/secret-id",
        method="POST",
        token=admin_token,
        payload={"ttl": "2160h", "num_uses": 0},
    )
    role_id = base.require_string(role_resp.get("data") or {}, "role_id", "RoleID")
    secret_data = secret_resp.get("data") or {}
    secret_id = base.require_string(secret_data, "secret_id", "SecretID")
    accessor = base.require_string(secret_data, "secret_id_accessor", "SecretID accessor")
    _private_file(LIFECYCLE_CREDENTIAL_DIR / "role-id", role_id)
    _private_file(LIFECYCLE_CREDENTIAL_DIR / "secret-id", secret_id)
    role_id = ""
    secret_id = ""
    now = datetime.now(timezone.utc)
    _write_root_json(
        ROLE_MAP,
        {
            "schema_version": "1.0",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=90)).isoformat(),
            "lifecycle_secret_id_accessor": accessor,
            "roles": discovered,
            "provider_secret_values_read": False,
            "provider_secret_values_written": False,
        },
    )
    return {
        "status": "pass",
        "action": "bootstrap",
        "providers": sorted(discovered),
        "policy": POLICY_NAME,
        "role": ROLE_NAME,
        "secret_values_printed": False,
        "provider_api_credentials_changed": False,
    }


def _load_role_map() -> dict[str, str]:
    try:
        fd = os.open(ROLE_MAP, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise IdentityLifecycleError("identity lifecycle role map unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o077:
            raise IdentityLifecycleError("identity lifecycle role map protection invalid")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            data = json.load(handle)
    finally:
        os.close(fd)
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise IdentityLifecycleError("identity lifecycle role map invalid")
    roles = data.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(PROFILES):
        raise IdentityLifecycleError("identity lifecycle role map provider set invalid")
    for value in roles.values():
        if not ROLE_RE.fullmatch(str(value)):
            raise IdentityLifecycleError("identity lifecycle role map contains invalid role")
    return {str(k): str(v) for k, v in roles.items()}


def _login_lifecycle() -> str:
    role_id = _read_private(LIFECYCLE_CREDENTIAL_DIR / "role-id", "lifecycle RoleID")
    secret_id = _read_private(LIFECYCLE_CREDENTIAL_DIR / "secret-id", "lifecycle SecretID")
    response = _api(
        "auth/approle/login",
        method="POST",
        payload={"role_id": role_id, "secret_id": secret_id},
    )
    role_id = ""
    secret_id = ""
    token = str((response.get("auth") or {}).get("client_token") or "")
    if not token:
        raise IdentityLifecycleError("OpenBao identity-lifecycle authentication failed")
    return token


def _revoke_token(token: str) -> None:
    try:
        _api("auth/token/revoke-self", method="POST", token=token, payload={}, allow_empty=True)
    except Exception:
        pass


def rotate(provider: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise PermissionError("OpenBao identity rotation must run as root")
    if provider not in PROFILES:
        raise IdentityLifecycleError("provider is not approved for identity lifecycle")
    role_map = _load_role_map()
    role_name = role_map[provider]
    profile = PROFILES[provider]
    old_secret = _read_private(profile.source_dir / "secret-id", "provider SecretID")
    token = _login_lifecycle()
    new_secret = ""
    try:
        lookup = _api(
            f"auth/approle/role/{role_name}/secret-id/lookup",
            method="POST",
            token=token,
            payload={"secret_id": old_secret},
        )
        old_accessor = base.require_string(
            lookup.get("data") or {}, "secret_id_accessor", "existing SecretID accessor"
        )
        created = _api(
            f"auth/approle/role/{role_name}/secret-id",
            method="POST",
            token=token,
            payload={
                "metadata": json.dumps({"connector": provider, "managed_by": ROLE_NAME}),
                "ttl": "2160h",
                "num_uses": 0,
            },
        )
        created_data = created.get("data") or {}
        new_secret = base.require_string(created_data, "secret_id", "replacement SecretID")
        new_accessor = base.require_string(
            created_data, "secret_id_accessor", "replacement SecretID accessor"
        )
        _write_private_like(
            profile.source_dir / "secret-id",
            new_secret,
            template=profile.source_dir / "secret-id",
        )
        staged = False
        if profile.staged_runtime_secret_id is not None:
            _write_private_like(
                profile.staged_runtime_secret_id,
                new_secret,
                template=profile.staged_runtime_secret_id,
                approved_owner_uids=frozenset({0, pwd.getpwnam("al").pw_uid}),
            )
            staged = True
        _api(
            f"auth/approle/role/{role_name}/secret-id-accessor/destroy",
            method="POST",
            token=token,
            payload={"secret_id_accessor": old_accessor},
            allow_empty=True,
        )
        now = datetime.now(timezone.utc)
        _write_root_json(
            STATE_ROOT / "last-rotation.json",
            {
                "schema_version": "1.0",
                "provider": provider,
                "rotated_at": now.isoformat(),
                "replacement_accessor_recorded": bool(new_accessor),
                "old_identity_revoked": True,
                "runtime_staged_copy_updated": staged,
                "runtime_refresh_required": True,
                "provider_api_credentials_changed": False,
                "secret_values_recorded": False,
            },
        )
        return {
            "status": "pass",
            "provider": provider,
            "old_identity_revoked": True,
            "new_identity_installed": True,
            "runtime_staged_copy_updated": staged,
            "runtime_refresh_required": True,
            "provider_api_credentials_changed": False,
            "secret_values_printed": False,
        }
    finally:
        old_secret = ""
        new_secret = ""
        _revoke_token(token)


def _read_root_json(path: Path, label: str) -> dict[str, Any]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise IdentityLifecycleError(f"{label} unavailable") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != ROOT_UID
                or info.st_mode & 0o077):
            raise IdentityLifecycleError(f"{label} protection invalid")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            data = json.load(handle)
    finally:
        os.close(fd)
    if not isinstance(data, dict):
        raise IdentityLifecycleError(f"{label} invalid")
    return data


def bootstrap_from_init(init_file: Path = INIT_FILE) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise PermissionError("protected initialization bootstrap must run as root")
    data = _read_root_json(init_file, "OpenBao initialization artifact")
    initial_token = str(data.get("root_token") or "").strip()
    complete = _lifecycle_bootstrapped()
    if not initial_token:
        if complete:
            return {"status": "already_bootstrapped", "secret_values_printed": False}
        raise IdentityLifecycleError("protected initialization artifact has no usable root token")
    if complete:
        result = {"status": "bootstrap_present_retirement_only", "providers": sorted(PROFILES)}
    else:
        result = bootstrap(initial_token)
    retirement = "revoked_now"
    try:
        base.revoke_admin_token(ADDRESS, initial_token)
    except base.ProvisionError as exc:
        if str(exc) != "OpenBao rejected the provisioning identity.":
            initial_token = ""
            raise IdentityLifecycleError("initial administrative token retirement failed") from exc
        retirement = "already_invalid"
    initial_token = ""
    data["root_token"] = ""
    _write_root_json(init_file, data)
    result = dict(result)
    result.update({"initial_admin_token_revoked": True, "initial_admin_token_retirement_state": retirement, "initial_admin_token_removed_from_init": True, "secret_values_printed": False, "provider_api_credentials_changed": False})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed OpenBao provider identity lifecycle")
    sub = parser.add_subparsers(dest="action", required=True)
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--admin-username", default=base.DEFAULT_ADMIN_USERNAME)
    sub.add_parser("bootstrap-from-init")
    rot = sub.add_parser("rotate")
    rot.add_argument("provider", choices=tuple(sorted(PROFILES)))
    sub.add_parser("status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "bootstrap":
            if os.geteuid() != 0:
                raise PermissionError("bootstrap requires root")
            password = getpass.getpass(f"OpenBao password for {args.admin_username}: ")
            admin_token = base.admin_login(ADDRESS, args.admin_username, password)
            password = ""
            try:
                result = bootstrap(admin_token)
            finally:
                base.revoke_admin_token(ADDRESS, admin_token)
                admin_token = ""
        elif args.action == "bootstrap-from-init":
            result = bootstrap_from_init()
        elif args.action == "rotate":
            result = rotate(args.provider)
        else:
            result = {
                "status": "pass" if ROLE_MAP.is_file() else "not_bootstrapped",
                "bootstrapped": ROLE_MAP.is_file(),
                "providers": sorted(PROFILES),
                "secret_values_printed": False,
            }
    except Exception as exc:
        raise SystemExit(f"DENIED: {type(exc).__name__}: {str(exc)[:250]}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
