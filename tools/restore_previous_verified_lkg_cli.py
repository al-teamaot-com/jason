#!/usr/bin/env python3
"""One-time, root-authenticated restoration of the already verified prior LKG.

This does not change the open breaker, production freeze, live service, or release
authorization. It restores the exact previous root-attested LKG only if the
current production manifest, CCC-only drift, and historic approved record match.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

import release_control_transition_worker as control

ROOT = Path("/var/lib/jason/openclaw/release-manager")
CONTROL = ROOT / "production-control-state.json"
DRIFT = ROOT / "production-drift.json"
FREEZE = ROOT / "production-deployment-freeze"
LOCK = ROOT / "protected-transitions/root-control.lock"
EXPECTED_REVISION = "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
EXPECTED_FAILED = "aa6fa38a29b803e11ada63afb3cf25d17b7daf44"


def secure_read(path: Path) -> tuple[dict, bytes]:
    st = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(st.st_mode)
            or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600):
        raise PermissionError("root-controlled evidence owner/mode invalid: " + path.name)
    content = path.read_bytes()
    return json.loads(content), content


def atomic_replace(path: Path, payload: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".verified-lkg-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, 0, 0)
        with os.fdopen(fd, "w") as out:
            json.dump(payload, out, sort_keys=True, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        parent = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def recover() -> None:
    if os.geteuid() != 0:
        raise PermissionError("local authenticated sudo root required")
    # Independent operator approval: this script is SHA-pinned and installed
    # locally as root before the action, and has no silent/remote trigger.
    with LOCK.open("a+") as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state, before_control = secure_read(CONTROL)
        drift, before_drift = secure_read(DRIFT)
        before_freeze = FREEZE.read_bytes()
        if not before_freeze:
            raise ValueError("production freeze is not present")
        if state.get("schema_version") != "1.0":
            raise ValueError("protected control schema invalid")
        if (state.get("last_known_good") or {}).get("manifest", {}).get("revision") != EXPECTED_FAILED:
            raise ValueError("current root LKG is not expected failed candidate")
        if (state.get("previous_last_known_good") or {}).get("manifest", {}).get("revision") != EXPECTED_REVISION:
            raise ValueError("previous root LKG is not expected live revision")
        request = {
            "action": "restore_previous_verified_lkg",
            "revision": EXPECTED_REVISION,
            "release_id": "release-" + EXPECTED_REVISION[:16],
        }
        # Use the source-reviewed independent root verification routine.
        updated = control.restore_previous_verified_lkg(request, state)
        if updated["circuit_breaker"]["state"] != "open":
            raise ValueError("circuit breaker changed unexpectedly")
        if (updated["last_known_good"]["manifest"]["revision"] != EXPECTED_REVISION
                or updated["previous_last_known_good"]["manifest"]["revision"] != EXPECTED_FAILED):
            raise ValueError("unexpected protected LKG restoration")
        # Detect concurrent changes before atomic replacement.
        if CONTROL.read_bytes() != before_control or DRIFT.read_bytes() != before_drift:
            raise RuntimeError("protected root evidence changed during verification")
        if FREEZE.read_bytes() != before_freeze:
            raise RuntimeError("production freeze changed during verification")
        atomic_replace(CONTROL, updated)
        readback, _ = secure_read(CONTROL)
        if readback != updated or FREEZE.read_bytes() != before_freeze:
            raise RuntimeError("protected post-write readback failed")
        print("PREVIOUS_IMMUTABLE_LKG_RESTORED=PASS")
        print("RESTORED_SHA=" + EXPECTED_REVISION)
        print("ROOT_CIRCUIT_BREAKER=OPEN_UNCHANGED")
        print("PRODUCTION_FREEZE_SHA256=" + hashlib.sha256(before_freeze).hexdigest())
        print("SERVICES_RESTARTED=NO")
        print("PRODUCTION_DEPLOYED=NO")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore-exact-previous-lkg", action="store_true", required=True)
    parser.parse_args()
    recover()
