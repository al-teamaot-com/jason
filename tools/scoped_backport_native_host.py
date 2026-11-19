#!/usr/bin/env python3
"""Root-attested native host for reviewed scoped runtime/MCP backport releases.

SOURCE ONLY. This file MUST NOT be invoked from a mutable checkout with sudo.
Installed root source, its exact digest, the original native deploy helper,
automatic recovery unit and Owner public key are independent trust boundaries.
No production changes are possible before that installation is verified.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping

from implementation.kernel.signed_owner_release import read_pinned_root_owner_public_key
from tools.scoped_backport_release import (
    PROTECTED, ENV, ROLLBACK_ENV, GROUP_BIND_DESTINATIONS,
    source_admission, validate_offer, ScopedBackportDenied, deny,
)

INSTALL_ROOT = Path("/usr/local/lib/jason/scoped-backport")
INSTALLED = INSTALL_ROOT / "tools/scoped_backport_native_host.py"
ROOT_POLICY = Path("/etc/jason-owner-release/scoped-backport-installed.json")
STATE = Path("/var/lib/jason/openclaw/release-manager")
ROOT_STATE = Path("/var/lib/jason-scoped-backport")
TRUST_KEY = Path("/etc/jason-owner-release/verified-owner-public-key.json")
SOURCE_REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
NATIVE = INSTALL_ROOT / "tools/deploy_live_container.py"
TIMER = "jason-scoped-backport-recovery.timer"
REQUEST_PATH = "jason-scoped-backport-requests.path"
CONTROL = STATE / "production-control-state.json"
DRIFT = STATE / "production-drift.json"
FREEZE = STATE / "production-deployment-freeze"
LOCK = STATE / "production-transaction.lock"
SHA = re.compile(r"^[a-f0-9]{40}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
APPROVAL = re.compile(r"^owner-mcp-[a-f0-9]{32}$")
PRODUCTION = ("jason-runtime", "jason-mcp-pilot")
APPROLE_PATHS = tuple(
    (Path(f"/opt/jason/bootstrap/secrets/openbao/microsoft-graph-group-{role}-approle") / source,
     dest)
    for role in ("read", "write")
    for source, dest in (("role-id", "role_id"), ("secret-id", "secret_id"))
)
ROOT_RECEIPT = Path("/var/lib/jason/authority/m365-group-runtime-approle-access-20261112.json")
ROOT_POLICY_FIELDS = {
    "schema_version", "profile", "trusted_source_sha", "reviewed_ci_sha",
    "root_handler_sha256", "native_host_sha256",
    "core_sha256", "request_module_sha256", "owner_local_sha256",
    "kernel_owner_proof_sha256", "native_deploy_sha256",
    "root_recovery_sha256", "recovery_unit_sha256", "recovery_timer_sha256",
    "request_unit_sha256", "request_path_sha256",
    "native_root_control_supported", "automatic_rollback_recovery_installed",
    "exact_signed_owner_approval_required", "no_global_owner_elevation",
}
# Modules are loaded from an immutable, trusted root-owned installation, not
# from caller-controlled PYTHONPATH. Original code digest binding is mandatory.
INSTALL_FILES = {
    "root_handler_sha256": INSTALL_ROOT / "tools/scoped_backport_native_root.py",
    "native_host_sha256": INSTALLED,
    "core_sha256": INSTALL_ROOT / "tools/scoped_backport_release.py",
    "request_module_sha256": INSTALL_ROOT / "tools/scoped_backport_release_request.py",
    "owner_local_sha256": INSTALL_ROOT / "tools/scoped_backport_owner_local_approval.py",
    "kernel_owner_proof_sha256": INSTALL_ROOT / "implementation/kernel/signed_owner_release.py",
    "native_deploy_sha256": NATIVE,
    "root_recovery_sha256": INSTALL_ROOT / "tools/scoped_backport_native_recovery.py",
    "recovery_unit_sha256": Path("/etc/systemd/system/jason-scoped-backport-recovery.service"),
    "recovery_timer_sha256": Path("/etc/systemd/system/jason-scoped-backport-recovery.timer"),
    "request_unit_sha256": Path("/etc/systemd/system/jason-scoped-backport-requests.service"),
    "request_path_sha256": Path("/etc/systemd/system/jason-scoped-backport-requests.path"),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def exact_file(path: Path, *, uid: int, mode: int | None = None,
               max_size: int = 131072) -> bytes:
    if path.is_symlink() or not path.is_file():
        deny("ROOT_FILE_MISSING_OR_SYMLINK")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        item = os.fstat(fd)
        if (not stat.S_ISREG(item.st_mode) or item.st_uid != uid or item.st_nlink != 1
                or (mode is not None and stat.S_IMODE(item.st_mode) != mode)
                or item.st_mode & 0o022
                or not 1 <= item.st_size <= max_size):
            deny("ROOT_FILE_METADATA_MISMATCH")
        buf = os.read(fd, max_size + 1)
        if len(buf) != item.st_size:
            deny("ROOT_FILE_CHANGED_DURING_READ")
        return buf
    finally:
        os.close(fd)


def root_directory(path: Path, *, mode: int = 0o700) -> None:
    if path.is_symlink() or not path.is_dir():
        deny("ROOT_STATE_DIRECTORY_MISSING")
    m = path.stat()
    if m.st_uid != 0 or stat.S_IMODE(m.st_mode) != mode:
        deny("ROOT_STATE_DIRECTORY_OWNER_MODE")


def root_json(path: Path, *, max_size=131072) -> dict:
    try:
        doc = json.loads(exact_file(path, uid=0, mode=0o600, max_size=max_size))
    except (ValueError, UnicodeError) as exc:
        raise ScopedBackportDenied("SCOPED_BACKPORT_ROOT_JSON_INVALID") from exc
    if not isinstance(doc, dict):
        deny("ROOT_JSON_NOT_OBJECT")
    return doc


def atomic_root_json(path: Path, data: Mapping, *, replace: bool = False) -> None:
    root_directory(path.parent)
    if path.is_symlink() or path.exists() and not replace:
        deny("ROOT_EVIDENCE_ALREADY_EXISTS")
    if replace:
        exact_file(path, uid=0, mode=0o600)
    raw = json.dumps(dict(data), separators=(",", ":"), sort_keys=True).encode() + b"\n"
    fd, temp = tempfile.mkstemp(prefix=".scoped-release-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temp, 0, 0)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run(*argv: str, timeout: int = 120, allow_failure=False) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if result.returncode and not allow_failure:
        deny("TRUSTED_COMMAND_FAILED")
    return result


def inspect(name: str) -> dict:
    if name not in PROTECTED + PRODUCTION and not name.startswith(
            ("jason-runtime-rollback-scoped-", "jason-mcp-pilot-rollback-scoped-")):
        deny("UNKNOWN_DOCKER_TARGET")
    data = json.loads(run("docker", "inspect", name, timeout=15).stdout)
    if len(data) != 1 or data[0].get("Name") != "/" + name:
        deny("DOCKER_TARGET_CARDINALITY")
    return data[0]


def env(container: Mapping, name: str) -> str | None:
    values = []
    for line in ((container.get("Config") or {}).get("Env") or []):
        if line.startswith(name + "="):
            values.append(line.partition("=")[2])
    if len(values) > 1:
        deny("DUPLICATE_PROTECTED_ENV_SETTING")
    return values[0] if values else None


def source(container: Mapping) -> str:
    labels = (container.get("Config") or {}).get("Labels") or {}
    values = [labels.get("org.opencontainers.image.revision"),
              labels.get("com.teamaot.jason.source_revision")]
    known = [v for v in values if v and v != "<no value>"]
    if not known or any(v != known[0] for v in known):
        deny("CONTAINER_SOURCE_LABEL_DRIFT")
    return known[0]


class NativeScopedBackportHost:
    """Exact source-bound native host; all mutations require installed root trust."""

    def __init__(self, *, repo: Path = SOURCE_REPO,
                 root: Path = ROOT_STATE, state: Path = STATE):
        self.repo = repo
        self.root = root
        self.state = state
        self.policy: dict | None = None
        self.active_offer: dict | None = None
        self.freeze_before: dict | None = None
        self.original: dict | None = None

    def enforce_installed_root_trust(self) -> None:
        if os.geteuid() != 0 or Path(__file__).resolve(strict=True) != INSTALLED:
            deny("IMMUTABLE_ROOT_INSTALL_REQUIRED")
        policy = root_json(ROOT_POLICY, max_size=8192)
        if (set(policy) != ROOT_POLICY_FIELDS or policy["schema_version"] != "1.0"
                or policy["profile"] != "governed-scoped-backport-v1"
                or not isinstance(policy["trusted_source_sha"], str)
                or not SHA.fullmatch(policy["trusted_source_sha"])
                or not isinstance(policy["reviewed_ci_sha"], str)
                or not SHA.fullmatch(policy["reviewed_ci_sha"])
                or any(policy[k] is not True for k in (
                    "native_root_control_supported",
                    "automatic_rollback_recovery_installed",
                    "exact_signed_owner_approval_required",
                    "no_global_owner_elevation"))):
            deny("ROOT_INSTALL_POLICY_INVALID")
        for field, path in INSTALL_FILES.items():
            expected = policy[field]
            if not isinstance(expected, str) or not HASH.fullmatch(expected):
                deny("ROOT_INSTALL_DIGEST_INVALID")
            if sha256(exact_file(path, uid=0, max_size=1_000_000)).hexdigest() != expected:
                deny("ROOT_INSTALLED_SOURCE_DRIFT")
        for p in (INSTALL_ROOT, INSTALL_ROOT / "tools"):
            if p.is_symlink() or not p.is_dir() or p.stat().st_uid != 0 or p.stat().st_mode & 0o022:
                deny("ROOT_EXECUTABLE_DIRECTORY_UNTRUSTED")
        # Public receipt can be read by the operator but cannot be
        # independently rewritten by that operator. Root verifies it against
        # the full private source/role policy before consuming queued work.
        from tools.scoped_backport_release_request import installed_attestation
        public = installed_attestation()
        for field in ("profile", "trusted_source_sha", "reviewed_ci_sha",
                      "root_handler_sha256", "native_root_control_supported",
                      "automatic_rollback_recovery_installed",
                      "exact_signed_owner_approval_required"):
            if public[field] != policy[field]:
                deny("PUBLIC_AND_PRIVATE_INSTALL_TRUST_DIVERGED")
        for argv in (("systemctl", "is-enabled", TIMER),
                     ("systemctl", "is-active", TIMER),
                     ("systemctl", "is-enabled", REQUEST_PATH),
                     ("systemctl", "is-active", REQUEST_PATH)):
            if run(*argv, timeout=12).stdout.strip() not in (b"enabled", b"active"):
                deny("AUTOMATIC_CRASH_RECOVERY_NOT_RUNNING")
        root_directory(self.root)
        for folder in ("transactions", "consumed-owner-approvals",
                       "freeze-backups", "offers", "requests"):
            root_directory(self.root / folder)
        # Force verification of the pinned root-controlled signer trust.
        read_pinned_root_owner_public_key(TRUST_KEY)
        self.policy = policy

    def _require_root_trust(self) -> None:
        if (self.policy is None or os.geteuid() != 0
                or Path(__file__).resolve(strict=True) != INSTALLED):
            deny("IMMUTABLE_ROOT_INSTALL_REQUIRED")

    @contextmanager
    def release_lock(self, offer: Mapping):
        validate_offer(offer)
        self._require_root_trust()
        if LOCK.is_symlink() or not LOCK.is_file():
            deny("NATIVE_RELEASE_LOCK_MISSING")
        fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW)
        try:
            meta = os.fstat(fd)
            if (meta.st_uid != pwd.getpwnam("al").pw_uid or
                    not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o002):
                deny("NATIVE_LOCK_UNTRUSTED")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ScopedBackportDenied("SCOPED_BACKPORT_RELEASE_TRANSACTION_BUSY") from exc
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _frozen(self, offer: Mapping) -> dict:
        if FREEZE.is_symlink() or not FREEZE.is_file():
            deny("PRODUCTION_FREEZE_MISSING")
        uid = pwd.getpwnam("al").pw_uid
        raw = exact_file(FREEZE, uid=uid, mode=0o600, max_size=4096)
        if sha256(raw).hexdigest() != offer["freeze_sha256"]:
            deny("PRODUCTION_FREEZE_SOURCE_CHANGED")
        doc = json.loads(raw)
        if doc.get("status") != "active" or doc.get("scope") != "manual-and-automatic-production-promotions":
            deny("PRODUCTION_FREEZE_INACTIVE")
        meta = FREEZE.stat()
        return {"raw": raw, "uid": meta.st_uid, "gid": meta.st_gid,
                "mode": stat.S_IMODE(meta.st_mode)}

    def _group_mounts(self) -> tuple[str, ...]:
        if not ROOT_RECEIPT.is_file():
            deny("GROUP_APPROLED_CORRECTION_NOT_ATTESTED")
        receipt = root_json(ROOT_RECEIPT, max_size=8192)
        if (receipt.get("approved_scope") != "aot-m365-group-app-role-runtime-files-four-only"
                or receipt.get("file_count") != 4
                or receipt.get("production_deployment") is not False
                or receipt.get("graph_mutation") is not False):
            deny("GROUP_APPROLE_RECEIPT_SCOPE")
        mounts = []
        for path, leaf in APPROLE_PATHS:
            parent = path.parent
            if parent.is_symlink() or not parent.is_dir():
                deny("GROUP_APPROLE_DIRECTORY_UNTRUSTED")
            ps = parent.stat()
            if ps.st_uid != 0 or ps.st_mode & 0o077:
                deny("GROUP_APPROLE_DIRECTORY_MODE")
            meta = path.lstat()
            if (path.is_symlink() or not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != 0 or meta.st_gid != 1000
                    or stat.S_IMODE(meta.st_mode) != 0o640):
                deny("GROUP_APPROLE_FILE_SCOPE_DRIFT")
            role = parent.name.removeprefix("microsoft-graph-group-").removesuffix("-approle")
            dest = f"/run/jason-secrets/openbao/microsoft-group-{role}/{leaf}"
            if dest not in GROUP_BIND_DESTINATIONS:
                deny("GROUP_APPROLE_MOUNT_UNREVIEWED")
            mounts.append(f"{path}:{dest}")
        if {m.split(":")[1] for m in mounts} != set(GROUP_BIND_DESTINATIONS):
            deny("GROUP_APPROLE_MOUNT_INCOMPLETE")
        return tuple(mounts)

    def freshly_validate_live_scope(self, offer: Mapping) -> None:
        self._require_root_trust()
        o = validate_offer(offer)
        if self.policy is None:
            deny("ROOT_NOT_ATTESTED")
        if o["protected_main_sha"] != self.policy["trusted_source_sha"]:
            deny("PROTECTED_MAIN_INSTALL_SCOPE_CHANGED")
        admission = source_admission(self.repo, trusted_main_sha=o["protected_main_sha"])
        if (admission["candidate_sha"] != o["candidate_sha"]
                or admission["rollback_sha"] != o["rollback_sha"]
                or admission["scope_sha256"] != o["scope_sha256"]
                or admission["manifest_sha256"] != o["manifest_sha256"]):
            deny("FRESH_MAIN_BACKPORT_SCOPE_CHANGED")
        self.freeze_before = self._frozen(o)
        self._group_mounts()
        for target, old_id in (
            ("jason-runtime", o["rollback_runtime_image_id"]),
            ("jason-mcp-pilot", o["rollback_mcp_image_id"]),
        ):
            live = inspect(target)
            if (live["Image"] != old_id or source(live) != o["rollback_sha"]
                    or not live["State"]["Running"]):
                deny("PRODUCTION_BASELINE_NOT_EXACT")
        for image_key in ("runtime_image_id", "mcp_image_id",
                          "rollback_runtime_image_id", "rollback_mcp_image_id"):
            image_id = o[image_key]
            image = json.loads(run("docker", "image", "inspect", image_id).stdout)
            if len(image) != 1 or image[0]["Id"] != image_id:
                deny("CANDIDATE_IMAGE_IMMUTABILITY")
            rev = (image[0].get("Config") or {}).get("Labels", {}).get(
                "org.opencontainers.image.revision")
            expected = o["candidate_sha"] if not image_key.startswith("rollback") else o["rollback_sha"]
            if rev != expected:
                deny("IMAGE_SOURCE_LABEL_DRIFT")
        self.active_offer = o

    def ensure_breaker_closed_and_workers_quiescent(self) -> None:
        if self.active_offer is None:
            deny("NO_VERIFIED_SOURCE_SCOPE")
        ctl, drift = root_json(CONTROL), root_json(DRIFT)
        last = ((ctl.get("last_known_good") or {}).get("manifest") or {})
        if (ctl.get("circuit_breaker", {}).get("state") != "closed"
                or drift.get("status") != "pass" or drift.get("problems")
                or last.get("revision") != self.active_offer["rollback_sha"]
                or last.get("complete") is not True):
            deny("CIRCUIT_BREAKER_OR_PRODUCTION_ALIGNMENT")
        try:
            at = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError) as exc:
            raise ScopedBackportDenied("SCOPED_BACKPORT_PRODUCTION_DRIFT_TIME_INVALID") from exc
        age = (datetime.now(timezone.utc) - at).total_seconds()
        if not 0 <= age <= 180:
            deny("PROTECTED_DRIFT_PROOF_STALE")
        protected = self.snapshot_protected()
        if any(v.get("healthy") is False for v in protected.values()):
            deny("PROTECTED_SERVICE_UNHEALTHY")
        # The globally shared transaction lock remains held through all steps.
        # The future installed root worker must also attest release worker
        # quiescence before entering this method.

    def deny_unresolved_attempt(self, offer: Mapping) -> None:
        if (self.root / "transactions" / (offer["release_id"] + ".json")).exists():
            deny("UNRESOLVED_PREVIOUS_RELEASE")
        if (self.root / "active.json").exists():
            deny("OTHER_SCOPED_RELEASE_ACTIVE")

    def owner_public_key(self):
        return read_pinned_root_owner_public_key(TRUST_KEY)

    def consumed_approvals(self) -> frozenset[str]:
        folder = self.root / "consumed-owner-approvals"
        root_directory(folder)
        ids = []
        for file in folder.iterdir():
            if file.suffix != ".json" or not APPROVAL.fullmatch(file.stem):
                deny("OWNER_CONSUMPTION_LEDGER_FOREIGN_FILE")
            root_json(file, max_size=4096)
            ids.append(file.stem)
        return frozenset(ids)

    def snapshot_protected(self) -> dict:
        result = {}
        for name in PROTECTED:
            item = inspect(name)
            if not item["State"]["Running"]:
                deny("PROTECTED_SERVICE_DOWN")
            status = (item["State"].get("Health") or {}).get("Status")
            result[name] = {
                "id": item["Id"], "image": item["Image"],
                "started_at": item["State"]["StartedAt"],
                "healthy": status != "unhealthy" if status else None,
            }
        return result

    def verify_protected_unchanged(self, before: Mapping) -> None:
        now = self.snapshot_protected()
        if now != before:
            deny("UNRELATED_PRODUCTION_CONTAINERS_CHANGED")

    def _journal_path(self, offer: Mapping) -> Path:
        return self.root / "transactions" / (offer["release_id"] + ".json")

    def _journal(self, offer: Mapping) -> dict:
        return root_json(self._journal_path(offer), max_size=16384)

    def _journal_update(self, offer: Mapping, status: str, **fields):
        journal = self._journal(offer)
        journal.update(status=status, updated_at=utcnow(), **fields)
        atomic_root_json(self._journal_path(offer), journal, replace=True)

    def record_intent(self, offer: Mapping, decision: Mapping) -> None:
        self._require_root_trust()
        if self.active_offer != dict(offer):
            deny("RELEASE_INTENT_NOT_FRESH")
        self.original = self.snapshot_protected()
        atomic_root_json(self._journal_path(offer), {
            "schema_version": "1.0", "authorization": "exact_owner_scoped_backport",
            "release_id": offer["release_id"],
            "candidate_sha": offer["candidate_sha"],
            "rollback_sha": offer["rollback_sha"],
            "manifest_sha256": offer["manifest_sha256"],
            "scope_sha256": offer["scope_sha256"],
            "approval_id": decision["approval_id"],
            "protected_before": self.original,
            "status": "intent_durable_no_mutation", "created_at": utcnow(),
        })

    def consume_owner_proof(self, approval_id: str) -> None:
        self._require_root_trust()
        if not APPROVAL.fullmatch(approval_id):
            deny("OWNER_APPROVAL_ID_INVALID")
        if self.active_offer is None:
            deny("NO_ACTIVE_SCOPED_INTENT")
        doc = {"schema_version": "1.0", "approval_id": approval_id,
               "release_id": self.active_offer["release_id"],
               "consumed_at": utcnow(), "one_use": True}
        atomic_root_json(self.root / "consumed-owner-approvals" /
                         (approval_id + ".json"), doc)
        self._journal_update(self.active_offer, "one_use_owner_proof_consumed")

    @contextmanager
    def frozen_transaction(self, offer: Mapping, decision: Mapping):
        self._require_root_trust()
        if self.freeze_before is None:
            deny("UNVERIFIED_FREEZE_BEFORE_MUTATION")
        if decision["approval_id"] not in self.consumed_approvals():
            deny("OWNER_PROOF_NOT_CONSUMED")
        original = self._frozen(offer)
        if original != self.freeze_before:
            deny("FREEZE_CHANGED_AFTER_INTENT")
        backup = self.root / "freeze-backups" / (offer["release_id"] + ".json")
        atomic_root_json(backup, {
            "schema_version": "1.0", "release_id": offer["release_id"],
            "freeze_sha256": offer["freeze_sha256"],
            "raw_utf8": original["raw"].decode(),
            "uid": original["uid"], "gid": original["gid"], "mode": original["mode"],
        })
        self._journal_update(offer, "freeze_backup_durable")
        lifted = False
        try:
            FREEZE.unlink()
            lifted = True
            self._journal_update(offer, "freeze_temporarily_lifted_under_lock")
            yield
        finally:
            if lifted:
                self._restore_freeze(offer)
            self._journal_update(offer, "freeze_restored_pending_verify")

    def _restore_freeze(self, offer: Mapping):
        if self.freeze_before is None:
            deny("FREEZE_RESTORE_BASELINE_MISSING")
        original = self.freeze_before
        if FREEZE.exists():
            self._frozen(offer)
            return
        parent = FREEZE.parent
        fd, temporary = tempfile.mkstemp(prefix=".scoped-refreeze-", dir=parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(original["raw"])
                f.flush()
                os.fsync(f.fileno())
            os.chown(temporary, original["uid"], original["gid"])
            os.chmod(temporary, original["mode"])
            os.replace(temporary, FREEZE)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._frozen(offer)

    def verify_freeze_restored(self, offer: Mapping) -> None:
        self._frozen(offer)
        if self._journal(offer).get("status") not in (
                "freeze_restored_pending_verify", "outcome_recorded"):
            deny("FREEZE_RESTORE_RECEIPT_MISSING")
        self._journal_update(offer, "freeze_restored_verified")

    def _rollback_name(self, target: str, offer: Mapping) -> str:
        return target + "-rollback-scoped-" + offer["candidate_sha"][:12]

    def promote_exact(self, target: str, image: str, revision: str,
                      environment: Mapping[str, str], readonly_mounts: tuple[str, ...]) -> None:
        self._require_root_trust()
        offer = self.active_offer
        if offer is None or target not in PRODUCTION:
            deny("PRODUCTION_TARGET_OUT_OF_SCOPE")
        image_key = "runtime_image_id" if target == "jason-runtime" else "mcp_image_id"
        if (image != offer[image_key] or revision != offer["candidate_sha"]
                or dict(environment) != ENV
                or readonly_mounts != GROUP_BIND_DESTINATIONS
                or self._journal(offer).get("status") not in (
                    "freeze_temporarily_lifted_under_lock", "runtime_replaced")):
            deny("PRODUCTION_ACTION_NOT_EXACT")
        if run("docker", "inspect", self._rollback_name(target, offer),
               allow_failure=True, timeout=10).returncode == 0:
            deny("ROLLBACK_NAME_PREEXISTS")
        mounts = self._group_mounts()
        argv = [
            "python3", str(NATIVE), "--live", target,
            "--image", image,
            "--rollback", self._rollback_name(target, offer),
            "--source-revision", revision,
            "--health-url", ("http://127.0.0.1:8080/healthz"
                             if target == "jason-runtime"
                             else "http://127.0.0.1:8000/healthz"),
            "--harden", "--set-env", "JASON_M365_GROUP_ADMIN_PROFILE=" +
            environment["JASON_M365_GROUP_ADMIN_PROFILE"],
        ]
        for mount in mounts:
            argv.extend(("--add-readonly-bind", mount))
        self._journal_update(offer, "mutating_" + target.replace("-", "_"))
        result = run(*argv, allow_failure=True, timeout=480)
        if result.returncode or b"DEPLOYMENT=PASS" not in result.stdout:
            deny("NATIVE_CONTAINER_REPLACEMENT_FAILED")
        if inspect(target)["Image"] != image:
            deny("LIVE_CANDIDATE_IMAGE_MISMATCH")
        self._journal_update(offer, "runtime_replaced"
                             if target == "jason-runtime"
                             else "both_replaced_pending_readback")

    def verify_candidate_pair(self, offer: Mapping) -> None:
        for name, key in (("jason-runtime", "runtime_image_id"),
                          ("jason-mcp-pilot", "mcp_image_id")):
            item = inspect(name)
            if (item["Image"] != offer[key]
                    or source(item) != offer["candidate_sha"]
                    or not item["State"]["Running"]
                    or env(item, "JASON_M365_GROUP_ADMIN_PROFILE") !=
                    ENV["JASON_M365_GROUP_ADMIN_PROFILE"]):
                deny("LIVE_SCOPED_CANDIDATE_MISMATCH")
            if name == "jason-runtime" and (
                    item["State"].get("Health") or {}).get("Status") != "healthy":
                deny("LIVE_SCOPED_RUNTIME_HEALTH_FAILED")
            destinations = {m["Destination"] for m in item.get("Mounts", [])
                            if m.get("Destination") in GROUP_BIND_DESTINATIONS}
            if destinations != set(GROUP_BIND_DESTINATIONS):
                deny("APPROLE_MOUNTS_NOT_PRESENT")
        if Path("/opt/jason/current").resolve(strict=True).name != offer["rollback_sha"]:
            deny("HOST_SOURCE_CHANGED_OUT_OF_SCOPE")

    def restore_pair_exact(self, offer: Mapping) -> None:
        """Rollback only exact candidate pair to their retained original names."""
        self._require_root_trust()
        for name, old_key, new_key in (
            ("jason-mcp-pilot", "rollback_mcp_image_id", "mcp_image_id"),
            ("jason-runtime", "rollback_runtime_image_id", "runtime_image_id"),
        ):
            retained_name = self._rollback_name(name, offer)
            existing = run("docker", "inspect", name, allow_failure=True, timeout=10)
            current = inspect(name) if existing.returncode == 0 else None
            if current is not None and current["Image"] == offer[old_key]:
                if source(current) != offer["rollback_sha"]:
                    deny("ROLLBACK_SOURCE_WRONG")
                continue
            if current is not None and current["Image"] != offer[new_key]:
                deny("FOREIGN_LIVE_IMAGE_CANNOT_REMOVE")
            retained = inspect(retained_name)
            if (retained["Image"] != offer[old_key] or
                    source(retained) != offer["rollback_sha"]):
                deny("RETAINED_ROLLBACK_CONTAINER_CHANGED")
            if current is not None:
                run("docker", "rm", "-f", name, timeout=30)
            run("docker", "rename", retained_name, name, timeout=15)
            run("docker", "start", name, timeout=45)
            live = inspect(name)
            if live["Image"] != offer[old_key] or not live["State"]["Running"]:
                deny("ROLLBACK_RESTORED_CONTAINER_UNHEALTHY")
        self._journal_update(offer, "rollback_pair_attempted")

    def verify_rollback(self, offer: Mapping) -> None:
        for name, key in (("jason-runtime", "rollback_runtime_image_id"),
                          ("jason-mcp-pilot", "rollback_mcp_image_id")):
            item = inspect(name)
            if (item["Image"] != offer[key] or source(item) != offer["rollback_sha"]
                    or not item["State"]["Running"]
                    or env(item, "JASON_M365_GROUP_ADMIN_PROFILE") not in (None, "")):
                deny("ROLLBACK_IMAGE_OR_GROUP_PROFILE_MISMATCH")
        self._journal_update(offer, "rollback_pair_verified")

    def record_outcome(self, offer: Mapping, outcome: str,
                       error: str = "") -> None:
        self._require_root_trust()
        if outcome not in (
            "production_pair_verified", "rollback_verified",
            "rollback_unverified", "failed_before_mutation",
        ):
            deny("UNKNOWN_RELEASE_OUTCOME")
        self._journal_update(offer, "outcome_recorded",
                             outcome=outcome,
                             failure_class=str(error)[:120])

    def open_breaker(self, reason: str) -> None:
        self._require_root_trust()
        if not re.fullmatch(r"SCOPED_BACKPORT_[A-Z_]{4,80}", reason):
            deny("BREAKER_REASON_NOT_ALLOWLISTED")
        state = root_json(CONTROL)
        if state.get("schema_version") != "1.0":
            deny("PROTECTED_BREAKER_SCHEMA")
        state["circuit_breaker"] = {
            "state": "open", "source": "scoped_backport_release_root",
            "reason": reason, "updated_at": utcnow(),
        }
        # The release-manager state parent is al-owned; the actual control
        # file MUST remain root-owned 0600 and never be writable by al.
        parent = CONTROL.parent
        meta = parent.lstat()
        if (parent.is_symlink() or not stat.S_ISDIR(meta.st_mode)
                or meta.st_uid != pwd.getpwnam("al").pw_uid
                or stat.S_IMODE(meta.st_mode) != 0o700):
            deny("BREAKER_STATE_PARENT_UNTRUSTED")
        raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        fd, temporary = tempfile.mkstemp(prefix=".scoped-breaker-", dir=parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.chown(temporary, 0, 0)
            os.replace(temporary, CONTROL)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        if root_json(CONTROL)["circuit_breaker"]["state"] != "open":
            deny("BREAKER_OPEN_READBACK_FAILED")
