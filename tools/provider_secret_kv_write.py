#!/usr/bin/env python3

from __future__ import annotations

import getpass
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Mapping

from tools import provider_secret_provision as base


def metadata_path(secret_path: str) -> str:
    marker = "/data/"
    if marker not in secret_path:
        raise base.ProvisionError("Provider secret path is not a KV v2 data path.")
    mount, relative = secret_path.split(marker, 1)
    return f"{mount}/metadata/{relative}"


def current_version(address: str, secret_path: str, token: str) -> int:
    api_path = metadata_path(secret_path)
    req = urllib.request.Request(
        f"{address.rstrip('/')}/v1/{api_path}",
        headers={"Accept": "application/json", "X-Vault-Token": token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 0
        if exc.code in (401, 403):
            raise base.ProvisionError(
                "OpenBao rejected the provisioning identity while reading secret metadata."
            ) from exc
        raise base.ProvisionError(
            f"OpenBao metadata request failed with HTTP {exc.code}."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise base.ProvisionError("OpenBao metadata lookup failed.") from exc

    try:
        parsed = json.loads(raw)
        version = parsed["data"]["current_version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise base.ProvisionError(
            "OpenBao returned invalid provider-secret metadata."
        ) from exc

    if not isinstance(version, int) or version < 0:
        raise base.ProvisionError("OpenBao returned an invalid secret version.")
    return version


def write_provider_secret_cas(
    *,
    address: str,
    admin_token: str,
    provider: str,
    values: Mapping[str, str],
) -> int:
    spec = base.PROVIDERS[provider]
    expected = tuple(spec["fields"])
    missing = [field for field in expected if not values.get(field)]
    if missing:
        raise base.ProvisionError("Missing provider fields: " + ", ".join(missing))

    secret_path = str(spec["secret_path"])
    version = current_version(address, secret_path, admin_token)
    base.api_request(
        address,
        secret_path,
        method="POST",
        token=admin_token,
        payload={
            "options": {"cas": version},
            "data": {field: values[field] for field in expected},
        },
        allow_empty=True,
    )
    return version + 1


def main() -> int:
    parser = base.build_parser()
    args = parser.parse_args()
    spec = base.PROVIDERS[args.provider]

    if args.check_only:
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "logical_name": spec["logical_name"],
                    "secret_path": spec["secret_path"],
                    "fields": list(spec["fields"]),
                    "write_semantics": "kv_v2_compare_and_set",
                    "network_contacted": False,
                    "secret_entered": False,
                    "status": "pass",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if base.os.geteuid() != 0:
        raise SystemExit("DENIED: provisioning must run as root")

    admin_password = getpass.getpass(
        f"OpenBao password for {args.admin_username}: "
    )
    admin_token: str | None = None
    values: dict[str, str] = {}
    try:
        admin_token = base.admin_login(
            args.address,
            args.admin_username,
            admin_password,
        )
        admin_password = ""
        identity = base.configure_read_approle(
            address=args.address,
            admin_token=admin_token,
            provider=args.provider,
        )
        values = base.collect_values(args.provider)
        new_version = write_provider_secret_cas(
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
                    "kv_version_written": new_version,
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
                base.revoke_admin_token(args.address, admin_token)
                print("[PASS] Temporary administrative token revoked.")
            except base.ProvisionError:
                print(
                    "[WARN] Temporary administrative token could not be revoked explicitly.",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
