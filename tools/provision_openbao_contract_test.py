from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Sequence
from urllib import error, request


POLICY_NAME = "jason-contract-test"
POLICY_TEXT = '''path "secret/data/jason/contract-test" {
  capabilities = ["read"]
}
'''
CONTRACT_PATH = "secret/data/jason/contract-test"


def ensure_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"Protected file permissions are too broad: {path}")


def read_secret_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Protected file was not found: {path}")
    ensure_private_file(path)
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"Protected file is empty: {path}")
    return value


def api_request(address: str, api_path: str, token: str, *, method: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{address.rstrip('/')}/v1/{api_path.lstrip('/')}",
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-Vault-Token": token},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise RuntimeError(f"OpenBao request failed with HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("OpenBao is unavailable.") from exc
    if not body:
        return {}
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenBao returned an invalid response.")
    return parsed


def provision(*, address: str, bootstrap_token_file: Path, token_output: Path, contract_value_file: Path) -> dict[str, object]:
    if os.geteuid() != 0:
        raise PermissionError("Provisioning must run as root.")
    bootstrap_token = read_secret_file(bootstrap_token_file)
    contract_value = read_secret_file(contract_value_file)
    if token_output.exists():
        raise FileExistsError("Dedicated token output already exists.")

    api_request(address, f"sys/policies/acl/{POLICY_NAME}", bootstrap_token, method="PUT", payload={"policy": POLICY_TEXT})
    api_request(address, CONTRACT_PATH, bootstrap_token, method="PUT", payload={"data": {"value": contract_value}})
    token_response = api_request(
        address,
        "auth/token/create",
        bootstrap_token,
        method="POST",
        payload={"policies": [POLICY_NAME], "display_name": "jason-contract-test", "renewable": True, "ttl": "24h"},
    )
    auth = token_response.get("auth")
    client_token = auth.get("client_token") if isinstance(auth, dict) else None
    if not isinstance(client_token, str) or not client_token:
        raise RuntimeError("OpenBao did not return a dedicated token.")

    token_output.parent.mkdir(parents=True, exist_ok=True)
    token_output.write_text(client_token + "\n", encoding="utf-8")
    token_output.chmod(0o600)

    environment = {
        **os.environ,
        "JASON_SECRET_BACKEND": "openbao",
        "JASON_OPENBAO_ADDR": address,
        "JASON_OPENBAO_TOKEN_FILE": str(token_output),
    }
    health = subprocess.run(["/usr/local/bin/jason-secret", "--health"], capture_output=True, text=True, timeout=10, env=environment)
    if health.returncode != 0 or health.stdout.strip() != "healthy":
        raise RuntimeError("jason-secret health validation failed.")
    contract = subprocess.run(
        ["/usr/local/bin/jason-secret", "--contract-test", "jason.contract-test"],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    if contract.returncode != 0 or contract.stdout.strip() != "contract-ok":
        raise RuntimeError("jason-secret contract test failed.")

    return {
        "address": address,
        "policy": POLICY_NAME,
        "contract_path": CONTRACT_PATH,
        "token_path": str(token_output),
        "token_mode": "0600",
        "health": "approved",
        "contract_test": "approved",
        "secret_value_exposed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision the non-production OpenBao contract-test identity and verify jason-secret.")
    parser.add_argument("--address", default="http://127.0.0.1:8200")
    parser.add_argument("--bootstrap-token-file", type=Path, default=Path("/etc/jason/openbao-bootstrap.token"))
    parser.add_argument("--token-output", type=Path, default=Path("/etc/jason/openbao.token"))
    parser.add_argument("--contract-value-file", type=Path, default=Path("/etc/jason/openbao-contract-test.value"))
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_only:
        print("APPROVED: Authenticated contract-test configuration validated; no files changed and no OpenBao request made.")
        return 0
    try:
        evidence = provision(
            address=args.address,
            bootstrap_token_file=args.bootstrap_token_file,
            token_output=args.token_output,
            contract_value_file=args.contract_value_file,
        )
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    if args.evidence_output:
        output = args.evidence_output.expanduser().resolve()
        if output.exists():
            raise SystemExit("DENIED: Evidence output already exists.")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.chmod(0o600)
        print(f"Evidence: {output}")
    print("APPROVED: OpenBao authenticated contract test completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
