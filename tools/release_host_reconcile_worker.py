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
CURRENT = Path("/opt/jason/current")
REPO = Path("/home/al/projects/jason")
SHA = re.compile(r"^[0-9a-f]{40}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
MAX_REQUESTS_PER_RUN = 8


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


def _verify_main(source_revision: str) -> None:
    subprocess.run(
        ["git", "-C", str(REPO), "fetch", "--no-tags", "origin", "main"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{source_revision}^{{commit}}"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "merge-base",
            "--is-ancestor",
            source_revision,
            "origin/main",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        raise HostReconcileError("requested host release is not on protected origin/main")


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

        script = CURRENT / "tools" / "reconcile_production_host_services.sh"
        if not script.is_file():
            raise HostReconcileError("immutable host reconciliation script is missing")

        completed = subprocess.run(
            [str(script), source_revision],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=240,
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
