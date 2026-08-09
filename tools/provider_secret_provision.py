from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
from typing import Mapping, Sequence
from urllib import error, request


PROVIDERS: dict[str, dict[str, object]] = {
    "datto_rmm": {
        "logical_prefix": "datto_rmm.readonly",
        "secret_path": "secret/data/jason/providers/datto_rmm/readonly",
        "fields": ("api_url", "api_key", "api_secret"),
    },
    "it_glue": {
        "logical_prefix": "it_glue.readonly",
        "secret_path": "secret/data/jason/providers/it_glue/readonly",
        "fields": ("api_key",),
    },
}

RUNTIME_POLICY_NAME = "jason-provider-readonly"
RUNTIME_TOKEN_PATH = Path("/etc/jason/openbao-provider.token")
MAPPING_PATH = Path("/etc/jason/secret-mappings.json")
DEFAULT_ADDRESS = "http://127.0.0.1:8200"


class ProvisionError(RuntimeError):
    pass


def ensure_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ProvisionError(f"Protected file permissions are too broad: {path}")


def read_protected(path: Path) -> str:
    if not path.is_file():
        raise ProvisionError(f"Protected file was not found: {path}")
    ensure_private_file(path)
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ProvisionError(f"Protected file is empty: {path}")
    return value


def api_request(address: str, api_path: str, token: str, *, method: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{address.rstrip('/')}/v1/{api_path.lstrip('/')}",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Vault-Token": token,
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ProvisionError("OpenBao rejected the provisioning identity.") from exc
        raise ProvisionError(f"OpenBao provisioning request failed with HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ProvisionError("OpenBao is unavailable.") from exc
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ProvisionError("OpenBao returned an invalid response.")
    return parsed


def runtime_policy_text() -> str:
    paths = [str(spec["secret_path"]) for spec in PROVIDERS.values()]
    return "\n".join(
        f'path "{path}" {{\n  capabilities = ["read"]\n}}\n' for path in sorted(paths)
    )


def ensure_runtime_identity(*, address: str, admin_token: str, token_output: Path) -> None:
    api_request(
        address,
        f"sys/policies/acl/{RUNTIME_POLICY_NAME}",
        admin_token,
        method="PUT",
        payload={"policy": runtime_policy_text()},
    )
    if token_output.exists():
        return
    response = api_request(
        address,
        "auth/token/create-orphan",
        admin_token,
        method="POST",
        payload={
            "policies": [RUNTIME_POLICY_NAME],
            "display_name": "jason-provider-readonly",
            "renewable": True,
            "period": "24h",
        },
    )
    auth = response.get("auth")
    token = auth.get("client_token") if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        raise ProvisionError("OpenBao did not return the provider runtime token.")
    token_output.parent.mkdir(parents=True, exist_ok=True)
    token_output.write_text(token + "\n", encoding="utf-8")
    token_output.chmod(0o600)


def write_provider_secret(*, address: str, admin_token: str, provider: str, values: Mapping[str, str]) -> None:
    spec = PROVIDERS[provider]
    expected = tuple(spec["fields"])
    missing = [field for field in expected if not values.get(field)]
    if missing:
        raise ProvisionError("Missing provider fields: " + ", ".join(missing))
    api_request(
        address,
        str(spec["secret_path"]),
        admin_token,
        method="POST",
        payload={"data": {field: values[field] for field in expected}},
    )


def update_mappings(path: Path, provider: str) -> None:
    raw: dict[str, object]
    if path.exists():
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ProvisionError("Secret mapping file must contain an object.")
        raw = parsed
    else:
        raw = {}
    spec = PROVIDERS[provider]
    prefix = str(spec["logical_prefix"])
    secret_path = str(spec["secret_path"])
    for field in tuple(spec["fields"]):
        raw[f"{prefix}.{field}"] = {"path": secret_path, "field": field}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o640)


def collect_values(provider: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in tuple(PROVIDERS[provider]["fields"]):
        if field.endswith("url"):
            values[field] = input(f"{provider} {field}: ").strip()
        else:
            values[field] = getpass.getpass(f"{provider} {field}: ").strip()
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision governed provider secrets into OpenBao without printing values.")
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--admin-token-file", type=Path)
    parser.add_argument("--runtime-token-output", type=Path, default=RUNTIME_TOKEN_PATH)
    parser.add_argument("--mapping-path", type=Path, default=MAPPING_PATH)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = PROVIDERS[args.provider]
    if args.check_only:
        print(json.dumps({
            "provider": args.provider,
            "logical_prefix": spec["logical_prefix"],
            "secret_path": spec["secret_path"],
            "fields": list(spec["fields"]),
            "runtime_policy": RUNTIME_POLICY_NAME,
            "runtime_token_output": str(args.runtime_token_output),
            "mapping_path": str(args.mapping_path),
            "network_contacted": False,
            "secret_entered": False,
            "status": "pass",
        }, indent=2, sort_keys=True))
        return 0
    if os.geteuid() != 0:
        raise SystemExit("DENIED: provisioning must run as root")
    if args.admin_token_file is None:
        raise SystemExit("DENIED: --admin-token-file is required for live provisioning")
    try:
        admin_token = read_protected(args.admin_token_file)
        ensure_runtime_identity(address=args.address, admin_token=admin_token, token_output=args.runtime_token_output)
        values = collect_values(args.provider)
        write_provider_secret(address=args.address, admin_token=admin_token, provider=args.provider, values=values)
        update_mappings(args.mapping_path, args.provider)
        values.clear()
        print(json.dumps({
            "provider": args.provider,
            "logical_prefix": spec["logical_prefix"],
            "runtime_token": str(args.runtime_token_output),
            "mapping_path": str(args.mapping_path),
            "secret_values_printed": False,
            "status": "pass",
        }, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
