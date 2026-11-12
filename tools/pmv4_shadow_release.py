#!/usr/bin/env python3
"""Independent, Teams-free PMv4 shadow release transaction (preproduction source).

This does not depend on the PMV3 release manager. It *reuses* Jason's
independently authenticated, exact-scope signed Owner verifier. The only
mutable target is a separately provisioned PMv4 shadow root. A trusted
component activator and independently verified health/continuity probes
must be supplied by an authorized host installer; absent callbacks FAIL CLOSED.

No production installation, owner signing, root control, or activation is
performed by importing this module or running its read-only inspector.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, ContextManager, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from implementation.kernel.signed_owner_release import (
    OwnerReleaseProofDenied, canonical, read_pinned_root_owner_public_key,
    verify_exact_owner_release,
)

SHA = re.compile(r"\A[0-9a-f]{40}\Z")
HASH = re.compile(r"\A[0-9a-f]{64}\Z")
PROTECTED_CORE = "ticket-processing"
ALLOWED_REVIEW_PREFIXES = (
    "config/openclaw-specialists/", "config/pmv4-shadow/",
    "tools/pmv4_", "tests/test_pmv4_", "docs/operations/PMv4-",
)
EMPTY_BASELINE = "0" * 40  # first independent shadow install, no prior gateway
ROOT_FORBIDDEN = Path("/var/lib/jason/openclaw")
# This is the ONLY permitted live root for a future separately approved
# installer; deliberately distinct from PMV3 production state.
PRODUCTION_ROOT = Path("/var/lib/jason/pmv4-shadow")
TRUST_PATH = Path("/etc/jason-owner-release/verified-owner-public-key.json")
REPO = "al-teamaot-com/jason"
MANIFEST_FIELDS = {
    "schema_version", "service", "release_mode", "repository",
    "candidate_sha", "rollback_sha", "scope_sha256", "bundle_sha256",
    "compose_sha256", "image_digest", "read_only", "provider_writes", "teams_approval_required",
    "production_core_changes", "network_profile", "activation",
}


class ShadowReleaseDenied(PermissionError):
    """Release refused without mutating any target (except durable denied logs)."""


def digest_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def safe_root(root: Path, *, production: bool) -> Path:
    p = Path(root)
    if not p.is_absolute() or ".." in p.parts:
        raise ShadowReleaseDenied("SHADOW_ROOT_NONCANONICAL")
    if p == ROOT_FORBIDDEN or ROOT_FORBIDDEN in p.parents:
        raise ShadowReleaseDenied("SHADOW_OVERLAPS_PMV3")
    if production and p != PRODUCTION_ROOT:
        raise ShadowReleaseDenied("SHADOW_PRODUCTION_ROOT_NOT_PINNED")
    if p.is_symlink() or not p.is_dir():
        raise ShadowReleaseDenied("SHADOW_ROOT_MISSING_OR_SYMLINK")
    if p.resolve(strict=True) != p:
        raise ShadowReleaseDenied("SHADOW_ROOT_REALPATH_MISMATCH")
    if production:
        meta = p.lstat()
        if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
            raise ShadowReleaseDenied("SHADOW_ROOT_OS_TRUST_MISSING")
    return p


def read_json(path: Path, *, max_bytes: int = 128 * 1024) -> dict[str, Any]:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("type/size")
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise ValueError("size")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("object required")
        return data
    except (OSError, ValueError, TypeError) as exc:
        raise ShadowReleaseDenied("SHADOW_INVALID_OR_UNAVAILABLE_JSON") from exc


def write_json_exclusive(path: Path, obj: Mapping[str, Any]) -> None:
    """Create one immutable authorization journal entry; no symlink follow."""
    blob = canonical(obj)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ShadowReleaseDenied("SHADOW_RECEIPT_EXISTS_OR_UNAVAILABLE") from exc
    with os.fdopen(fd, "wb") as out:
        out.write(blob)
        out.flush()
        os.fsync(out.fileno())


def update_journal(path: Path, obj: Mapping[str, Any]) -> None:
    """Atomic shadow-only evidence write, never production root records."""
    tmp = path.with_name(".tmp-" + path.name)
    if tmp.exists() or tmp.is_symlink():
        raise ShadowReleaseDenied("SHADOW_JOURNAL_TEMP_CONFLICT")
    write_json_exclusive(tmp, obj)
    os.replace(tmp, path)


def manifest_check(m: Mapping[str, Any]) -> None:
    if set(m) != MANIFEST_FIELDS:
        raise ShadowReleaseDenied("SHADOW_MANIFEST_SCHEMA_INVALID")
    if (m["schema_version"] != "1.0"
        or m["service"] != "jason-pmv4-shadow"
        or m["release_mode"] != "owner-signed-isolated-shadow"
        or m["repository"] != REPO
        or m["read_only"] is not True
        or m["provider_writes"] is not False
        or m["teams_approval_required"] is not False
        or m["production_core_changes"] != []
        or m["network_profile"] != "disconnected"
        or m["activation"] != "shadow-only"
        or any(not isinstance(m[k], str) or not SHA.fullmatch(m[k])
               for k in ("candidate_sha", "rollback_sha"))
        or any(not isinstance(m[k], str) or not HASH.fullmatch(m[k])
               for k in ("scope_sha256", "bundle_sha256", "compose_sha256"))
        or not isinstance(m["image_digest"], str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", m["image_digest"])):
        raise ShadowReleaseDenied("SHADOW_MANIFEST_FIELDS_INVALID")
    if m["candidate_sha"] == m["rollback_sha"]:
        raise ShadowReleaseDenied("SHADOW_NO_DISTINCT_ROLLBACK")


def bundle_digest(path: Path) -> str:
    """Stable inventory hash, rejecting symlinks, devices and path tricks."""
    if not path.is_dir() or path.is_symlink():
        raise ShadowReleaseDenied("SHADOW_BUNDLE_DIRECTORY_INVALID")
    rows: list[dict[str, str]] = []
    for entry in sorted(path.rglob("*")):
        if entry.is_symlink():
            raise ShadowReleaseDenied("SHADOW_BUNDLE_SYMLINK")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise ShadowReleaseDenied("SHADOW_BUNDLE_NONREGULAR_FILE")
        relative = entry.relative_to(path).as_posix()
        if relative.startswith(".") or "//" in relative or ".." in relative.split("/"):
            raise ShadowReleaseDenied("SHADOW_BUNDLE_PATH_INVALID")
        rows.append({"path": relative, "sha256": digest_file(entry)})
        if len(rows) > 256:
            raise ShadowReleaseDenied("SHADOW_BUNDLE_OVERSIZED")
    if not rows:
        raise ShadowReleaseDenied("SHADOW_BUNDLE_EMPTY")
    return sha256(canonical({"files": rows})).hexdigest()


@dataclass(frozen=True)
class VerifiedScope:
    release_id: str
    candidate_sha: str
    rollback_sha: str
    manifest_sha256: str
    scope_sha256: str
    freeze_sha256: str
    approval_id: str


class ShadowController:
    """Trusted host adapter, without any PMV3 release-manager dependency.

    Callbacks must be independently provisioned by a release installer and
    may not originate from the candidate bundle or a chat-provided script.
    """

    def __init__(self, root: Path, *, public_key_path: Path,
                 protected_ci_check: Callable[[str], bool],
                 activate_shadow: Callable[[Path], None],
                 verify_shadow_and_core: Callable[[Path], bool],
                 restore_shadow: Callable[[Path], None],
                 production: bool = True,
                 host_mutation_quiescent: Callable[[], bool] | None = None,
                 preexisting_core_health: Callable[[], bool] | None = None,
                 host_release_transaction: Callable[[], ContextManager[None]] | None = None):
        self.root = safe_root(root, production=production)
        self.public_key_path = Path(public_key_path)
        if production and self.public_key_path != TRUST_PATH:
            raise ShadowReleaseDenied("SHADOW_ROOT_TRUST_PATH_NOT_PINNED")
        self.protected_ci_check = protected_ci_check
        self.activate_shadow = activate_shadow
        self.verify_shadow_and_core = verify_shadow_and_core
        self.restore_shadow = restore_shadow
        self.production = production
        # Both are mandatory for real production, including a separate host:
        # its isolation attestor may return true for host quiescence only
        # after independently verifying no shared control plane exists.
        if production and (
            not callable(host_mutation_quiescent)
            or not callable(preexisting_core_health)
        ):
            raise ShadowReleaseDenied("SHADOW_HOST_AND_CORE_PROBES_NOT_PROVISIONED")
        self.host_mutation_quiescent = host_mutation_quiescent
        self.preexisting_core_health = preexisting_core_health
        if production and not callable(host_release_transaction):
            raise ShadowReleaseDenied("SHADOW_CROSS_RELEASE_LOCK_NOT_PROVISIONED")
        self.host_release_transaction = host_release_transaction or nullcontext

    def _paths(self) -> tuple[Path, Path, Path, Path]:
        for name in ("releases", "receipts", "control"):
            path = self.root / name
            if path.is_symlink() or not path.is_dir():
                raise ShadowReleaseDenied("SHADOW_CONTROL_DIRECTORY_UNAVAILABLE")
            if self.production:
                meta = path.lstat()
                if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
                    raise ShadowReleaseDenied("SHADOW_CONTROL_DIRECTORY_UNTRUSTED")
        return (self.root / "releases", self.root / "receipts",
                self.root / "control" / "shadow-freeze.json",
                self.root / "current")

    @staticmethod
    def _release_dir(releases: Path, sha: str) -> Path:
        if not SHA.fullmatch(sha):
            raise ShadowReleaseDenied("SHADOW_INVALID_RELEASE_IDENTITY")
        result = releases / sha
        if result.is_symlink() or not result.is_dir():
            raise ShadowReleaseDenied("SHADOW_MISSING_IMMUTABLE_RELEASE")
        return result

    @staticmethod
    def _active_sha(current: Path, releases: Path) -> str:
        if not current.is_symlink():
            raise ShadowReleaseDenied("SHADOW_CURRENT_POINTER_MISSING")
        target = os.readlink(current)
        if not target.startswith("releases/"):
            raise ShadowReleaseDenied("SHADOW_CURRENT_POINTER_UNTRUSTED")
        current_sha = target.removeprefix("releases/")
        if not SHA.fullmatch(current_sha):
            raise ShadowReleaseDenied("SHADOW_CURRENT_POINTER_UNTRUSTED")
        ShadowController._release_dir(releases, current_sha)
        return current_sha

    def _check_no_pending(self, receipts: Path) -> None:
        for item in receipts.iterdir():
            if item.is_symlink() or not item.is_file() or item.suffix != ".json":
                raise ShadowReleaseDenied("SHADOW_RECEIPT_STORE_UNTRUSTED")
            record = read_json(item)
            if record.get("state") not in ("accepted", "rolled_back"):
                raise ShadowReleaseDenied("SHADOW_UNRECONCILED_TRANSACTION")

    def preflight(self, manifest: Mapping[str, Any], approval: Mapping[str, Any],
                  *, at: datetime | None = None) -> VerifiedScope:
        """All checks independently rerun under the transaction lock."""
        manifest_check(manifest)
        releases, receipts, freeze, current = self._paths()
        # This is not PMV3 release execution: callbacks are independent
        # *read-only* attestors installed outside the candidate. No shared
        # production control may be modified while unsafe or in flight.
        if (self.host_mutation_quiescent is not None
            and self.host_mutation_quiescent() is not True):
            raise ShadowReleaseDenied("SHADOW_SHARED_HOST_MUTATION_NOT_QUIESCENT")
        if (self.preexisting_core_health is not None
            and self.preexisting_core_health() is not True):
            raise ShadowReleaseDenied("SHADOW_EXISTING_TICKET_CORE_UNVERIFIED")
        candidate, rollback = manifest["candidate_sha"], manifest["rollback_sha"]
        if self._active_sha(current, releases) != rollback:
            raise ShadowReleaseDenied("SHADOW_ROLLBACK_NOT_CURRENT")
        bundle = self._release_dir(releases, candidate) / "bundle"
        # The initial empty baseline has no PMv4 gateway; rollback must
        # remove only this shadow namespace. Later releases require a usable
        # previous immutable package.
        if rollback == EMPTY_BASELINE:
            if read_json(self._release_dir(releases, rollback) / "baseline.json") != {
                "schema_version": "1.0", "service": "jason-pmv4-shadow",
                "baseline": "no_prior_shadow_runtime",
            }:
                raise ShadowReleaseDenied("SHADOW_EMPTY_BASELINE_INVALID")
        else:
            bundle_digest(self._release_dir(releases, rollback) / "bundle")
        if bundle_digest(bundle) != manifest["bundle_sha256"]:
            raise ShadowReleaseDenied("SHADOW_BUNDLE_DIGEST_MISMATCH")
        if read_json(self._release_dir(releases, candidate) / "release-manifest.json") != dict(manifest):
            raise ShadowReleaseDenied("SHADOW_STAGED_MANIFEST_MISMATCH")
        if self.production:
            for path in (bundle, self._release_dir(releases, candidate),
                         self._release_dir(releases, candidate) / "release-manifest.json"):
                info = path.lstat()
                if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                    raise ShadowReleaseDenied("SHADOW_BUNDLE_NOT_ROOT_TRUSTED")
        compose = self.root / "control" / "docker-compose.yml"
        if not compose.is_file() or compose.is_symlink():
            raise ShadowReleaseDenied("SHADOW_COMPOSE_NOT_PROVISIONED")
        if digest_file(compose) != manifest["compose_sha256"]:
            raise ShadowReleaseDenied("SHADOW_COMPOSE_DRIFT")
        if self.production:
            meta = compose.lstat()
            if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
                raise ShadowReleaseDenied("SHADOW_COMPOSE_UNTRUSTED")
        freeze_doc = read_json(freeze)
        if freeze_doc != {"schema_version": "1.0", "status": "active",
                          "service": "jason-pmv4-shadow"}:
            raise ShadowReleaseDenied("SHADOW_FREEZE_NOT_ACTIVE")
        reviewed = self.root / "control" / "reviewed-scope.json"
        scope = read_json(reviewed)
        if set(scope) != {"schema_version", "service", "candidate_sha",
                          "rollback_sha", "bundle_sha256", "files", "protected_core",
                          "provider_writes"} or (
            scope["schema_version"] != "1.0"
            or scope["service"] != "jason-pmv4-shadow"
            or scope["candidate_sha"] != candidate
            or scope["rollback_sha"] != rollback
            or scope["bundle_sha256"] != manifest["bundle_sha256"]
            or not isinstance(scope["files"], list)
            or not scope["files"]
            or any(not isinstance(x, str) or not any(
                       x.startswith(prefix) for prefix in ALLOWED_REVIEW_PREFIXES)
                   or ".." in x.split("/") or x.startswith("/")
                   for x in scope["files"])
            or len(scope["files"]) != len(set(scope["files"]))
            or scope["protected_core"] != [PROTECTED_CORE]
            or scope["provider_writes"] is not False
            or sha256(canonical(scope)).hexdigest() != manifest["scope_sha256"]
        ):
            raise ShadowReleaseDenied("SHADOW_REVIEWED_SCOPE_MISMATCH")
        if self.production:
            meta = reviewed.lstat()
            if meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) & 0o022:
                raise ShadowReleaseDenied("SHADOW_REVIEWED_SCOPE_UNTRUSTED")
        if self.protected_ci_check(candidate) is not True:
            raise ShadowReleaseDenied("SHADOW_PROTECTED_SOURCE_OR_CI_UNVERIFIED")
        self._check_no_pending(receipts)
        manifest_digest = sha256(canonical(manifest)).hexdigest()
        signature = verify_exact_owner_release(
            approval,
            public_key=read_pinned_root_owner_public_key(
                self.public_key_path, require_root_owned=self.production
            ),
            expected_candidate_sha=candidate, expected_rollback_sha=rollback,
            expected_release_id="release-" + candidate[:16],
            expected_scope_sha256=manifest["scope_sha256"],
            expected_manifest_sha256=manifest_digest,
            expected_freeze_sha256=digest_file(freeze),
            at=at or datetime.now(timezone.utc),
            consumed_ids=frozenset(item.stem.removeprefix("owner-")
                                   for item in receipts.glob("owner-*.json")),
        )
        return VerifiedScope(
            "release-" + candidate[:16], candidate, rollback, manifest_digest,
            manifest["scope_sha256"], digest_file(freeze),
            signature["approval_id"],
        )

    @staticmethod
    def _switch(current: Path, sha: str) -> None:
        temp = current.with_name(".current.next")
        if temp.exists() or temp.is_symlink():
            raise ShadowReleaseDenied("SHADOW_POINTER_TEMP_CONFLICT")
        os.symlink("releases/" + sha, temp)
        os.replace(temp, current)
        fd = os.open(current.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def reconcile_pending_rollback(
        self, *, rollback_acceptance: Callable[[Path], bool],
    ) -> dict[str, Any]:
        # Hold the same host mutation lock used by legacy PMv3 for the ENTIRE
        # recovery transaction, not just a race-prone preflight instant.
        with self.host_release_transaction():
            return self._reconcile_pending_rollback_locked(
                rollback_acceptance=rollback_acceptance
            )

    def _reconcile_pending_rollback_locked(
        self, *, rollback_acceptance: Callable[[Path], bool],
    ) -> dict[str, Any]:
        """Only restore an interrupted *previously authorized* transaction.

        No new release, no new Owner grant, no PMV3 state touch. Missing
        identity, freeze drift, inconsistent pointer or failed rollback
        acceptance keeps the journal pending and blocks future promotion.
        """
        releases, receipts, freeze, current = self._paths()
        lockfile = self.root / "control" / "shadow-release.lock"
        if lockfile.is_symlink() or not lockfile.is_file():
            raise ShadowReleaseDenied("SHADOW_LOCK_UNAVAILABLE")
        with lockfile.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            pending: list[tuple[Path, dict[str, Any]]] = []
            for path in receipts.iterdir():
                if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                    raise ShadowReleaseDenied("SHADOW_RECEIPT_STORE_UNTRUSTED")
                record = read_json(path)
                if record.get("state") == "started":
                    pending.append((path, record))
                elif record.get("state") not in ("accepted", "rolled_back"):
                    raise ShadowReleaseDenied("SHADOW_UNKNOWN_JOURNAL_STATE")
            if not pending:
                return {"status": "nothing_pending", "production_mutation": False}
            if len(pending) != 1:
                raise ShadowReleaseDenied("SHADOW_MULTIPLE_PENDING_TRANSACTIONS")
            receipt_file, record = pending[0]
            candidate, rollback = record.get("candidate_sha"), record.get("rollback_sha")
            approval_id = record.get("approval_id")
            if (
                record.get("schema_version") != "1.0"
                or record.get("service") != "jason-pmv4-shadow"
                or not isinstance(candidate, str) or not SHA.fullmatch(candidate)
                or not isinstance(rollback, str) or not SHA.fullmatch(rollback)
                or not isinstance(approval_id, str)
                or receipt_file.name != "owner-" + approval_id + ".json"
                or record.get("release_id") != "release-" + candidate[:16]
                or not isinstance(record.get("freeze_sha256"), str)
                or not HASH.fullmatch(record["freeze_sha256"])
                or digest_file(freeze) != record["freeze_sha256"]
            ):
                raise ShadowReleaseDenied("SHADOW_PENDING_EVIDENCE_INVALID")
            observed = self._active_sha(current, releases)
            if observed not in (candidate, rollback):
                raise ShadowReleaseDenied("SHADOW_PENDING_POINTER_UNRELATED")
            prior = self._release_dir(releases, rollback)
            if rollback == EMPTY_BASELINE:
                if read_json(prior / "baseline.json") != {
                    "schema_version": "1.0", "service": "jason-pmv4-shadow",
                    "baseline": "no_prior_shadow_runtime",
                }:
                    raise ShadowReleaseDenied("SHADOW_EMPTY_BASELINE_INVALID")
            else:
                bundle_digest(prior / "bundle")
            self._switch(current, rollback)
            self.restore_shadow(prior)
            if self._active_sha(current, releases) != rollback:
                raise ShadowReleaseDenied("SHADOW_ROLLBACK_READBACK_FAILED")
            if rollback_acceptance(prior) is not True:
                raise ShadowReleaseDenied("SHADOW_ROLLBACK_HEALTH_UNVERIFIED")
            record["state"] = "rolled_back"
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            record["reconciled"] = True
            update_journal(receipt_file, record)
            return {
                "status": "shadow_rollback_verified",
                "rollback_sha": rollback,
                "recovered_release_id": record["release_id"],
                "pmv3_mutation": False,
            }

    def promote(self, manifest: Mapping[str, Any], approval: Mapping[str, Any],
                *, at: datetime | None = None) -> dict[str, Any]:
        # The legacy Release Manager and independent PMv4 cannot both mutate
        # the shared host while holding different lock inodes. This trusted
        # root-provisioned shared transaction encloses preflight, activation,
        # acceptance and rollback.
        with self.host_release_transaction():
            return self._promote_locked(manifest, approval, at=at)

    def _promote_locked(self, manifest: Mapping[str, Any],
                        approval: Mapping[str, Any],
                        *, at: datetime | None = None) -> dict[str, Any]:
        """One Owner-signed, single shadow transaction, with rollback on failure."""
        _, receipts, _, current = self._paths()
        lockfile = self.root / "control" / "shadow-release.lock"
        if lockfile.is_symlink() or not lockfile.is_file():
            raise ShadowReleaseDenied("SHADOW_LOCK_UNAVAILABLE")
        with lockfile.open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            scope = self.preflight(manifest, approval, at=at)
            releases = self.root / "releases"
            candidate_dir = self._release_dir(releases, scope.candidate_sha)
            previous_dir = self._release_dir(releases, scope.rollback_sha)
            receipt_file = receipts / ("owner-" + scope.approval_id + ".json")
            journal: dict[str, Any] = {
                "schema_version": "1.0", "service": "jason-pmv4-shadow",
                "state": "started", "release_id": scope.release_id,
                "approval_id": scope.approval_id,
                "candidate_sha": scope.candidate_sha,
                "rollback_sha": scope.rollback_sha,
                "manifest_sha256": scope.manifest_sha256,
                "scope_sha256": scope.scope_sha256,
                "freeze_sha256": scope.freeze_sha256,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "no_pmv3_or_provider_mutation": True,
            }
            write_json_exclusive(receipt_file, journal)
            try:
                self._switch(current, scope.candidate_sha)
                self.activate_shadow(candidate_dir)
                if self._active_sha(current, releases) != scope.candidate_sha:
                    raise ShadowReleaseDenied("SHADOW_DEPLOY_READBACK_MISMATCH")
                if self.verify_shadow_and_core(candidate_dir) is not True:
                    raise ShadowReleaseDenied("SHADOW_ACCEPTANCE_NOT_VERIFIED")
                if digest_file(self.root / "control" / "shadow-freeze.json") != scope.freeze_sha256:
                    raise ShadowReleaseDenied("SHADOW_FREEZE_DRIFT")
            except BaseException:
                # Even if rollback fails, preserve "started" for fail-closed
                # future admissions and explicit root reconciliation.
                try:
                    self._switch(current, scope.rollback_sha)
                    self.restore_shadow(previous_dir)
                    if self._active_sha(current, releases) != scope.rollback_sha:
                        raise ShadowReleaseDenied("SHADOW_ROLLBACK_READBACK_FAILED")
                    journal["state"] = "rolled_back"
                    journal["finished_at"] = datetime.now(timezone.utc).isoformat()
                    update_journal(receipt_file, journal)
                except BaseException:
                    pass
                raise
            journal["state"] = "accepted"
            journal["finished_at"] = datetime.now(timezone.utc).isoformat()
            update_journal(receipt_file, journal)
            return {
                "status": "shadow_accepted",
                "release_id": scope.release_id,
                "candidate_sha": scope.candidate_sha,
                "rollback_sha": scope.rollback_sha,
                "ticket_core_verified": True,
                "pmv3_mutation": False,
                "teams_approval": False,
            }


def inspect_only() -> int:
    """CLI deliberately provides no promotion or authorization shortcut."""
    print(json.dumps({
        "service": "jason-pmv4-shadow", "phase": "preproduction",
        "standalone_from_pmv3": True,
        "teams_required": False,
        "production_deployed": False,
        "production_authority": False,
        "runtime_adapter_installed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(inspect_only())
