from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from typing import Sequence
from urllib import error, request


DEFAULT_ADDRESS = "http://127.0.0.1:8200"
DEFAULT_TEST_ADDRESS = "http://127.0.0.1:8300"
DEFAULT_IMAGE = "ghcr.io/openbao/openbao:2.6.1"
DEFAULT_CONTAINER = "openbao-restore-test"
DEFAULT_NETWORK = "jason-restore-test"
DEFAULT_BACKUP_DIR = Path("/opt/jason/backups/openbao")
DEFAULT_INIT_FILE = Path("/opt/jason/bootstrap/secrets/openbao/init.json")
DEFAULT_TOKEN_FILE = Path("/etc/jason/openbao.token")
DEFAULT_WRAPPER = Path("/usr/local/bin/jason-secret")


class RestoreTestError(RuntimeError):
    pass


def run(command: list[str], *, capture: bool = True, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=capture,
        text=True,
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RestoreTestError(f"Command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result


def ensure_private_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Protected file was not found: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"Protected file permissions are too broad: {path}")


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RestoreTestError(f"Expected JSON object: {path}")
    return value


def api_json(address: str, path: str, *, method: str = "GET", token: str | None = None, payload: dict[str, object] | None = None, timeout: int = 15) -> tuple[int, dict[str, object]]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(f"{address.rstrip('/')}/v1/{path.lstrip('/')}", data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, parsed
    except error.HTTPError as exc:
        raw = exc.read()
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        return exc.code, parsed
    except (error.URLError, TimeoutError, OSError) as exc:
        raise RestoreTestError(f"OpenBao request failed: {exc}") from exc


def wait_for_health(address: str, expected: set[int], attempts: int = 30) -> tuple[int, dict[str, object]]:
    last_status = 0
    last_data: dict[str, object] = {}
    for _ in range(attempts):
        try:
            last_status, last_data = api_json(address, "sys/health")
        except RestoreTestError:
            last_status, last_data = 0, {}
        if last_status in expected:
            return last_status, last_data
        time.sleep(1)
    raise RestoreTestError(f"OpenBao health did not reach an expected status; last HTTP status was {last_status}.")


def latest_snapshot(backup_dir: Path) -> Path:
    snapshots = sorted(backup_dir.glob("*.snap"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not snapshots:
        raise FileNotFoundError(f"No Raft snapshot was found in {backup_dir}")
    snapshot = snapshots[0]
    sidecar = Path(str(snapshot) + ".sha256")
    if not sidecar.is_file():
        raise FileNotFoundError(f"Snapshot checksum sidecar was not found: {sidecar}")
    return snapshot


def verify_snapshot(snapshot: Path) -> tuple[str, int]:
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    sidecar = Path(str(snapshot) + ".sha256")
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    if digest != expected:
        raise RestoreTestError("Raft snapshot checksum verification failed.")
    return digest, snapshot.stat().st_size


def wrapper_validation(wrapper: Path, address: str, token_file: Path) -> None:
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise FileNotFoundError(f"Canonical wrapper is not executable: {wrapper}")
    ensure_private_file(token_file)
    env = {
        **os.environ,
        "JASON_SECRET_BACKEND": "openbao",
        "JASON_OPENBAO_ADDR": address,
        "JASON_OPENBAO_TOKEN_FILE": str(token_file),
    }
    health = run([str(wrapper), "--health"], env=env)
    if health.stdout.strip() != "healthy":
        raise RestoreTestError("Secret wrapper health validation failed.")
    contract = run([str(wrapper), "--contract-test", "jason.contract-test"], env=env)
    if contract.stdout.strip() != "contract-ok":
        raise RestoreTestError("Secret wrapper contract validation failed.")


def write_config(root: Path) -> None:
    config = root / "config" / "openbao.hcl"
    config.write_text(
        '''storage "raft" {
  path    = "/openbao/data"
  node_id = "jason-restore-test"
}

listener "tcp" {
  address         = "0.0.0.0:8300"
  cluster_address = "0.0.0.0:8301"
  tls_disable     = 1
}

api_addr     = "http://127.0.0.1:8300"
cluster_addr = "http://127.0.0.1:8301"
disable_mlock = true
ui = false
''',
        encoding="utf-8",
    )
    os.chown(root / "config", 0, 1000)
    os.chown(config, 0, 1000)
    os.chmod(root / "config", 0o750)
    os.chmod(config, 0o640)
    for name in ("data", "audit", "logs"):
        path = root / name
        os.chown(path, 100, 1000)
        os.chmod(path, 0o750)


def cleanup(container: str, network: str, root: Path) -> None:
    run(["docker", "rm", "-f", container], check=False)
    run(["docker", "network", "rm", network], check=False)
    shutil.rmtree(root, ignore_errors=True)


def unseal(address: str, init_file: Path) -> None:
    init_data = read_json(init_file)
    shares = init_data.get("unseal_keys_b64")
    threshold = init_data.get("unseal_threshold")
    if not isinstance(shares, list) or not isinstance(threshold, int) or threshold <= 0 or len(shares) < threshold:
        raise RestoreTestError("Protected initialization material does not satisfy its recorded threshold.")
    result: dict[str, object] = {}
    for share in shares[:threshold]:
        if not isinstance(share, str) or not share:
            raise RestoreTestError("Protected initialization material contains an invalid share.")
        status, result = api_json(address, "sys/unseal", method="POST", payload={"key": share})
        if status != 200:
            raise RestoreTestError(f"OpenBao rejected a protected unseal share with HTTP {status}.")
    if bool(result.get("sealed")):
        raise RestoreTestError("Restored OpenBao remained sealed after the configured threshold.")


def validate_configuration(args: argparse.Namespace) -> None:
    if args.test_address.rstrip("/") == args.address.rstrip("/"):
        raise ValueError("The test address must differ from the live OpenBao address.")
    if args.container == "openbao":
        raise ValueError("The isolated restore container must not use the live container name.")
    if args.network == "jason-core":
        raise ValueError("The isolated restore test must not use the live Docker network.")
    if args.evidence_output.expanduser().resolve().exists():
        raise FileExistsError("Evidence output already exists.")


def execute(args: argparse.Namespace) -> dict[str, object]:
    validate_configuration(args)
    if args.check_only:
        return {
            "status": "approved",
            "mode": "check-only",
            "docker_contacted": False,
            "openbao_contacted": False,
            "protected_material_read": False,
            "evidence_written": False,
        }
    if os.geteuid() != 0:
        raise PermissionError("The governed restore test must run as root.")

    ensure_private_file(args.init_file)
    ensure_private_file(args.token_file)
    snapshot = latest_snapshot(args.backup_dir)
    snapshot_sha256, snapshot_size = verify_snapshot(snapshot)
    live_status, live_health = wait_for_health(args.address, {200, 429})
    if not live_health.get("initialized") or live_health.get("sealed"):
        raise RestoreTestError("Live OpenBao is not initialized and unsealed.")
    live_cluster_id = str(live_health.get("cluster_id") or "")
    if not live_cluster_id:
        raise RestoreTestError("Live OpenBao cluster ID is missing.")
    wrapper_validation(args.wrapper, args.address, args.token_file)

    root = Path(tempfile.mkdtemp(prefix="jason-openbao-restore-", dir="/tmp"))
    output = args.evidence_output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for name in ("config", "data", "audit", "logs", "snapshot"):
            (root / name).mkdir()
        write_config(root)
        restore_snapshot = root / "snapshot" / "restore.snap"
        shutil.copy2(snapshot, restore_snapshot)
        os.chown(root / "snapshot", 0, 0)
        os.chown(restore_snapshot, 0, 0)
        os.chmod(root / "snapshot", 0o750)
        os.chmod(restore_snapshot, 0o600)

        cleanup(args.container, args.network, Path("/nonexistent-jason-restore-cleanup"))
        run(["docker", "network", "create", "--driver", "bridge", args.network])
        run([
            "docker", "run", "-d", "--name", args.container, "--hostname", args.container,
            "--user", "0:0", "--network", args.network, "--cap-add", "IPC_LOCK",
            "--security-opt", "no-new-privileges:true", "-p", "127.0.0.1:8300:8300",
            "-v", f"{root / 'config'}:/openbao/config:ro",
            "-v", f"{root / 'data'}:/openbao/data",
            "-v", f"{root / 'audit'}:/openbao/audit",
            "-v", f"{root / 'logs'}:/openbao/logs",
            "-v", f"{root / 'snapshot'}:/snapshot:ro",
            args.image, "server", "-config=/openbao/config/openbao.hcl",
        ])
        wait_for_health(args.test_address, {501})

        initialized = run([
            "docker", "exec", "-e", "BAO_ADDR=http://127.0.0.1:8300", args.container,
            "bao", "operator", "init", "-key-shares=1", "-key-threshold=1", "-format=json",
        ])
        temporary_init = json.loads(initialized.stdout)
        temporary_key = temporary_init.get("unseal_keys_b64", [None])[0]
        temporary_token = temporary_init.get("root_token")
        if not isinstance(temporary_key, str) or not isinstance(temporary_token, str):
            raise RestoreTestError("Temporary restore target initialization returned incomplete protected material.")
        status, result = api_json(args.test_address, "sys/unseal", method="POST", payload={"key": temporary_key})
        temporary_key = ""
        if status != 200 or result.get("sealed"):
            raise RestoreTestError("Temporary restore target could not be unsealed.")

        run([
            "docker", "exec", "-e", "BAO_ADDR=http://127.0.0.1:8300", "-e", f"BAO_TOKEN={temporary_token}",
            args.container, "bao", "operator", "raft", "snapshot", "restore", "-force", "/snapshot/restore.snap",
        ])
        temporary_token = ""
        wait_for_health(args.test_address, {503})
        unseal(args.test_address, args.init_file)
        _, restored_health = wait_for_health(args.test_address, {200, 429})
        restored_cluster_id = str(restored_health.get("cluster_id") or "")
        if restored_cluster_id != live_cluster_id:
            raise RestoreTestError("Restored cluster ID does not match the source cluster.")
        wrapper_validation(args.wrapper, args.test_address, args.token_file)
        wrapper_validation(args.wrapper, args.address, args.token_file)

        evidence = {
            "schema_version": "1.0",
            "evidence_type": "openbao-raft-restore-test",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "host": socket.gethostname(),
            "snapshot_path": str(snapshot),
            "snapshot_sha256": snapshot_sha256,
            "snapshot_size_bytes": snapshot_size,
            "isolated_container": args.container,
            "isolated_network": args.network,
            "isolated_host_port": 8300,
            "live_cluster_id": live_cluster_id,
            "restored_cluster_id": restored_cluster_id,
            "cluster_identity_match": True,
            "restored_initialized": True,
            "restored_unsealed": True,
            "restored_secret_contract": "approved",
            "live_service_after_test": "approved",
            "live_data_modified": False,
            "protected_values_exposed": False,
            "status": "approved",
        }
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.chmod(0o600)
        return evidence
    finally:
        cleanup(args.container, args.network, root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore the latest verified OpenBao Raft snapshot into an isolated test instance and collect non-secret evidence.")
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--test-address", default=DEFAULT_TEST_ADDRESS)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--init-file", type=Path, default=DEFAULT_INIT_FILE)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--wrapper", type=Path, default=DEFAULT_WRAPPER)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evidence = execute(args)
    except Exception as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
    if args.check_only:
        print(json.dumps(evidence, indent=2, sort_keys=True))
        print("APPROVED: Restore-test configuration validated; no Docker or OpenBao request made, no protected material read, and no evidence written.")
    else:
        print(f"Evidence: {args.evidence_output.expanduser().resolve()}")
        print("APPROVED: Isolated OpenBao Raft restore test completed.")
        print("No token, password, unseal share, recovery material, or secret value was displayed or stored in evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
