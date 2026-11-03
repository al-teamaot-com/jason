#!/usr/bin/env python3
"""Recover the single-host Jason pilot after host/OpenBao restart.

This script is intentionally secret-safe:
- it never prints OpenBao unseal shares or provider AppRole values;
- it reads protected initialization material only when OpenBao is sealed;
- it stages only the existing governed runtime AppRole files;
- it fails closed on unexpected metadata or incomplete staging.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENBAO_CONTAINER = "openbao"
OPENBAO_HEALTH_URL = "http://127.0.0.1:8200/v1/sys/health"
OPENBAO_UNSEAL_URL = "http://127.0.0.1:8200/v1/sys/unseal"
INIT_FILE = Path("/opt/jason/bootstrap/secrets/openbao/init.json")
REPO_ROOT = Path("/home/al/projects/jason")
STAGER = REPO_ROOT / "tools/stage_provider_read_runtime_credentials.py"
STAGED_FILES = (
    Path("/run/jason-runtime-credentials/openbao/autotask/role_id"),
    Path("/run/jason-runtime-credentials/openbao/autotask/secret_id"),
    Path("/run/jason-runtime-credentials/openbao/it-glue/role_id"),
    Path("/run/jason-runtime-credentials/openbao/it-glue/secret_id"),
)
RUNTIME_CONTAINER = "jason-runtime"
MCP_CONTAINER = "jason-mcp-pilot"


class RecoveryError(RuntimeError):
    pass


def run(args: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "check": False,
        "text": True,
        "stdout": subprocess.DEVNULL if quiet else subprocess.PIPE,
        "stderr": subprocess.DEVNULL if quiet else subprocess.PIPE,
    }
    return subprocess.run(args, **kwargs)


def require_ok(result: subprocess.CompletedProcess[str], message: str) -> None:
    if result.returncode != 0:
        raise RecoveryError(message)


def docker_exists(name: str) -> bool:
    return run(["docker", "inspect", name], quiet=True).returncode == 0


def docker_start(name: str) -> None:
    if not docker_exists(name):
        raise RecoveryError(f"required container is missing: {name}")
    require_ok(run(["docker", "start", name], quiet=True), f"failed to start {name}")


def openbao_health() -> dict[str, Any]:
    try:
        with urlopen(OPENBAO_HEALTH_URL, timeout=5) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception as parse_exc:
            raise RecoveryError(f"OpenBao health returned HTTP {exc.code}") from parse_exc
    except (URLError, TimeoutError) as exc:
        raise RecoveryError("OpenBao health endpoint is unavailable") from exc


def wait_for_openbao(timeout_seconds: int = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = openbao_health()
            if last.get("initialized") is True:
                return last
        except RecoveryError:
            pass
        time.sleep(2)
    raise RecoveryError(f"OpenBao did not become initialized within {timeout_seconds}s")


def load_protected_unseal_shares() -> tuple[list[str], int]:
    if not INIT_FILE.is_file() or INIT_FILE.is_symlink():
        raise RecoveryError("protected OpenBao initialization artifact is missing or invalid")
    metadata = INIT_FILE.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid != 0 or metadata.st_gid != 0 or mode != 0o600:
        raise RecoveryError("protected OpenBao initialization artifact metadata is not root:root mode 0600")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(INIT_FILE, flags)
    try:
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise RecoveryError("protected OpenBao initialization artifact could not be parsed") from exc

    shares = data.get("unseal_keys_b64")
    threshold = data.get("unseal_threshold")
    declared = data.get("unseal_shares")
    if (
        not isinstance(shares, list)
        or not shares
        or not all(isinstance(value, str) and value.strip() for value in shares)
        or not isinstance(threshold, int)
        or threshold < 1
        or threshold > len(shares)
        or declared != len(shares)
    ):
        raise RecoveryError("protected OpenBao initialization artifact has invalid share metadata")
    return shares, threshold


def unseal_if_needed(health: dict[str, Any]) -> None:
    if health.get("sealed") is False:
        print("OPENBAO_UNSEAL=NOT_NEEDED")
        return
    shares, threshold = load_protected_unseal_shares()
    for index, share in enumerate(shares[:threshold], start=1):
        body = json.dumps({"key": share}).encode("utf-8")
        request = Request(
            OPENBAO_UNSEAL_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            raise RecoveryError(f"OpenBao rejected unseal share {index} with HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise RecoveryError(f"OpenBao unseal request {index} failed") from exc

        print(
            f"OPENBAO_UNSEAL_SHARE_{index}=ACCEPTED "
            f"progress={result.get('progress')} sealed={str(result.get('sealed')).lower()}"
        )
        if result.get("sealed") is False:
            print("OPENBAO_UNSEAL=PASS")
            return
    raise RecoveryError("OpenBao remained sealed after the configured threshold")


def staged_credentials_ready() -> bool:
    for path in STAGED_FILES:
        try:
            metadata = path.stat()
        except FileNotFoundError:
            return False
        if (
            not path.is_file()
            or path.is_symlink()
            or metadata.st_uid != 1000
            or metadata.st_gid != 1000
            or stat.S_IMODE(metadata.st_mode) != 0o400
            or metadata.st_size <= 0
        ):
            raise RecoveryError(f"runtime credential staging metadata is invalid: {path}")
    return True


def stage_runtime_credentials() -> None:
    if staged_credentials_ready():
        print("RUNTIME_CREDENTIAL_STAGING=ALREADY_READY")
        return
    if any(path.exists() for path in STAGED_FILES):
        raise RecoveryError("runtime credential staging is incomplete; refusing implicit replacement")
    if not STAGER.is_file():
        raise RecoveryError(f"credential staging tool is missing: {STAGER}")
    result = run([sys.executable, str(STAGER), "--stage"], quiet=True)
    require_ok(result, "provider runtime credential staging failed")
    if not staged_credentials_ready():
        raise RecoveryError("provider runtime credential staging did not produce the expected files")
    print("RUNTIME_CREDENTIAL_STAGING=PASS")


def wait_container_health(name: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = run(
            [
                "docker",
                "inspect",
                name,
                "--format",
                "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
            ]
        )
        if result.returncode == 0:
            state = (result.stdout or "").strip()
            if state == "running|healthy" or state == "running|none":
                print(f"{name.upper().replace('-', '_')}_HEALTH=PASS")
                return
        time.sleep(2)
    raise RecoveryError(f"{name} did not become healthy within {timeout_seconds}s")


def ensure_mcp() -> None:
    if not docker_exists(MCP_CONTAINER):
        raise RecoveryError(f"required container is missing: {MCP_CONTAINER}")
    require_ok(
        run(["docker", "update", "--restart", "unless-stopped", MCP_CONTAINER], quiet=True),
        "failed to set MCP restart policy",
    )
    docker_start(MCP_CONTAINER)
    deadline = time.monotonic() + 120
    probe = (
        "import urllib.request; "
        "r=urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3); "
        "assert r.status == 200"
    )
    while time.monotonic() < deadline:
        result = run(["docker", "exec", MCP_CONTAINER, "python", "-c", probe], quiet=True)
        if result.returncode == 0:
            print("JASON_MCP_PILOT_HEALTH=PASS")
            return
        time.sleep(2)
    raise RecoveryError("jason-mcp-pilot did not pass health verification")


def main() -> int:
    try:
        print("JASON_BOOT_RECOVERY=START")
        docker_start(OPENBAO_CONTAINER)
        health = wait_for_openbao()
        unseal_if_needed(health)
        final_health = openbao_health()
        if final_health.get("initialized") is not True or final_health.get("sealed") is not False:
            raise RecoveryError("OpenBao is not initialized and unsealed after recovery")
        print("OPENBAO_READY=PASS")

        stage_runtime_credentials()

        require_ok(
            run(["docker", "update", "--restart", "unless-stopped", RUNTIME_CONTAINER], quiet=True),
            "failed to set runtime restart policy",
        )
        docker_start(RUNTIME_CONTAINER)
        wait_container_health(RUNTIME_CONTAINER)
        ensure_mcp()

        for optional in ("jason-teams-gateway", "jason-ollama", "openclaw-openclaw-gateway-1"):
            if docker_exists(optional):
                run(["docker", "start", optional], quiet=True)

        print("JASON_BOOT_RECOVERY=PASS")
        return 0
    except Exception as exc:
        print(f"JASON_BOOT_RECOVERY=FAIL reason={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
