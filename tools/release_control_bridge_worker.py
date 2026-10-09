#!/usr/bin/env python3
"""Root-owned read-only circuit-breaker snapshot publisher.

Never grants the unprivileged release process permission to modify the breaker.
"""
from __future__ import annotations

import json
import os
import pwd
import stat
import tempfile
from pathlib import Path

ROOT = Path("/var/lib/jason/openclaw/release-manager")
STATE = ROOT / "production-control-state.json"
DRIFT = ROOT / "production-drift.json"
SNAPSHOT = ROOT / "protected-readback"


def publish() -> None:
    if os.geteuid() != 0:
        raise PermissionError("root-only protected state publisher")
    owner = pwd.getpwnam("al")
    if ROOT.stat().st_uid != owner.pw_uid:
        raise PermissionError("unexpected release manager state root owner")
    SNAPSHOT.mkdir(mode=0o700, exist_ok=True)
    os.chown(SNAPSHOT, owner.pw_uid, owner.pw_gid)
    for source in (STATE, DRIFT):
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
                raise PermissionError("protected state is not root-owned mode 0600")
            with os.fdopen(fd, "r", closefd=False) as handle:
                payload = json.load(handle)
        finally:
            os.close(fd)
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise ValueError("invalid protected state schema")
        target = SNAPSHOT / source.name
        handle, name = tempfile.mkstemp(dir=SNAPSHOT, prefix=".publish-")
        try:
            with os.fdopen(handle, "w") as out:
                json.dump(payload, out, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.chown(name, owner.pw_uid, owner.pw_gid)
            os.chmod(name, 0o600)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)


if __name__ == "__main__":
    publish()
