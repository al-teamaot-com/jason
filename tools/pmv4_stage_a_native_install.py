"""Native root Stage A0 installer transaction with an exact audit journal.

This module is a LIBRARY ONLY. There is no runnable production apply CLI.
The existing root reconcile service must invoke it from root-installed trusted
code, after separate exact Owner consent and native protected-main CI.
No signer material is read, created, copied, or rotated.

A0 is create-only in a previously empty namespace. A crash before commit
can be recovered by EXACT, journal-verified rollback to the absence baseline.
If any object has drifted, refuse recovery rather than remove foreign data.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable, Iterator, Mapping

from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a_admission as admission
from tools.pmv4_host_release_guard import OLD_RELEASE_LOCK, LEGACY_MANAGER_UID

JOURNAL_ROOT = Path(
    "/var/lib/jason/openclaw/release-manager/protected-transitions"
)


class StageANativeDenied(PermissionError):
    pass


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def _fsync_directory(parent: Path) -> None:
    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _require_secure_regular(path: Path, uid: int, mode: int) -> None:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise StageANativeDenied("STAGE_A_NATIVE_FILE_UNAVAILABLE") from exc
    if (path.is_symlink() or not stat.S_ISREG(meta.st_mode)
            or meta.st_nlink != 1 or meta.st_uid != uid
            or stat.S_IMODE(meta.st_mode) != mode):
        raise StageANativeDenied("STAGE_A_NATIVE_FILE_UNTRUSTED")


def _journal_path(candidate_sha: str, *, sandbox: Path | None) -> Path:
    packet._require_sha(candidate_sha)
    if sandbox is None:
        return JOURNAL_ROOT / ("pmv4-stage-a0-" + candidate_sha + ".jsonl")
    if not sandbox.is_absolute() or not sandbox.is_dir() or sandbox.is_symlink():
        raise StageANativeDenied("STAGE_A_SANDBOX_UNTRUSTED")
    if Path("/tmp") not in sandbox.parents or sandbox.resolve() != sandbox:
        raise StageANativeDenied("STAGE_A_SANDBOX_PRODUCTION_DENIED")
    return sandbox / ("pmv4-stage-a0-" + candidate_sha + ".jsonl")


class NativeStageAInstaller:
    """Exact install/rollback; production uses fixed absolute paths only.

    Disposable CI may pass a private /tmp sandbox as a path mapper. Such a
    sandbox is never accepted for production mode.
    """

    def __init__(
        self, *, production: bool = True, sandbox: Path | None = None,
        old_lock: Path = OLD_RELEASE_LOCK, owner_metadata: bool = False,
        root_health: Callable[[], Mapping[str, Any]] | None = None,
        at: datetime | None = None,
    ):
        if production and (
            sandbox is not None or Path(old_lock) != OLD_RELEASE_LOCK
            or os.geteuid() != 0 or owner_metadata is False
        ):
            raise StageANativeDenied("STAGE_A_PRODUCTION_ROOT_BOUNDARY_REQUIRED")
        if not production:
            if sandbox is None or not sandbox.is_dir() or sandbox.is_symlink():
                raise StageANativeDenied("STAGE_A_TEST_SANDBOX_REQUIRED")
            if not str(sandbox).startswith("/tmp/"):
                raise StageANativeDenied("STAGE_A_TEST_OUTSIDE_TEMP_DENIED")
        self.production = production
        self.sandbox = sandbox
        self.old_lock = Path(old_lock)
        self.owner_metadata = owner_metadata
        self.root_health = root_health
        if production and at is not None:
            raise StageANativeDenied("STAGE_A_PRODUCTION_CLOCK_OVERRIDE")
        self.at = at
        self._held = False
        self._new_fd: int | None = None

    def _map(self, absolute: str) -> Path:
        if not absolute.startswith("/"):
            raise StageANativeDenied("STAGE_A_PATH_NOT_ABSOLUTE")
        if not any(absolute == prefix or absolute.startswith(prefix + "/")
                   for prefix in (packet.HOST_CODE, packet.ROOT, packet.ETC)):
            raise StageANativeDenied("STAGE_A_PATH_NOT_ALLOWLISTED")
        if self.production:
            return Path(absolute)
        assert self.sandbox is not None
        target = self.sandbox / absolute.lstrip("/")
        ancestor = target.parent
        while ancestor != self.sandbox:
            if ancestor.is_symlink() or self.sandbox not in ancestor.parents:
                raise StageANativeDenied("STAGE_A_PATH_TRAVERSAL")
            ancestor = ancestor.parent
        return target

    def _journal(self, sha: str) -> Path:
        return _journal_path(sha, sandbox=self.sandbox)

    @contextmanager
    def _legacy_lock(self) -> Iterator[None]:
        if self._held:
            raise StageANativeDenied("STAGE_A_NESTED_LOCK")
        _require_secure_regular(
            self.old_lock,
            LEGACY_MANAGER_UID if self.production else os.geteuid(),
            0o664 if self.production else 0o600,
        )
        fd = os.open(self.old_lock, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StageANativeDenied("STAGE_A_SHARED_RELEASE_LOCK_BUSY") from exc
            self._held = True
            yield
        finally:
            self._held = False
            if self._new_fd is not None:
                os.close(self._new_fd)
                self._new_fd = None
            os.close(fd)

    def _trusted_journal_parent(self) -> None:
        j = self._journal("0" * 40).parent
        info = j.lstat()
        if (not stat.S_ISDIR(info.st_mode) or j.is_symlink()
                or info.st_mode & 0o022):
            raise StageANativeDenied("STAGE_A_JOURNAL_PARENT_UNTRUSTED")
        if self.production and info.st_uid != 0:
            raise StageANativeDenied("STAGE_A_JOURNAL_PARENT_NOT_ROOT_OWNED")

    def _append(self, journal: Path, event: str, binding: Mapping[str, Any]) -> None:
        # Append-only chained audit. An interrupted/truncated record fails
        # closed instead of accepting a forged "completed" checkpoint.
        rows = self._events(journal) if journal.exists() else []
        previous = rows[-1]["hash"] if rows else "0" * 64
        payload = {
            "version": 1, "seq": len(rows) + 1, "event": event,
            "source_sha": binding["source_sha"],
            "scope_sha256": binding["scope_sha256"],
            "owner_approval_id": binding["owner_approval_id"],
            "manifest_sha256": binding["manifest_sha256"],
            "freeze_sha256": binding["freeze_sha256"],
            "signed_proof_sha256": binding["signed_proof_sha256"],
            "prev_sha256": previous,
        }
        payload["hash"] = _hash(_canonical(payload))
        encoded = _canonical(payload) + b"\n"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(journal, flags, 0o600)
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                    or meta.st_uid != os.geteuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600):
                raise StageANativeDenied("STAGE_A_JOURNAL_TAMPERED")
            if os.write(fd, encoded) != len(encoded):
                raise StageANativeDenied("STAGE_A_JOURNAL_PARTIAL_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(journal.parent)

    def _events(self, journal: Path) -> list[dict[str, Any]]:
        if not journal.exists():
            return []
        _require_secure_regular(journal, os.geteuid(), 0o600)
        raw = journal.read_bytes()
        if len(raw) > 512 * 1024 or not raw.endswith(b"\n"):
            raise StageANativeDenied("STAGE_A_JOURNAL_TRUNCATED")
        previous = "0" * 64
        rows = []
        for line in raw.splitlines():
            try:
                data = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise StageANativeDenied("STAGE_A_JOURNAL_INVALID") from exc
            if (not isinstance(data, dict)
                    or set(data) != {"version", "seq", "event", "source_sha",
                                        "scope_sha256", "owner_approval_id",
                                        "manifest_sha256", "freeze_sha256",
                                        "signed_proof_sha256", "prev_sha256", "hash"}
                    or data["version"] != 1
                    or data["seq"] != len(rows) + 1
                    or data["prev_sha256"] != previous
                    or data["hash"] != _hash(_canonical({
                        k:v for k,v in data.items() if k != "hash"
                    }))):
                raise StageANativeDenied("STAGE_A_JOURNAL_CHAIN_INVALID")
            previous = data["hash"]
            rows.append(data)
        return rows

    def _expected_paths(self, scope: Mapping[str, Any]) -> list[str]:
        return ([item["path"] for item in scope["directories"]]
                + [item["path"] for item in scope["files"]]
                + [item["path"] for item in scope["symlinks"]])

    def _assert_parents(self) -> None:
        # Production-owned ancestors; do not replace or chmod them.
        # /var/lib/jason is intentionally UID1000 (operator-owned), not
        # world-writable. /etc/jason is 0700 root-owned.
        for path in ("/usr/local/lib/jason", "/var/lib/jason", "/etc/jason"):
            if not self.production:
                continue
            obj = Path(path)
            info = obj.lstat()
            if (obj.is_symlink() or not stat.S_ISDIR(info.st_mode)
                    or info.st_mode & 0o002):
                raise StageANativeDenied("STAGE_A_PARENT_UNTRUSTED")
            if path != "/var/lib/jason" and info.st_uid != 0:
                raise StageANativeDenied("STAGE_A_PARENT_OWNER_MISMATCH")
            if path == "/var/lib/jason" and info.st_uid != 1000:
                raise StageANativeDenied("STAGE_A_OPERATOR_PARENT_MISMATCH")

    def _source_file(self, repo: Path, row: Mapping[str, Any]) -> bytes:
        if row["source"] == "constant":
            return packet.STATIC_DOCS[row["path"]][0]
        src = repo / row["source"]
        if src.is_symlink() or not src.is_file():
            raise StageANativeDenied("STAGE_A_SOURCE_FILE_MISSING")
        value = src.read_bytes()
        if _hash(value) != row["sha256"]:
            raise StageANativeDenied("STAGE_A_SOURCE_CONTENT_CHANGED")
        return value

    def _verify_objects(self, scope: Mapping[str, Any], *,
                        partial: bool) -> None:
        wanted = set(self._expected_paths(scope))
        for row in scope["directories"]:
            path = self._map(row["path"])
            if path.exists():
                meta = path.lstat()
                if (path.is_symlink() or not stat.S_ISDIR(meta.st_mode)
                        or stat.S_IMODE(meta.st_mode) != int(row["mode"], 8)
                        or (self.owner_metadata and
                            (meta.st_uid, meta.st_gid) != (row["uid"], row["gid"]))):
                    raise StageANativeDenied("STAGE_A_DIRECTORY_DRIFT")
            elif not partial:
                raise StageANativeDenied("STAGE_A_DIRECTORY_ABSENT")
        for row in scope["files"]:
            path = self._map(row["path"])
            if path.exists():
                meta = path.lstat()
                if (path.is_symlink() or not stat.S_ISREG(meta.st_mode)
                        or meta.st_nlink != 1
                        or stat.S_IMODE(meta.st_mode) != int(row["mode"], 8)
                        or (self.owner_metadata and
                            (meta.st_uid, meta.st_gid) != (row["uid"], row["gid"]))
                        or _hash(path.read_bytes()) != row["sha256"]):
                    raise StageANativeDenied("STAGE_A_FILE_DRIFT")
            elif not partial:
                raise StageANativeDenied("STAGE_A_FILE_ABSENT")
        for row in scope["symlinks"]:
            path = self._map(row["path"])
            if path.is_symlink():
                if os.readlink(path) != row["target"]:
                    raise StageANativeDenied("STAGE_A_POINTER_DRIFT")
            elif path.exists() or not partial:
                raise StageANativeDenied("STAGE_A_POINTER_ABSENT")
        for base in (packet.ROOT, packet.HOST_CODE, packet.ETC):
            path = self._map(base)
            if path.is_symlink():
                raise StageANativeDenied("STAGE_A_TARGET_SYMLINK")
            if path.exists():
                for sub in [path, *path.rglob("*")]:
                    absolute = "/" + str(sub.relative_to(self.sandbox)
                                          if self.sandbox else sub).lstrip("/")
                    if absolute not in wanted:
                        raise StageANativeDenied("STAGE_A_UNDECLARED_OBJECT")

    def _create(self, repo: Path, scope: Mapping[str, Any],
                journal: Path, binding: Mapping[str, Any],
                after_step: Callable[[str], None] | None) -> None:
        for row in scope["directories"]:
            path = self._map(row["path"])
            if not path.exists():
                self._append(journal, "intent_dir:" + row["path"], binding)
                path.mkdir(mode=int(row["mode"], 8))
                if self.owner_metadata:
                    os.chown(path, row["uid"], row["gid"])
                os.chmod(path, int(row["mode"], 8))
                _fsync_directory(path.parent)
            else:
                self._verify_objects(scope, partial=True)
            self._append(journal, "done_dir:" + row["path"], binding)
            if after_step is not None: after_step("dir:" + row["path"])
        for row in scope["files"]:
            path = self._map(row["path"])
            if not path.exists():
                self._append(journal, "intent_file:" + row["path"], binding)
                data = self._source_file(repo, row)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o600)
                try:
                    with os.fdopen(fd, "wb", closefd=False) as output:
                        output.write(data)
                        output.flush()
                        if self.owner_metadata:
                            os.fchown(fd, row["uid"], row["gid"])
                        os.fchmod(fd, int(row["mode"], 8))
                        os.fsync(fd)
                finally:
                    os.close(fd)
                _fsync_directory(path.parent)
            else:
                self._verify_objects(scope, partial=True)
            if row["path"] == packet.ROOT + "/control/host-mutation.lock":
                self._assert_new_lock(scope)
            self._append(journal, "done_file:" + row["path"], binding)
            if after_step is not None: after_step("file:" + row["path"])
        for row in scope["symlinks"]:
            path = self._map(row["path"])
            if not path.is_symlink():
                self._append(journal, "intent_link:" + row["path"], binding)
                path.symlink_to(row["target"])
                _fsync_directory(path.parent)
            else:
                self._verify_objects(scope, partial=True)
            self._append(journal, "done_link:" + row["path"], binding)
            if after_step is not None: after_step("link:" + row["path"])

    def _assert_new_lock(self, scope: Mapping[str, Any]) -> None:
        lock = self._map(packet.ROOT + "/control/host-mutation.lock")
        expected_uid = 0 if self.production else os.geteuid()
        _require_secure_regular(lock, expected_uid, 0o600)
        if self._new_fd is None:
            self._new_fd = os.open(lock, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                fcntl.flock(self._new_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(self._new_fd)
                self._new_fd = None
                raise StageANativeDenied("STAGE_A_NEW_ROOT_LOCK_BUSY") from exc

    def install(
        self, *, repo: Path, candidate_sha: str, scope: Mapping[str, Any],
        manifest: Mapping[str, Any], signed_proof: Mapping[str, Any],
        freeze_path: Path, ci_check: Callable[[str], bool],
        approval_public_key: Any = None,
        after_step: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """One bounded exact transaction, never public ungoverned apply."""
        if self.production and approval_public_key is not None:
            raise StageANativeDenied("STAGE_A_UNPINNED_PUBLIC_KEY_DENIED")
        if self.production and (self.root_health is None
                                or Path(freeze_path) != packet.FREEZE):
            raise StageANativeDenied("STAGE_A_NATIVE_ROOT_EVIDENCE_REQUIRED")
        if not callable(self.root_health):
            raise StageANativeDenied("STAGE_A_NATIVE_ROOT_HEALTH_UNAVAILABLE")
        self._trusted_journal_parent()
        with self._legacy_lock():
            self._assert_parents()
            observed_health = dict(self.root_health())
            proof = admission.verify_admission(
                repo=repo, candidate_sha=candidate_sha,
                reviewed_scope=scope, exact_manifest=manifest,
                signed_owner_proof=signed_proof, frozen_marker=freeze_path,
                confirmed_root_health=observed_health,
                protected_main_ci_check=ci_check,
                at=self.at or datetime.now(timezone.utc),
                production=self.production, test_public_key=approval_public_key,
            )
            if scope["candidate_sha"] != candidate_sha:
                raise StageANativeDenied("STAGE_A_SOURCE_NOT_PINNED")
            journal = self._journal(candidate_sha)
            if journal.exists() or journal.is_symlink():
                raise StageANativeDenied("STAGE_A_EXISTING_JOURNAL_NEEDS_RECOVERY")
            if any(self._map(name).exists() or self._map(name).is_symlink()
                   for name in (packet.ROOT, packet.HOST_CODE, packet.ETC)):
                raise StageANativeDenied("STAGE_A_ABSENCE_BASELINE_CHANGED")
            binding = {
                "source_sha": candidate_sha,
                "scope_sha256": scope["scope_sha256"],
                "owner_approval_id": proof["owner_approval_id"],
                "manifest_sha256": proof["exact_manifest_sha256"],
                "freeze_sha256": manifest["freeze_sha256"],
                "signed_proof_sha256": _hash(_canonical(signed_proof)),
            }
            self._append(journal, "prepared", binding)
            # All create steps have a durable preceding intent. A torn
            # file/foreign entry is quarantined, never recursively erased.
            self._create(repo, scope, journal, binding, after_step)
            self._verify_objects(scope, partial=False)
            self._assert_new_lock(scope)
            # The signed freeze fingerprint and previously observed root
            # source must remain unchanged during this create-only A0
            # transaction. Do not treat the successful file copy as health.
            if _hash(freeze_path.read_bytes()) != manifest["freeze_sha256"]:
                raise StageANativeDenied("STAGE_A_FREEZE_CHANGED_DURING_INSTALL")
            if self.production:
                from tools.pmv4_host_release_guard import IndependentHostGuard
                checked = IndependentHostGuard()
                if checked.protected_release_status().get("ready") is not True:
                    raise StageANativeDenied("STAGE_A_POST_INSTALL_ROOT_BREAKER_OPEN")
                core = checked.core_health_evidence()
                if (core.get("runtime_healthy") is not True
                        or core.get("mcp_running") is not True
                        or core.get("worker_scan_fresh") is not True):
                    raise StageANativeDenied("STAGE_A_POST_INSTALL_CORE_UNHEALTHY")
                if _hash(packet.HOLD.read_bytes()) != observed_health.get(
                    "promotion_hold_sha256"
                ):
                    raise StageANativeDenied("STAGE_A_PROMOTION_HOLD_CHANGED")
            self._append(journal, "verified_installed", binding)
            return {
                "status": "installed",
                "source_sha": candidate_sha,
                "scope_sha256": scope["scope_sha256"],
                "rollback_sha": packet.EMPTY_BASELINE,
                "owner_approval_id": proof["owner_approval_id"],
                "audit_chain_sha256": self._events(journal)[-1]["hash"],
                "production_mutation": self.production,
            }

    def recover_empty(self, *, scope: Mapping[str, Any],
                      confirmed_approval_id: str,
                      confirmed_proof_sha256: str) -> dict[str, Any]:
        """Rollback failed/incomplete exact A0 to absence without new release."""
        journal = self._journal(scope["candidate_sha"])
        with self._legacy_lock():
            self._trusted_journal_parent()
            rows = self._events(journal)
            if (not rows or rows[0]["event"] != "prepared"
                    or any(x["source_sha"] != scope["candidate_sha"]
                           or x["scope_sha256"] != scope["scope_sha256"]
                           or x["owner_approval_id"] != confirmed_approval_id
                           or x["manifest_sha256"] != rows[0]["manifest_sha256"]
                           or x["freeze_sha256"] != rows[0]["freeze_sha256"]
                           or x["signed_proof_sha256"] != confirmed_proof_sha256
                           for x in rows)
                    or rows[0]["signed_proof_sha256"] != confirmed_proof_sha256
                    or rows[-1]["event"] == "rolled_back"):
                raise StageANativeDenied("STAGE_A_RECOVERY_RECEIPT_INVALID")
            self._verify_objects(scope, partial=True)
            binding = {
                "source_sha": scope["candidate_sha"],
                "scope_sha256": scope["scope_sha256"],
                "owner_approval_id": confirmed_approval_id,
                "manifest_sha256": rows[0]["manifest_sha256"],
                "freeze_sha256": rows[0]["freeze_sha256"],
                "signed_proof_sha256": confirmed_proof_sha256,
            }
            self._append(journal, "rollback_intent", binding)
            for row in scope["symlinks"]:
                path = self._map(row["path"])
                if path.is_symlink():
                    path.unlink()
            for row in scope["files"]:
                path = self._map(row["path"])
                if path.is_file():
                    path.unlink()
            for row in reversed(scope["directories"]):
                path = self._map(row["path"])
                if path.is_dir():
                    path.rmdir()
            if any(self._map(name).exists() or self._map(name).is_symlink()
                   for name in (packet.ROOT, packet.HOST_CODE, packet.ETC)):
                raise StageANativeDenied("STAGE_A_RECOVERY_BASELINE_NOT_EMPTY")
            self._append(journal, "rolled_back", binding)
            return {
                "status": "empty_baseline_restored",
                "rollback_sha": packet.EMPTY_BASELINE,
                "source_sha": scope["candidate_sha"],
                "receipt_chain_sha256": self._events(journal)[-1]["hash"],
                "production_mutation": self.production,
            }


def production_root_health_readback() -> dict[str, Any]:
    """Recheck *root-owned* control files in addition to delegated views.

    Never use a mere unprivileged drift PASS to authorize installation.
    This is invoked by the independently installed root worker UNDER the
    native legacy release lock immediately before any Stage A0 write.
    """
    if os.geteuid() != 0:
        raise StageANativeDenied("STAGE_A_ROOT_HEALTH_REQUIRES_ROOT")
    control = packet.RELEASE_STATE / "production-control-state.json"
    drift = packet.RELEASE_STATE / "production-drift.json"
    delegated_control = packet.RELEASE_STATE / "protected-readback/production-control-state.json"
    delegated_drift = packet.RELEASE_STATE / "protected-readback/production-drift.json"
    for p in (control, drift):
        _require_secure_regular(p, 0, 0o600)
    actual_control = json.loads(control.read_bytes())
    actual_drift = json.loads(drift.read_bytes())
    view_control = json.loads(delegated_control.read_bytes())
    view_drift = json.loads(delegated_drift.read_bytes())
    if actual_control != view_control or actual_drift != view_drift:
        raise StageANativeDenied("STAGE_A_DELEGATED_ROOT_EVIDENCE_MISMATCH")
    evidence = packet.recovery_readback()
    if (evidence.get("breaker_state") != "closed"
            or evidence.get("preflight_evidence_satisfied") is not True):
        raise StageANativeDenied("STAGE_A_ROOT_BREAKER_OR_HEALTH_DENIED")
    # Only root can reliably lstat the protected /etc/jason parent.
    for path in ("/usr/local/lib/jason", "/var/lib/jason", "/etc/jason"):
        info = Path(path).lstat()
        if (Path(path).is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_mode & 0o002):
            raise StageANativeDenied("STAGE_A_UNTRUSTED_PARENT")
    absent = all(
        not Path(p).exists() and not Path(p).is_symlink()
        for p in (packet.HOST_CODE, packet.ROOT, packet.ETC)
    )
    evidence["stage_a_empty_baseline_verified"] = absent
    evidence["root_only_target_parent_verification_needed"] = False
    if not absent:
        raise StageANativeDenied("STAGE_A_PREEXISTING_TARGET_NEEDS_RECONCILIATION")
    return evidence


def execute_native_stage_a0_request(request: Mapping[str, Any],
                                    *, repo: Path) -> dict[str, Any]:
    """Narrow root worker handler; no user-controllable paths or test key.

    The existing root worker independently verifies the exact protected
    source and loads only this root-installed module. This function also
    checks authoritative GitHub CI with the existing read-only gh identity.
    It never changes a running service, freeze, breaker, signer's key,
    provider credential or the PMv3 production ledger.
    """
    if os.geteuid() != 0:
        raise StageANativeDenied("STAGE_A_NATIVE_WORKER_NOT_ROOT")
    if set(request) != {
        "request_id", "source_revision", "action", "scope_sha256",
        "manifest_sha256", "freeze_sha256", "signed_owner_proof",
    } or request["action"] != "pmv4_stage_a0_install":
        raise StageANativeDenied("STAGE_A_UNRECOGNIZED_ROOT_REQUEST")
    candidate = packet._require_sha(request["source_revision"])
    # Import the independently reviewed CI gate only through root-controlled
    # immutable source under the pre-existing Jason native host worker.
    from tools.pmv4_shadow_ci import protected_main_ci_verified

    def gh_as_al(args: list[str], **kwargs: Any) -> Any:
        import subprocess
        return subprocess.run(
            ["/usr/sbin/runuser", "-u", "al", "--", *args], **kwargs
        )

    def check_ci(sha: str) -> bool:
        return protected_main_ci_verified(sha, runner=gh_as_al)

    # Exact repo HEAD/clean checkout must be source staged by the existing
    # native release mechanism; a developer tree never serves as root input.
    packet.verify_exact_repository_head(repo, candidate)
    source = packet.build_scope(repo, candidate)
    if source["scope_sha256"] != request["scope_sha256"]:
        raise StageANativeDenied("STAGE_A_REQUESTED_SCOPE_MISMATCH")
    freeze_bytes = packet.FREEZE.read_bytes()
    freeze_digest = _hash(freeze_bytes)
    if freeze_digest != request["freeze_sha256"]:
        raise StageANativeDenied("STAGE_A_REQUESTED_FREEZE_MISMATCH")
    expected_manifest = admission.exact_stage_a_manifest(source, freeze_digest)
    if _hash(_canonical(expected_manifest)) != request["manifest_sha256"]:
        raise StageANativeDenied("STAGE_A_REQUESTED_MANIFEST_MISMATCH")
    proof = request["signed_owner_proof"]
    approval_id = (proof.get("payload") or {}).get("approval_id")
    if (not isinstance(approval_id, str)
            or not approval_id.startswith("owner-mcp-")
            or len(approval_id) != 42):
        raise StageANativeDenied("STAGE_A_REQUEST_HAS_NO_SIGNED_OWNER_ID")
    native = NativeStageAInstaller(
        production=True, owner_metadata=True,
        root_health=production_root_health_readback,
    )
    journal = native._journal(candidate)
    if journal.exists():
        # A previously journaled install was interrupted or its request was
        # replayed. Preserve the earlier signed decision's one-use constraint:
        # never re-issue installation. Restore only exact, hash-verified A0
        # objects; refuse any unknown entry or broken journal.
        rows = native._events(journal)
        if rows and rows[-1]["event"] == "rolled_back":
            raise StageANativeDenied("STAGE_A_OWNER_DECISION_ALREADY_CONSUMED")
        if rows and rows[-1]["event"] == "verified_installed":
            raise StageANativeDenied("STAGE_A_ALREADY_INSTALLED_NO_REPLAY")
        return native.recover_empty(
            scope=source, confirmed_approval_id=approval_id,
            confirmed_proof_sha256=_hash(_canonical(proof)),
        )
    try:
        return native.install(
            repo=repo, candidate_sha=candidate,
            scope=source, manifest=expected_manifest,
            signed_proof=proof, freeze_path=packet.FREEZE, ci_check=check_ci,
        )
    except Exception as exc:
        # Ordinary exceptions after a root journal was prepared MUST attempt
        # the safe authorized empty-baseline rollback without waiting for
        # another Owner prompt. An unexpected foreign object remains blocked.
        if journal.exists():
            try:
                native.recover_empty(
                    scope=source, confirmed_approval_id=approval_id,
                    confirmed_proof_sha256=_hash(_canonical(proof)),
                )
            except Exception as rollback_error:
                raise StageANativeDenied(
                    "STAGE_A_NATIVE_INSTALL_FAILED_AND_ROLLBACK_REQUIRES_REVIEW"
                ) from rollback_error
            raise StageANativeDenied(
                "STAGE_A_NATIVE_INSTALL_FAILED_ROLLBACK_VERIFIED"
            ) from exc
        raise
