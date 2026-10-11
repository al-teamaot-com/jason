#!/usr/bin/env python3
"""Root-owned worker for bounded Jason host release reconciliation."""

from __future__ import annotations

import grp
import json
import os
import pwd
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SPOOL = Path("/var/lib/jason/openclaw/release-manager/host-reconcile")
REQUESTS = SPOOL / "requests"
RESULTS = SPOOL / "results"
CANDIDATE_SCRIPTS = SPOOL / "candidate-scripts"
CURRENT = Path("/opt/jason/current")
REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
SHA = re.compile(r"^[0-9a-f]{40}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
MAX_REQUESTS_PER_RUN = 8
HOST_RECONCILE_TIMEOUT_SECONDS = 360


ROLLBACK_MANAGED_SYSTEM_UNITS = {
    "jason-production-drift-watchdog.service": "infrastructure/openclaw-operations/systemd/jason-production-drift-watchdog.service",
    "jason-production-drift-watchdog.timer": "infrastructure/openclaw-operations/systemd/jason-production-drift-watchdog.timer",
}


class HostReconcileError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_request(path: Path) -> dict[str, str]:
    expected_uid = pwd.getpwnam("al").pw_uid
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise HostReconcileError("request is not a regular file")
        if meta.st_uid != expected_uid:
            raise HostReconcileError("request owner is not the Jason host operator")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            payload = json.load(handle)
    finally:
        os.close(fd)

    request_id = str(payload.get("request_id") or "")
    source_revision = str(payload.get("source_revision") or "").casefold()
    if request_id != path.stem or not REQUEST_ID.fullmatch(request_id):
        raise HostReconcileError("request id is invalid")
    if not SHA.fullmatch(source_revision):
        raise HostReconcileError("source revision must be an exact SHA")
    return {"request_id": request_id, "source_revision": source_revision}


def _mcp_revision() -> str:
    value = subprocess.check_output(
        [
            "docker",
            "inspect",
            "jason-mcp-pilot",
            "--format",
            '{{index .Config.Labels "com.teamaot.jason.source_revision"}}',
        ],
        text=True,
    ).strip().casefold()
    if not SHA.fullmatch(value):
        raise HostReconcileError("live MCP revision is not an exact SHA")
    return value


def _git(*args: str) -> list[str]:
    return [
        "git",
        "-c",
        f"safe.directory={REPO}",
        "-C",
        str(REPO),
        *args,
    ]


def _verify_main(source_revision: str) -> None:
    # Network/source freshness belongs to the unprivileged Release Manager.
    # The root boundary deliberately performs only local immutable/ref checks
    # against the same managed Git source used by Release Manager, never a
    # mutable developer checkout.
    subprocess.run(
        _git("cat-file", "-e", f"{source_revision}^{{commit}}"),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    completed = subprocess.run(
        _git(
            "merge-base",
            "--is-ancestor",
            source_revision,
            "origin/main",
        ),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise HostReconcileError("requested host release is not on protected origin/main")




def _candidate_reconcile_script(source_revision: str) -> Path:
    """Materialize the exact candidate reconciliation script from protected Git evidence."""
    CANDIDATE_SCRIPTS.mkdir(parents=True, exist_ok=True)
    try:
        body = subprocess.check_output(
            _git("show", f"{source_revision}:tools/reconcile_production_host_services.sh"),
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HostReconcileError(
            "candidate host reconciliation script is not materializable from protected source"
        ) from exc
    developer_checkout = "/home/al/projects" + "/jason"
    if developer_checkout in body:
        raise HostReconcileError(
            "candidate host reconciliation script depends on developer checkout"
        )
    required = (
        'REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"',
        'DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"',
        'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT',
        'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=',
    )
    missing = [item for item in required if item not in body]
    if missing:
        raise HostReconcileError(
            "candidate host reconciliation contract is incomplete: " + ",".join(missing)
        )
    target = CANDIDATE_SCRIPTS / f"reconcile-{source_revision}.sh"
    temp = target.with_suffix(".sh.tmp")
    temp.write_text(body, encoding="utf-8")
    os.chown(temp, 0, 0)
    os.chmod(temp, 0o700)
    os.replace(temp, target)
    return target




def _target_contains_path(source_revision: str, relative_path: str) -> bool:
    completed = subprocess.run(
        _git("cat-file", "-e", f"{source_revision}:{relative_path}"),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _reconcile_release_specific_system_units(source_revision: str) -> list[str]:
    """Remove newer release-owned units that do not exist in the rollback release."""
    removed: list[str] = []
    for unit, relative_path in ROLLBACK_MANAGED_SYSTEM_UNITS.items():
        if _target_contains_path(source_revision, relative_path):
            continue
        subprocess.run(
            ["systemctl", "disable", "--now", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for path in (
            Path("/etc/systemd/system") / unit,
            Path("/etc/systemd/system/timers.target.wants") / unit,
            Path("/etc/systemd/system/multi-user.target.wants") / unit,
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        removed.append(unit)
    if removed:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "reset-failed"], check=False)
    return removed


def _historical_post_success_documentation_failure(detail: str, source_revision: str) -> bool:
    """Accept only an old-script documentation-publication failure after critical alignment."""
    required = (
        "JASON_USER_WORKER_RECONCILIATION=PASS",
        "JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS",
        "JASON_HOST_SERVICE_RECONCILIATION=PASS",
        "MANAGED_ENGINEERING_SOURCE=PASS",
        "MANAGED_DOCUMENTATION_SOURCE=PASS",
        f"HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION={source_revision}",
        "ERROR: production succeeded but documentation reconciliation publication failed",
    )
    return all(marker in detail for marker in required)

def _write_result(
    request_id: str,
    source_revision: str,
    *,
    success: bool,
    detail: str,
) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "request_id": request_id,
        "source_revision": source_revision,
        "success": bool(success),
        "detail": detail[-4000:],
        "completed_at": now(),
    }
    target = RESULTS / f"{request_id}.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o640)
    gid = grp.getgrnam("jason").gr_gid
    os.chown(temp, 0, gid)
    os.replace(temp, target)


def _process(path: Path) -> None:
    request_id = path.stem
    source_revision = ""
    try:
        request = _read_request(path)
        request_id = request["request_id"]
        source_revision = request["source_revision"]
        _verify_main(source_revision)

        live_mcp = _mcp_revision()
        if live_mcp != source_revision:
            raise HostReconcileError(
                "live MCP revision does not match requested host release"
            )

        script = _candidate_reconcile_script(source_revision)
        if not script.is_file():
            raise HostReconcileError("candidate host reconciliation script is missing")

        release_dir = Path("/opt/jason/releases") / source_revision
        if release_dir.exists():
            meta = release_dir.lstat()
            if release_dir.is_symlink() or not stat.S_ISDIR(meta.st_mode):
                raise HostReconcileError(
                    "target immutable release path is not a real directory"
                )
            if meta.st_uid != 0:
                raise HostReconcileError(
                    "target immutable release directory is not root-owned"
                )
            os.chmod(release_dir, 0o755)

        script_env = os.environ.copy()
        script_env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "safe.directory",
                "GIT_CONFIG_VALUE_0": str(REPO),
            }
        )
        previous_umask = os.umask(0o022)
        try:
            completed = subprocess.run(
                [str(script), source_revision],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=HOST_RECONCILE_TIMEOUT_SECONDS,
                env=script_env,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            detail = str(output).strip()
            raise HostReconcileError(
                f"candidate host reconciliation script exceeded {HOST_RECONCILE_TIMEOUT_SECONDS}s"
                + (": " + detail[-3000:] if detail else "")
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = str(exc.stdout or "").strip()
            if _historical_post_success_documentation_failure(detail, source_revision):
                completed = subprocess.CompletedProcess(
                    args=[str(script), source_revision],
                    returncode=0,
                    stdout=(
                        detail
                        + "\nHISTORICAL_POST_SUCCESS_DOCUMENTATION_FAILURE=DEFERRED_TO_RELEASE_MANAGER"
                    ),
                )
            else:
                raise HostReconcileError(
                    "candidate host reconciliation script failed"
                    + (": " + detail[-3000:] if detail else "")
                ) from exc
        finally:
            os.umask(previous_umask)

        removed_units = _reconcile_release_specific_system_units(source_revision)
        if removed_units:
            completed = subprocess.CompletedProcess(
                args=completed.args,
                returncode=completed.returncode,
                stdout=(
                    str(completed.stdout or "")
                    + "\nJASON_RELEASE_SPECIFIC_UNIT_CLEANUP=PASS removed="
                    + ",".join(sorted(removed_units))
                ),
            )

        release_meta = release_dir.stat()
        if release_meta.st_uid != 0 or (release_meta.st_mode & 0o055) != 0o055:
            raise HostReconcileError(
                "immutable release directory is not safely traversable"
            )
        resolved = CURRENT.resolve().name.casefold()
        if resolved != source_revision:
            raise HostReconcileError(
                "immutable host release did not resolve to requested revision"
            )
        _write_result(
            request_id,
            source_revision,
            success=True,
            detail=completed.stdout,
        )
    except Exception as exc:
        _write_result(
            request_id,
            source_revision,
            success=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("release host reconciliation worker must run as root")
    REQUESTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    paths = sorted(
        (
            path
            for path in REQUESTS.iterdir()
            if path.is_file() and path.suffix == ".json"
        ),
        key=lambda item: item.stat().st_mtime,
    )[:MAX_REQUESTS_PER_RUN]
    for path in paths:
        _process(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
