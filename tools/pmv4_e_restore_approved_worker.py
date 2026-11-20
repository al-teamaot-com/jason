#!/usr/bin/env python3
"""Restore the one exact root worker from the approved Stage E before-image."""
from contextlib import ExitStack
from hashlib import sha256
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat

CANDIDATE = "f792abc67cfa38c85a44f33a54cef576f862b9fe"
STATE = Path("/usr/local/lib/jason/pmv4-e-bootstrap") / ("dispatch-install-" + CANDIDATE)
WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
BEFORE = "dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896"
INSTALLED = "60b0166a328fe32d1e8246b9279bfd22fcc083e3734b4f81315ab953ed83727a"
CATALOG = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
FREEZE_HASH = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
LOCKS = (
    (MANAGER / "production-transaction.lock", 1000, 0o664),
    (Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock"), 0, 0o600),
)


def need(ok, reason):
    if not ok:
        raise PermissionError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path, uid, mode):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid
             and (uid != 0 or meta.st_gid == 0)
             and meta.st_nlink == 1 and stat.S_IMODE(meta.st_mode) == mode
             and 0 < meta.st_size < 200_000, "UNTRUSTED_FILE:" + path.name)
        raw = stream.read(200_000)
        need(len(raw) == meta.st_size, "FILE_CHANGED:" + path.name)
        return raw


def restore():
    """Copy the approved backup, retaining the backup and install journal."""
    before = read(STATE / "worker-before.py", 0, 0o755)
    current = read(WORKER, 0, 0o755)
    need(digest(before) == BEFORE and digest(current) in (BEFORE, INSTALLED),
         "WORKER_BEFORE_IMAGE_OR_CURRENT_DIGEST_CHANGED")
    if current == before:
        return "PMV4_E_SHARED_WORKER=ALREADY_RESTORED"
    pending = STATE / "worker-approved-restore.py"
    if os.path.lexists(pending):
        need(read(pending, 0, 0o755) == before, "RESTORE_TEMPORARY_CHANGED")
    else:
        fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o755)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o755)
            stream.write(before)
            stream.flush()
            os.fsync(stream.fileno())
    need(read(WORKER, 0, 0o755) == current, "WORKER_CHANGED_BEFORE_RESTORE")
    os.replace(pending, WORKER)
    for folder in (STATE, WORKER.parent):
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    need(digest(read(WORKER, 0, 0o755)) == BEFORE, "RESTORE_READBACK_FAILED")
    return "PMV4_E_SHARED_WORKER=APPROVED_BEFORE_IMAGE_RESTORED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    need(os.geteuid() == 0, "LOCAL_ROOT_REQUIRED")
    need(STATE.resolve() == STATE and WORKER.parent.resolve() == WORKER.parent,
         "ROOT_PATH_CHANGED")
    accepted = json.loads(read(STATE / "accepted.json", 0, 0o400))
    scope = accepted.get("scope", {})
    need(accepted.get("status") == "installed"
         and accepted.get("owner_object_id")
         and scope.get("policy", {}).get("candidate_sha") == CANDIDATE
         and scope.get("worker_before_sha256") == BEFORE
         and scope.get("worker_after_sha256") == INSTALLED,
         "APPROVED_INSTALL_BEFORE_IMAGE_NOT_BOUND")
    policy = json.loads(read(CATALOG, 0, 0o600))
    need(policy.get("root_worker_sha256") == BEFORE,
         "CATALOG_PIN_DOES_NOT_MATCH_APPROVED_BEFORE_IMAGE")
    need(digest(read(MANAGER / "production-deployment-freeze", 1000, 0o600)) == FREEZE_HASH,
         "FREEZE_CHANGED")
    need(not os.path.lexists("/opt/jason/pmv4-e-trusted"),
         "NATIVE_STAGE_E_ALREADY_STARTED")
    records = Path("/var/lib/jason-owner-release/pmv4-e-dispatch")
    need(not any(records.iterdir()), "OWNER_REQUEST_ALREADY_DISPATCHED")
    with ExitStack() as locks:
        for path, uid, mode in LOCKS:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            locks.callback(os.close, fd)
            meta = os.fstat(fd)
            need(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid
                 and stat.S_IMODE(meta.st_mode) == mode and meta.st_nlink == 1,
                 "RELEASE_LOCK_CHANGED")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not any((MANAGER / "host-reconcile/requests").iterdir()),
             "ROOT_REQUEST_IN_PROGRESS")
        need(digest(read(WORKER, 0, 0o755)) in (BEFORE, INSTALLED),
             "LIVE_WORKER_CHANGED")
        need(digest(read(STATE / "worker-before.py", 0, 0o755)) == BEFORE,
             "APPROVED_BACKUP_CHANGED")
        if not args.apply:
            print("PMV4_E_SHARED_WORKER_RESTORE_PREFLIGHT=PASS")
            return
        print(restore())


if __name__ == "__main__":
    try:
        main()
    except (PermissionError, OSError, ValueError) as exc:
        raise SystemExit("DENIED:" + type(exc).__name__ + ":" + str(exc)[:140])
