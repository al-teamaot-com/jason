#!/usr/bin/env python3
"""Fail-closed, root-owned crash recovery for scoped-backport promotion.

SOURCE ONLY; cannot run from a mutable checkout. The systemd timer only
reconciles incomplete root journals. It never promotes, creates provider
objects, signs an Owner release, closes a breaker, or reuses approval proof.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import sys
from typing import Mapping

INSTALLED_ROOT = Path("/usr/local/lib/jason/scoped-backport")
INSTALLED_RECOVERY = INSTALLED_ROOT / "tools/scoped_backport_native_recovery.py"
if os.geteuid() == 0 and Path(__file__).resolve() == INSTALLED_RECOVERY:
    sys.path.insert(0, str(INSTALLED_ROOT))

from tools.scoped_backport_native_host import (
    NativeScopedBackportHost, ROOT_STATE, FREEZE, root_json, root_directory,
    utcnow, inspect, source,
)
from tools.scoped_backport_release import (
    validate_offer, ScopedBackportDenied, deny,
)

RESOLVED = {
    "production_pair_verified",
    "rollback_verified",
    "failed_before_mutation",
}
ROOT_NAME = "tools/scoped_backport_native_recovery.py"


def _restore_frozen_backup(host: NativeScopedBackportHost,
                           offer: Mapping) -> None:
    if FREEZE.exists():
        host._frozen(offer)
        return
    backup = root_json(host.root / "freeze-backups" /
                       (offer["release_id"] + ".json"), max_size=8192)
    if (backup.get("schema_version") != "1.0"
            or backup.get("release_id") != offer["release_id"]
            or backup.get("freeze_sha256") != offer["freeze_sha256"]
            or backup.get("mode") != 0o600
            or not isinstance(backup.get("raw_utf8"), str)):
        deny("CRASH_FREEZE_BACKUP_SCOPE_MISMATCH")
    parent = FREEZE.parent
    user = __import__("pwd").getpwnam("al")
    if (parent.is_symlink() or parent.stat().st_uid != user.pw_uid
            or stat.S_IMODE(parent.stat().st_mode) != 0o700):
        deny("CRASH_FREEZE_PARENT_UNTRUSTED")
    from hashlib import sha256
    raw = backup["raw_utf8"].encode()
    if sha256(raw).hexdigest() != offer["freeze_sha256"]:
        deny("CRASH_FREEZE_BACKUP_HASH_MISMATCH")
    # Caller is already an exact installed root timer under native release lock.
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=".scoped-crash-refreeze-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, backup["uid"], backup["gid"])
        os.chmod(temporary, backup["mode"])
        os.replace(temporary, FREEZE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    host._frozen(offer)


def reconcile_one(host: NativeScopedBackportHost, offer: Mapping,
                  journal: Mapping) -> dict:
    o = validate_offer(offer)
    if (journal.get("release_id") != o["release_id"]
            or journal.get("candidate_sha") != o["candidate_sha"]
            or journal.get("rollback_sha") != o["rollback_sha"]
            or journal.get("scope_sha256") != o["scope_sha256"]
            or journal.get("manifest_sha256") != o["manifest_sha256"]):
        deny("RECOVERY_JOURNAL_OFFER_MISMATCH")
    if journal.get("outcome") in RESOLVED:
        return {"status": "resolved_prior_attempt_no_action",
                "release_id": o["release_id"]}
    protected = journal.get("protected_before")
    if not isinstance(protected, dict) or set(protected) != set(o["protected_services"]):
        deny("RECOVERY_PROTECTED_SNAPSHOT_MISSING")
    host.active_offer = o
    with host.release_lock(o):
        # Incomplete production mutation is an emergency hold, not a fresh
        # release authorization. Never try to re-promote either candidate.
        host.open_breaker("SCOPED_BACKPORT_INTERRUPTED_TRANSACTION")
        host.restore_pair_exact(o)
        host.verify_rollback(o)
        host.verify_protected_unchanged(protected)
        _restore_frozen_backup(host, o)
        host._journal_update(o, "interrupted_rollback_verified",
                             outcome="rollback_verified",
                             recovered_at=utcnow(),
                             breaker_remains_open=True)
        return {"status": "interrupted_rollback_verified_breaker_open",
                "release_id": o["release_id"]}


def reconcile_all() -> dict:
    if (os.geteuid() != 0 or not sys.flags.isolated or
            Path(__file__).resolve(strict=True) != INSTALLED_RECOVERY):
        deny("INSTALLED_ROOT_RECOVERY_TIMER_REQUIRED")
    host = NativeScopedBackportHost()
    host.enforce_installed_root_trust()
    journal_dir = host.root / "transactions"
    root_directory(journal_dir)
    journals = sorted(journal_dir.glob("release-*.json"))
    if len(journals) > 20:
        deny("EXCESS_INCOMPLETE_RELEASE_JOURNALS")
    resolved = []
    for path in journals:
        if path.is_symlink() or not path.is_file():
            deny("RECOVERY_JOURNAL_PATH_UNTRUSTED")
        journal = root_json(path, max_size=32768)
        release_id = journal.get("release_id")
        if path.name != release_id + ".json":
            deny("RECOVERY_JOURNAL_NAME_MISMATCH")
        scope_file = host.root / "offers" / (release_id + ".json")
        stage = root_json(scope_file, max_size=32768)
        offer = stage.get("source_offer")
        if not isinstance(offer, dict):
            deny("RECOVERY_ROOT_OFFER_MISSING")
        outcome = reconcile_one(host, offer, journal)
        resolved.append(outcome)
    return {
        "status": "recovery_scan_completed",
        "checked": len(journals), "results": resolved,
        "provider_writes": False, "production_promotions": False,
    }


def main() -> int:
    report = reconcile_all()
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
