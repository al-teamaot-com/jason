#!/usr/bin/env python3
"""Recover the single-host Jason pilot after host/OpenBao restart.

This script is intentionally secret-safe:
- it never prints OpenBao unseal shares or provider AppRole values;
- it reads protected initialization material only when OpenBao is sealed;
- it stages only the existing governed runtime AppRole files;
- it fails closed on unexpected metadata or incomplete staging.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hmac
import importlib.util
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
CURRENT_ROOT = Path("/opt/jason/current")
STAGER = CURRENT_ROOT / "tools/stage_provider_read_runtime_credentials.py"
BOOTSTRAP_TO_STAGED = (
    (Path("/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/role-id"), Path("/run/jason-runtime-credentials/openbao/autotask/role_id")),
    (Path("/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/secret-id"), Path("/run/jason-runtime-credentials/openbao/autotask/secret_id")),
    (Path("/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/role-id"), Path("/run/jason-runtime-credentials/openbao/it-glue/role_id")),
    (Path("/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/secret-id"), Path("/run/jason-runtime-credentials/openbao/it-glue/secret_id")),
)
STAGED_FILES = (
    Path("/run/jason-runtime-credentials/openbao/autotask/role_id"),
    Path("/run/jason-runtime-credentials/openbao/autotask/secret_id"),
    Path("/run/jason-runtime-credentials/openbao/it-glue/role_id"),
    Path("/run/jason-runtime-credentials/openbao/it-glue/secret_id"),
)
RUNTIME_CONTAINER = "jason-runtime"
MCP_CONTAINER = "jason-mcp-pilot"
LEGACY_RELEASE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_RELEASE_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
COORDINATED_READBACK = Path("/etc/jason-owner-release/coordinated-readback/component.json")
HOST_GUARD = Path("/usr/local/lib/jason/scoped-backport/tools/pmv4_host_release_guard.py")
STAGED_ROOT = Path("/run/jason-runtime-credentials")
RUNTIME_SECRETS_ROOT = Path("/run/jason-secrets")


class RecoveryError(RuntimeError):
    pass


class RecoveryDeferred(RecoveryError):
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


def _read_private_bounded(path: Path, *, expected_uid: int, expected_mode: int) -> bytes:
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) != expected_mode
            or info.st_size <= 0 or info.st_size > 16384):
        raise RecoveryError(f"credential metadata is invalid: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
            raise RecoveryError(f"credential file changed during verification: {path}")
        value = os.read(fd, 16385)
    finally:
        os.close(fd)
    if not value or len(value) > 16384:
        raise RecoveryError(f"credential content length is invalid: {path}")
    return value


def staged_credentials_current() -> bool:
    """Compare protected sources to staged copies without printing or hashing values."""
    if not staged_credentials_ready():
        return False
    for source, staged in BOOTSTRAP_TO_STAGED:
        source_value = _read_private_bounded(source, expected_uid=0, expected_mode=0o600)
        staged_value = _read_private_bounded(staged, expected_uid=1000, expected_mode=0o400)
        if not hmac.compare_digest(source_value, staged_value):
            return False
    return True


@contextmanager
def runtime_recovery_transaction():
    """Serialize credential staging and same-ID recovery with release mutations."""
    if os.path.lexists(PMV4_RELEASE_LOCK) or os.path.lexists(COORDINATED_READBACK):
        for path in (HOST_GUARD, *HOST_GUARD.parents):
            info = path.lstat()
            if (path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022
                    or (path == HOST_GUARD and
                        (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
                    or (path != HOST_GUARD and not stat.S_ISDIR(info.st_mode))):
                raise RecoveryError("installed host release guard is untrusted")
        spec = importlib.util.spec_from_file_location("jason_boot_host_guard", HOST_GUARD)
        if spec is None or spec.loader is None:
            raise RecoveryError("installed host release guard is unavailable")
        guard_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard_module)
        entered = False
        try:
            with guard_module.IndependentHostGuard().host_release_transaction():
                entered = True
                yield
        except guard_module.HostGateDenied as exc:
            if not entered and str(exc) == "PMV4_HOST_TRANSACTION_BUSY":
                raise RecoveryDeferred("release transaction is active") from None
            raise
        return
    # Legacy single-host installations predate the independent PMv4 lock.
    # Do not create or replace a lock, and never fall back on a PMv4 host.
    fd = os.open(LEGACY_RELEASE_LOCK, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != 1000 or info.st_mode & 0o002):
            raise RecoveryError("legacy release transaction lock is untrusted")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryDeferred("release transaction is active") from None
        yield
    finally:
        os.close(fd)


def runtime_credential_destinations() -> dict[str, str]:
    return {str(path): str(RUNTIME_SECRETS_ROOT / path.relative_to(STAGED_ROOT))
            for path in STAGED_FILES}


def runtime_credential_identity(info: dict) -> tuple:
    """Validate the existing immutable identity and the exact four read-only binds."""
    identity = info.get("Id", "")
    image = info.get("Image", "")
    config = info.get("Config") or {}
    host = info.get("HostConfig") or {}
    revision = (config.get("Labels") or {}).get("com.teamaot.jason.source_revision", "")
    def hex_id(value, size):
        return isinstance(value, str) and len(value) == size and all(
            ch in "0123456789abcdef" for ch in value)
    if (info.get("Name") != "/" + RUNTIME_CONTAINER
            or not hex_id(identity, 64)
            or not isinstance(image, str) or not image.startswith("sha256:")
            or not hex_id(image[7:], 64)
            or not hex_id(revision, 40)
            or host.get("RestartPolicy", {}).get("Name") != "unless-stopped"):
        raise RecoveryError("unexpected runtime recovery identity or configuration")
    mounts = info.get("Mounts") or []
    for source, destination in runtime_credential_destinations().items():
        selected = [m for m in mounts if m.get("Source") == source
                    or m.get("Destination") == destination]
        if (len(selected) != 1 or selected[0].get("Source") != source
                or selected[0].get("Destination") != destination
                or selected[0].get("Type") != "bind" or selected[0].get("RW") is not False):
            raise RecoveryError("runtime credential mount topology is invalid")
    # In-memory equality only: never print, hash, or persist the configuration.
    ordered_mounts = sorted(mounts, key=lambda row: (str(row.get("Destination")), str(row.get("Source")), str(row.get("Type"))))
    return identity, image, config, host, ordered_mounts


def runtime_credential_mounts_current(identity: str) -> bool:
    """Compare mount metadata only; do not read or disclose credential values."""
    expected = []
    for source, destination in runtime_credential_destinations().items():
        info = os.lstat(source)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 1000
                or info.st_gid != 1000 or stat.S_IMODE(info.st_mode) != 0o400
                or not 0 < info.st_size <= 16384):
            raise RecoveryError("runtime credential mount source is invalid")
        expected.append([destination, info.st_dev, info.st_ino])
    probe = (
        "import json,os,stat,sys\n"
        "stale=False\n"
        "for path,dev,ino in json.loads(sys.argv[1]):\n"
        " s=os.lstat(path)\n"
        " if not stat.S_ISREG(s.st_mode) or s.st_uid!=1000 or s.st_gid!=1000 "
        "or stat.S_IMODE(s.st_mode)!=0o400: sys.exit(2)\n"
        " if (s.st_dev,s.st_ino)!=(dev,ino): stale=True\n"
        "sys.exit(42 if stale else 0)"
    )
    result = run(["docker", "exec", "--user", "1000:1000", identity,
                  "python", "-c", probe, json.dumps(expected)], quiet=True)
    if result.returncode == 42:
        return False
    require_ok(result, "runtime credential mount verification failed")
    return True


def ensure_runtime_credential_mounts() -> None:
    """Recover existing runtime only; never create, remove, or adopt a container."""
    before = inspect_container(RUNTIME_CONTAINER)
    baseline = runtime_credential_identity(before)
    identity = baseline[0]
    state = before.get("State", {}).get("Status")
    if state == "running":
        if not runtime_credential_mounts_current(identity):
            require_ok(run(["docker", "restart", identity], quiet=True),
                       "same-container runtime credential remount failed")
    elif state in ("exited", "created"):
        require_ok(run(["docker", "start", identity], quiet=True),
                   "existing runtime startup failed")
    else:
        raise RecoveryError("runtime is not in a recoverable state")
    wait_container_health(RUNTIME_CONTAINER)
    after = inspect_container(RUNTIME_CONTAINER)
    if runtime_credential_identity(after) != baseline:
        raise RecoveryError("runtime identity or configuration changed during recovery")
    if (after.get("State", {}).get("Status") != "running"
            or (after.get("State", {}).get("Health") or {}).get("Status") != "healthy"):
        raise RecoveryError("runtime did not become healthy after recovery")
    if not runtime_credential_mounts_current(identity):
        raise RecoveryError("runtime credential mount remains stale after recovery")
    print("RUNTIME_CREDENTIAL_REMOUNT=PASS")


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


def stage_runtime_credentials() -> bool:
    if staged_credentials_ready() and staged_credentials_current():
        print("RUNTIME_CREDENTIAL_STAGING=ALREADY_CURRENT")
        return False
    if not STAGER.is_file():
        raise RecoveryError(f"credential staging tool is missing: {STAGER}")
    replace = any(path.exists() for path in STAGED_FILES)
    args = [sys.executable, str(STAGER), "--stage"]
    if replace:
        args.append("--replace-existing")
    result = run(args, quiet=True)
    require_ok(result, "provider runtime credential staging failed")
    if not staged_credentials_ready() or not staged_credentials_current():
        raise RecoveryError("provider runtime credential staging did not converge to authoritative source")
    print("RUNTIME_CREDENTIAL_STAGING=" + ("REFRESHED" if replace else "PASS"))
    return True


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


def inspect_container(name: str) -> dict:
    result = run(["docker", "inspect", name])
    require_ok(result, f"required container inspection failed: {name}")
    objects = json.loads(result.stdout or "[]")
    if len(objects) != 1 or not isinstance(objects[0], dict):
        raise RecoveryError("invalid container inspection")
    return objects[0]


def ticket_hosting(info: dict) -> str:
    entries = info.get("Config", {}).get("Env") or []
    values = [item.split("=", 1)[1] for item in entries
              if item.startswith("JASON_TICKET_WORKER_HOSTING=")]
    if len(values) > 1:
        raise RecoveryError("ambiguous ticket-worker hosting")
    return values[0] if values else "embedded"


def recover_ticket_core(*,
                        transaction_lock: Path = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock"),
                        owner_lock: Path = Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3.owner.lock")) -> None:
    """Recover only the already approved external worker after the known boot failure."""
    import fcntl
    if ticket_hosting(inspect_container(RUNTIME_CONTAINER)) != "external":
        return
    name = "jason-pmv4-ticket-core"
    fd = os.open(transaction_lock, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("TICKET_CORE_RECOVERY=DEFERRED_PRODUCTION_TRANSACTION")
            return
        info = inspect_container(name)
        state = info["State"]
        identity = info["Id"]
        if (len(identity) != 64 or any(ch not in "0123456789abcdef" for ch in identity)
                or info.get("Name") != "/" + name
                or ticket_hosting(info) != "external"
                or info.get("Path") != "python"
                or info.get("Args") != ["-m", "jason_runtime.ticket_worker_service"]
                or not info.get("Config", {}).get("Healthcheck", {}).get("Test")
                or info.get("Config", {}).get("Healthcheck", {}).get("Test") == ["NONE"]
                or info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") != "unless-stopped"):
            raise RecoveryError("unexpected external ticket-core topology")
        if state.get("Status") == "running":
            wait_container_health(identity)
            return
        error = state.get("Error") or ""
        if (state.get("Status") != "exited" or state.get("ExitCode") != 127
                or "failed to fulfil mount request" not in error
                or "no such file or directory" not in error
                or not any(str(path) in error for path in STAGED_FILES)):
            raise RecoveryError("ticket core stopped outside known boot credential-mount failure")
        sources = [Path(m["Source"]) for m in info.get("Mounts", [])]
        if not sources or any(not p.is_absolute() or not p.exists() for p in sources):
            raise RecoveryError("ticket-core mount readiness failed")
        if not staged_credentials_ready() or not staged_credentials_current():
            raise RecoveryError("staged credentials not ready")
        lock_probe = (
            "import os,fcntl,sys; "
            "fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW); "
            "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); os.close(fd)"
        )
        require_ok(run(["runuser", "-u", "al", "--", "/usr/bin/python3", "-c",
                        lock_probe, str(owner_lock)]),
                   "external ticket-worker lock unavailable")
        require_ok(run(["docker", "start", identity], quiet=True),
                   "existing ticket-core boot recovery failed")
        wait_container_health(identity)
        if inspect_container(name).get("Id") != identity:
            raise RecoveryError("ticket-core identity changed during recovery")
        print("TICKET_CORE_BOOT_RECOVERY=PASS")
    finally:
        os.close(fd)


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

        with runtime_recovery_transaction():
            stage_runtime_credentials()
            # Check the actual bind in every cycle, even if staging was already
            # current (e.g. an interrupted previous recovery).
            ensure_runtime_credential_mounts()
        ensure_mcp()
        recover_ticket_core()

        for optional in ("jason-teams-gateway", "jason-ollama", "openclaw-openclaw-gateway-1"):
            if docker_exists(optional):
                run(["docker", "start", optional], quiet=True)

        print("JASON_BOOT_RECOVERY=PASS")
        return 0
    except RecoveryDeferred:
        print("JASON_BOOT_RECOVERY=DEFERRED_PRODUCTION_TRANSACTION")
        return 0
    except Exception as exc:
        print(f"JASON_BOOT_RECOVERY=FAIL reason={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
