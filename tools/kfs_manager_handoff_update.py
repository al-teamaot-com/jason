#!/usr/bin/env python3
from __future__ import annotations

import base64
import binascii
import getpass
import json
import os
import stat
import sys
from pathlib import Path

try:
    from tools import provider_secret_kv_write as kv
    from tools import provider_secret_provision as base
    from tools.provider_secret_lifecycle import verify
except ModuleNotFoundError:
    import provider_secret_kv_write as kv
    import provider_secret_provision as base
    from provider_secret_lifecycle import verify

PROVIDER = "kyocera_kfs"
DEFAULT_HANDOFF = Path("/home/al/kfs-claw-handoff/kfs-manager-current.json")


def _basic_pair(value: str) -> tuple[str, str] | None:
    token = str(value or "").strip()
    if token.lower().startswith("basic "):
        token = token[6:].strip()
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    return tuple(decoded.split(":", 1))


def _load_handoff(path: Path) -> dict[str, str]:
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("KFS Manager handoff must have mode 0600.")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or set(parsed) != {"kfs_username", "kfs_password"}:
        raise RuntimeError("KFS Manager handoff has an invalid field contract.")
    values = {name: str(parsed[name]) for name in parsed}
    if any(not value for value in values.values()):
        raise RuntimeError("KFS Manager handoff contains an empty field.")
    return values


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("DENIED: KFS Manager handoff update must run as root")

    handoff_path = Path(os.getenv("JASON_KFS_MANAGER_HANDOFF", str(DEFAULT_HANDOFF)))
    handoff = _load_handoff(handoff_path)
    address = base.DEFAULT_ADDRESS
    username = base.DEFAULT_ADMIN_USERNAME
    admin_password = getpass.getpass(f"OpenBao password for {username}: ")
    admin_token = None
    current: dict[str, str] = {}
    updated: dict[str, str] = {}
    try:
        admin_token = base.admin_login(address, username, admin_password)
        admin_password = ""
        spec = base.PROVIDERS[PROVIDER]
        secret_path = str(spec["secret_path"])
        version_before = kv.current_version(address, secret_path, admin_token)
        if version_before < 1:
            raise RuntimeError("Current KFS secret does not exist.")
        response = base.api_request(
            address,
            secret_path,
            method="GET",
            token=admin_token,
        )
        current_raw = ((response.get("data") or {}).get("data") or {})
        if not isinstance(current_raw, dict):
            raise RuntimeError("Current KFS secret has an invalid shape.")
        current = {name: str(value) for name, value in current_raw.items()}

        required = tuple(spec["fields"])
        missing = [name for name in required if not current.get(name)]
        if missing:
            raise RuntimeError(
                "Current KFS secret is missing required fields: " + ", ".join(missing)
            )

        gateway_pair = _basic_pair(current["authorization"])
        manager_pair = (handoff["kfs_username"], handoff["kfs_password"])
        if gateway_pair is not None and manager_pair == gateway_pair:
            raise RuntimeError(
                "Refusing KFS update: Manager login equals dealer gateway credential."
            )

        updated = {name: current[name] for name in required}
        updated["kfs_username"] = handoff["kfs_username"]
        updated["kfs_password"] = handoff["kfs_password"]
        base.api_request(
            address,
            secret_path,
            method="POST",
            token=admin_token,
            payload={
                "options": {"cas": version_before},
                "data": {name: updated[name] for name in required},
            },
            allow_empty=True,
        )
        version = version_before + 1
        check = verify(PROVIDER)
        handoff_path.unlink()
        print(json.dumps({
            "provider": PROVIDER,
            "kv_version_written": version,
            "manager_identity_updated": True,
            "gateway_credential_preserved": True,
            "handoff_deleted": True,
            "runtime_access_active": check["runtime_access_active"],
            "field_contract_valid": check["field_contract_valid"],
            "secret_values_printed": False,
            "status": "pass",
        }, indent=2, sort_keys=True))
        return 0
    finally:
        admin_password = ""
        handoff.clear()
        current.clear()
        updated.clear()
        if admin_token:
            try:
                base.revoke_admin_token(address, admin_token)
                print("[PASS] Temporary administrative token revoked.")
            except base.ProvisionError:
                print("[WARN] Temporary administrative token revoke failed.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
