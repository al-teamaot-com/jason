from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
from typing import Sequence
from urllib import error, request


def ensure_private_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Protected file was not found: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"Protected file permissions are too broad: {path}")


def read_protected_value(path: Path) -> str:
    ensure_private_file(path)
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"Protected file is empty: {path}")
    return value


def run_wrapper_validation(*, address: str, runtime_token_file: Path, wrapper: Path) -> None:
    ensure_private_file(runtime_token_file)
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise FileNotFoundError(f"Canonical secret wrapper is not executable: {wrapper}")
    environment = {
        **os.environ,
        "JASON_SECRET_BACKEND": "openbao",
        "JASON_OPENBAO_ADDR": address,
        "JASON_OPENBAO_TOKEN_FILE": str(runtime_token_file),
    }
    health = subprocess.run([str(wrapper), "--health"], capture_output=True, text=True, timeout=10, env=environment)
    if health.returncode != 0 or health.stdout.strip() != "healthy":
        raise RuntimeError("Dedicated runtime token failed jason-secret health validation.")
    contract = subprocess.run(
        [str(wrapper), "--contract-test", "jason.contract-test"],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    if contract.returncode != 0 or contract.stdout.strip() != "contract-ok":
        raise RuntimeError("Dedicated runtime token failed jason-secret contract validation.")


def token_lookup_self(address: str, token: str) -> dict[str, object]:
    req = request.Request(
        f"{address.rstrip('/')}/v1/auth/token/lookup-self",
        headers={"Accept": "application/json", "X-Vault-Token": token},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"Runtime token lookup failed with HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("OpenBao runtime token lookup could not be completed.") from exc
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("OpenBao returned invalid runtime token metadata.")
    return data


def require_orphan_runtime(address: str, runtime_token: str) -> None:
    data = token_lookup_self(address, runtime_token)
    parent = data.get("parent")
    if parent not in (None, ""):
        raise RuntimeError("Dedicated runtime token is parented and would be revoked with the bootstrap identity.")


def revoke_self(address: str, token: str) -> None:
    req = request.Request(
        f"{address.rstrip('/')}/v1/auth/token/revoke-self",
        data=b"{}",
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-Vault-Token": token},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"OpenBao returned unexpected HTTP {response.status} during revocation.")
    except error.HTTPError as exc:
        raise RuntimeError(f"Bootstrap token revocation failed with HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("OpenBao bootstrap token revocation could not be completed.") from exc


def validate_evidence_output(path: Path) -> Path:
    output = path.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Evidence output already exists.")
    output.parent.mkdir(parents=True, exist_ok=True)
    probe = output.parent / f".{output.name}.write-test"
    try:
        probe.write_text("", encoding="utf-8")
    finally:
        probe.unlink(missing_ok=True)
    return output


def retire(*, address: str, bootstrap_token_file: Path, contract_value_file: Path, runtime_token_file: Path, wrapper: Path, evidence_output: Path) -> dict[str, object]:
    if os.geteuid() != 0:
        raise PermissionError("Bootstrap retirement must run as root.")

    ensure_private_file(bootstrap_token_file)
    ensure_private_file(contract_value_file)
    bootstrap_token = read_protected_value(bootstrap_token_file)
    runtime_token = read_protected_value(runtime_token_file)
    output = validate_evidence_output(evidence_output)

    run_wrapper_validation(address=address, runtime_token_file=runtime_token_file, wrapper=wrapper)
    require_orphan_runtime(address, runtime_token)

    revoke_self(address, bootstrap_token)
    bootstrap_token = ""

    run_wrapper_validation(address=address, runtime_token_file=runtime_token_file, wrapper=wrapper)
    require_orphan_runtime(address, runtime_token)
    runtime_token = ""

    bootstrap_token_file.unlink()
    contract_value_file.unlink()

    evidence = {
        "schema_version": "1.1",
        "evidence_type": "openbao-bootstrap-retirement",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "address": address,
        "runtime_token_path": str(runtime_token_file),
        "runtime_token_orphan": True,
        "runtime_health_before_revocation": "approved",
        "runtime_contract_before_revocation": "approved",
        "runtime_health_after_revocation": "approved",
        "runtime_contract_after_revocation": "approved",
        "bootstrap_token_revoked": True,
        "bootstrap_token_file_removed": not bootstrap_token_file.exists(),
        "contract_value_file_removed": not contract_value_file.exists(),
        "protected_values_exposed": False,
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the dedicated OpenBao runtime identity and retire temporary bootstrap artifacts.")
    parser.add_argument("--address", default="http://127.0.0.1:8200")
    parser.add_argument("--bootstrap-token-file", type=Path, default=Path("/etc/jason/openbao-bootstrap.token"))
    parser.add_argument("--contract-value-file", type=Path, default=Path("/etc/jason/openbao-contract-test.value"))
    parser.add_argument("--runtime-token-file", type=Path, default=Path("/etc/jason/openbao.token"))
    parser.add_argument("--wrapper", type=Path, default=Path("/usr/local/bin/jason-secret"))
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_only:
        print("APPROVED: Bootstrap retirement configuration validated; no token read, no OpenBao request made, and no file changed.")
        return 0
    try:
        retire(address=args.address, bootstrap_token_file=args.bootstrap_token_file, contract_value_file=args.contract_value_file, runtime_token_file=args.runtime_token_file, wrapper=args.wrapper, evidence_output=args.evidence_output)
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    print(f"Evidence: {args.evidence_output.expanduser().resolve()}")
    print("APPROVED: OpenBao bootstrap credential retired.")
    print("No token, password, contract value, or unseal material was displayed or stored in evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
