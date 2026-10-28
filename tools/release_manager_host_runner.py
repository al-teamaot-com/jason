#!/usr/bin/env python3
"""Host-side Jason Release Manager.

Build once, validate the exact image in an isolated pre-production container,
then promote the same image to production through the canonical production
deployment script. Release records are durable and evidence-gated.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import pwd
import secrets
import sqlite3
import os
import stat
import re
import shutil
import subprocess
import tempfile
import sys
import time
import urllib.request
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import release_manager_gate as gate
sys.path.insert(0, str(Path(__file__).resolve().parent))
import production_read_canary_gate as owner_read_canary
import worker_execution_enrollment as worker_enrollment

DEFAULT_REPO = Path("/home/al/.local/lib/jason/engineering-worker-source")
DEFAULT_STATE = Path("/var/lib/jason/openclaw/release-manager")
MOBILE_APPROVAL_POLICY = Path("/var/lib/jason/authority/mobile-release-approval-policy.json")
SHA = re.compile(r"^[0-9a-f]{40}$")
MUTATION_ENV_OVERRIDES = {
    "JASON_AUTOTASK_MUTATION_ENABLED": "false",
    "JASON_AUTOTASK_TICKET_UPDATE_MCP_PROFILE": "",
    "JASON_AUTOTASK_INTERNAL_NOTE_MCP_PROFILE": "",
    "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE": "",
    "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE": "",
    "JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE": "",
    "JASON_DATTO_COMPONENT_EXECUTION_AUTONOMY_ENABLED": "false",
    "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID": "",
    "JASON_AUTONOMY_WORKER_ENABLED": "false",
    "JASON_AUTONOMY_SHADOW_ENABLED": "false",
    "JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED": "false",
    "JASON_UNIVERSAL_APPROVAL_MODE": "off",
    "JASON_UNIVERSAL_APPROVAL_WORKER_ENABLED": "false",
    # A test-only Teams card must never be issued from isolated preproduction.
    "JASON_OWNER_UAT_MODE": "off",
    "JASON_OWNER_UAT_WORKER_ENABLED": "false",
    "JASON_OWNER_UAT_SESSION_ID": "",
    # Isolated preproduction must not issue real owner Teams cards or read
    # live mobile release approvals even when production mode is enabled.
    "JASON_RELEASE_MOBILE_APPROVAL_MODE": "off",
    "JASON_RELEASE_MOBILE_APPROVAL_WORKER_ENABLED": "false",
}

CONTROLLER_SOURCE = Path(__file__).resolve()
CONTROL_STATE_SCHEMA_VERSION = "1.0"
USER_CONTROL_TIMERS = (
    "jason-release-manager.timer",
    "jason-support-repair-worker.timer",
    "jason-self-heal-watchdog.timer",
)
SYSTEM_CONTROL_TIMERS = (
    "jason-delegation-maintenance.timer",
    "jason-openclaw-authority-health.timer",
    "jason-openclaw-authority-full-integrity.timer",
    "jason-production-drift-watchdog.timer",
)


class ReleaseManagerError(RuntimeError):
    pass


class ReleaseManagerBusy(ReleaseManagerError):
    pass


class CCCCheckerUpgradeRequired(ReleaseManagerError):
    """A valid pre-mutation CCC report requires a separately authorized upgrade.

    This is a scheduled-release deferral, never permission to advance without
    current checker certification. Explicit/manual promote still raises.
    """


class CCCMaterialReviewRequired(ReleaseManagerError):
    """Exact-revision owner material review has not yet been recorded.

    Only the scheduled timer may defer cleanly. Direct promotion fails closed,
    and the CCC report remains NOT_PROVEN until a separately recorded review.
    """


def acquire_production_transaction_lock(
    repo: Path,
    state_root: Path,
    record: dict[str, Any],
):
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    schedule = policy.get("schedule") if isinstance(policy, dict) else {}
    schedule = schedule if isinstance(schedule, dict) else {}
    serialized = bool(schedule.get("serialized_promotion", False))
    maximum = int(schedule.get("max_concurrent_releases", 1) or 1)
    if not serialized or maximum != 1:
        raise ReleaseManagerError(
            "production transaction lock requires serialized_promotion=true and "
            "max_concurrent_releases=1"
        )

    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_root / "production-transaction.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip()[:500]
        handle.close()
        detail = f"; active transaction: {owner}" if owner else ""
        raise ReleaseManagerBusy(
            "another production release transaction is already active" + detail
        ) from exc

    metadata = {
        "release_id": str(record.get("release_id") or ""),
        "candidate_sha": str(
            (record.get("release_candidate") or {}).get("candidate_sha") or ""
        ),
        "pid": os.getpid(),
        "acquired_at": now(),
    }
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps(metadata, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def release_production_transaction_lock(handle) -> None:
    try:
        handle.seek(0)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


QUICKBOOKS_READ_PROFILES = frozenset({
    "quickbooks-sandbox-read-v1",
    "quickbooks-production-read-v1",
})


def declared_quickbooks_read_profile(candidate_worktree: Path) -> str | None:
    """Bind profile selection to the reviewed, immutable release source."""
    path = candidate_worktree / "config" / "quickbooks-read-profile.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "read_profile"}
            or payload.get("schema_version") != "1.0"
            or payload.get("read_profile") not in QUICKBOOKS_READ_PROFILES):
        raise ReleaseManagerError("candidate QuickBooks read profile declaration invalid")
    return str(payload["read_profile"])


AUTOTASK_PROVIDER_READ_PROFILES = frozenset({
    "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10",
    "itglue-autotask-entra-comprehensive-entity-read-catalog-v11",
    "itglue-autotask-entra-dynamic-schema-read-catalog-v13",
})


def declared_autotask_read_profiles(candidate_worktree: Path) -> tuple[str, str] | None:
    """Bind BOTH new source profile and rollback baseline to immutable Git."""
    path = candidate_worktree / "config" / "autotask-entity-read-profile.json"
    if path.is_symlink():
        raise ReleaseManagerError("Autotask profile declaration cannot be a symlink")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseManagerError("Autotask read profile declaration unreadable") from exc
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "read_profile", "rollback_read_profile"}
            or payload.get("schema_version") != "1.0"
            or payload.get("read_profile") not in AUTOTASK_PROVIDER_READ_PROFILES
            or payload.get("rollback_read_profile") not in AUTOTASK_PROVIDER_READ_PROFILES):
        raise ReleaseManagerError("candidate Autotask read profile declaration invalid")
    return str(payload["read_profile"]), str(payload["rollback_read_profile"])


def declared_autotask_read_profile(candidate_worktree: Path) -> str | None:
    pair = declared_autotask_read_profiles(candidate_worktree)
    return pair[0] if pair is not None else None



def live_autotask_read_profile() -> str:
    """Prove both live services have the same supported activation profile."""
    profiles = set()
    for name in ("jason-runtime", "jason-mcp-pilot"):
        env = json.loads(output([
            "docker", "inspect", name, "--format", "{{json .Config.Env}}",
        ]))
        if not isinstance(env, list):
            raise ReleaseManagerError("live Autotask profile environment unavailable")
        matching = [
            item.split("=", 1)[1] for item in env
            if isinstance(item, str)
            and item.startswith("JASON_PROVIDER_READ_ACTIVATION_PROFILE=")
        ]
        if len(matching) != 1 or matching[0] not in AUTOTASK_PROVIDER_READ_PROFILES:
            raise ReleaseManagerError("live Autotask read activation profile missing or invalid")
        profiles.add(matching[0])
    if len(profiles) != 1:
        raise ReleaseManagerError("live Runtime/MCP Autotask read profiles disagree")
    return profiles.pop()


def live_quickbooks_read_profile() -> str:
    """Require matching, supported read profiles from live Runtime and MCP."""
    profiles = set()
    for name in ("jason-runtime", "jason-mcp-pilot"):
        env = json.loads(output([
            "docker", "inspect", name, "--format", "{{json .Config.Env}}",
        ]))
        if not isinstance(env, list):
            raise ReleaseManagerError("live QuickBooks profile environment unavailable")
        matches = [
            item.split("=", 1)[1]
            for item in env
            if isinstance(item, str)
            and item.startswith("JASON_QUICKBOOKS_READ_PROFILE=")
        ]
        if len(matches) != 1 or matches[0] not in QUICKBOOKS_READ_PROFILES:
            raise ReleaseManagerError("live QuickBooks read profile missing or invalid")
        profiles.add(matches[0])
    if len(profiles) != 1:
        raise ReleaseManagerError("live Runtime and MCP QuickBooks profiles disagree")
    return profiles.pop()


def autotask_rollback_environment(
    env: dict[str, str], *, prior_autotask_profile: str
) -> dict[str, str]:
    """Use the exact immutable candidate's reviewed rollback profile.

    The v11 candidate script rejects a v10 *candidate activation* override,
    even during rollback. Its rollback-current image selects v10 internally,
    and this function supplies only an independently verified expectation.
    """
    if prior_autotask_profile not in AUTOTASK_PROVIDER_READ_PROFILES:
        raise ReleaseManagerError("rollback Autotask profile is unsupported")
    result = env.copy()
    result.pop("JASON_PROVIDER_READ_ACTIVATION_PROFILE", None)
    result["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] = prior_autotask_profile
    return result


def quickbooks_rollback_environment(
    env: dict[str, str], *, rollback_sha: str, prior_profile: str
) -> dict[str, str]:
    """Restore the old profile alongside the old images on rollback."""
    if prior_profile not in QUICKBOOKS_READ_PROFILES:
        raise ReleaseManagerError("rollback QuickBooks read profile is not supported")
    result = env.copy()
    result["JASON_RUNTIME_PRODUCTION_IMAGE"] = "jason-runtime:rollback-current"
    result["JASON_MCP_PRODUCTION_IMAGE"] = "jason-mcp:rollback-current"
    result["JASON_SOURCE_REVISION_OVERRIDE"] = rollback_sha
    result["JASON_QUICKBOOKS_READ_PROFILE"] = prior_profile
    return result


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def release_description(repo: Path, candidate_sha: str) -> str:
    try:
        value = run(["git", "show", "-s", "--format=%s", candidate_sha], cwd=repo)
    except Exception:
        value = "Jason production build " + candidate_sha[:12]
    value = " ".join(str(value or "").split()).strip()
    return (value or ("Jason production build " + candidate_sha[:12]))[:300]


def write_owner_notification_event(
    state_root: Path,
    record: dict[str, Any],
    event_type: str,
    *,
    owner_action: str = "",
) -> None:
    allowed = {
        "production_queue_entered",
        "production_owner_action_required",
        "production_queue_completed",
    }
    if event_type not in allowed:
        raise ReleaseManagerError("unsupported owner notification event")
    release_id = str(record.get("release_id") or "").strip()
    candidate = record.get("release_candidate") or {}
    candidate_sha = str(candidate.get("candidate_sha") or record.get("development", {}).get("source_sha") or "").strip()
    if not release_id or len(candidate_sha) != 40:
        return
    root = state_root / "owner-notification-events"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / f"{release_id}-{event_type}.json"
    if path.exists():
        return
    payload = {
        "schema_version": "1.0",
        "event_type": event_type,
        "release_id": release_id,
        "candidate_sha": candidate_sha,
        "description": str(record.get("description") or "")[:300],
        "change_class": str(record.get("change_class") or ""),
        "owner_action": str(owner_action or "")[:400],
        "created_at": now(),
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def production_window_open(at: datetime | None = None) -> bool:
    """Return whether unattended production promotion is currently permitted.

    The owner-approved production window is continuous 24x7. This function
    remains as the scheduler gate so future policy changes stay centralized.
    """
    observed = at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("production window evaluation requires timezone-aware time")
    return True


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def output(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def exact_sha(value: str, field: str) -> str:
    value = str(value or "").strip().casefold()
    if not SHA.fullmatch(value):
        raise ReleaseManagerError(f"{field} must be an exact 40-character git SHA")
    return value


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def record_id(candidate_sha: str) -> str:
    return "release-" + candidate_sha[:16]


def record_path(state_root: Path, release_id: str) -> Path:
    return state_root / "records" / f"{release_id}.json"


def load_record(state_root: Path, release_id: str) -> dict[str, Any]:
    path = record_path(state_root, release_id)
    if not path.exists():
        raise ReleaseManagerError(f"release record not found: {release_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_record(state_root: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = now()
    atomic_json(record_path(state_root, str(record["release_id"])), record)


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def control_state_path(state_root: Path) -> Path:
    return state_root / "production-control-state.json"


def _read_protected_snapshot(state_root: Path, filename: str) -> dict[str, Any]:
    """Read a fresh root-published snapshot; never trust stale breaker state."""
    snapshot = state_root / "protected-readback" / filename
    if not snapshot.is_file():
        raise ReleaseManagerError("protected release-state snapshot unavailable: " + filename)
    metadata = snapshot.stat()
    if time.time() - metadata.st_mtime > 90 or metadata.st_mtime > time.time() + 10:
        raise ReleaseManagerError("protected release-state snapshot stale: " + filename)
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != CONTROL_STATE_SCHEMA_VERSION:
        raise ReleaseManagerError("invalid protected release-state snapshot: " + filename)
    return payload


def load_control_state(state_root: Path) -> dict[str, Any]:
    path = control_state_path(state_root)
    if not path.exists():
        return {
            "schema_version": CONTROL_STATE_SCHEMA_VERSION,
            "circuit_breaker": {"state": "closed", "updated_at": now()},
            "last_known_good": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except PermissionError:
        payload = _read_protected_snapshot(state_root, "production-control-state.json")
    if str(payload.get("schema_version") or "") != CONTROL_STATE_SCHEMA_VERSION:
        raise ReleaseManagerError("production control-state schema is unsupported")
    return payload


def save_control_state(state_root: Path, payload: dict[str, Any]) -> None:
    path = control_state_path(state_root)
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ReleaseManagerError("protected production control state requires governed root write; refusing operator-owned replacement")
    payload["schema_version"] = CONTROL_STATE_SCHEMA_VERSION
    payload["updated_at"] = now()
    atomic_json(path, payload)


def unit_active(unit: str, *, user: bool) -> bool:
    args = ["systemctl"]
    env = None
    if user:
        args.append("--user")
        env = user_systemd_env()
    args.extend(["is-active", unit])
    completed = subprocess.run(
        args,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "active"


def scheduled_control_alignment() -> dict[str, str]:
    states: dict[str, str] = {}
    for unit in USER_CONTROL_TIMERS:
        active = unit_active(unit, user=True)
        states[unit] = "active" if active else "inactive"
        if not active:
            raise ReleaseManagerError(f"required user control timer is not active: {unit}")
    for unit in SYSTEM_CONTROL_TIMERS:
        active = unit_active(unit, user=False)
        states[unit] = "active" if active else "inactive"
        if not active:
            raise ReleaseManagerError(f"required system control timer is not active: {unit}")
    return states


# Only the preinstalled canonical recovery utility may produce the backup
# marker that permits the exact reviewed controller-copy transitional state.
# The root-owned host source and original last-known-good stay unchanged.
CONTROLLER_RECOVERY_MANAGED_REPO = Path("/home/al/.local/lib/jason/engineering-worker-source")
CONTROLLER_RECOVERY_OWNER_REVIEW = Path("/var/lib/jason/ccc/material-review.json")


def _controller_recovery_old_source_verified(source: Path) -> bool:
    return (
        source.is_file() and not source.is_symlink()
        and source.stat().st_uid == 0
    )


def _operator_recovery_identity(repo: Path, installed: Path, old_source: Path) -> dict[str, Any]:
    """Attest the one-time operator recovery copy against protected source.

    This is NOT a general alternate production controller. Only a copied
    canonical controller at the exact reviewed main revision, with the exact
    old immutable runner and installer-created backup, is accepted.
    """
    if not _controller_recovery_old_source_verified(old_source):
        raise ReleaseManagerError("controller recovery old source is not root immutable")
    old_digest = file_digest(old_source)
    backup = installed.with_name(
        installed.name + ".recovery-backup-" + old_digest[len("sha256:"):][:16]
    )
    if (not backup.is_file() or backup.is_symlink()
            or backup.stat().st_uid != os.geteuid()
            or backup.stat().st_mode & 0o077
            or file_digest(backup) != old_digest):
        raise ReleaseManagerError("canonical controller recovery backup missing or altered")

    managed = CONTROLLER_RECOVERY_MANAGED_REPO
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(managed), "rev-parse", "refs/remotes/origin/main"],
            stderr=subprocess.DEVNULL, timeout=12, text=True,
        ).strip()
        repo_sha = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=12, text=True,
        ).strip()
        expected = subprocess.check_output(
            ["git", "-C", str(managed), "show",
             f"{sha}:tools/release_manager_host_runner.py"],
            stderr=subprocess.DEVNULL, timeout=12,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseManagerError("controller recovery reviewed source unavailable") from exc
    if not SHA.fullmatch(sha) or repo_sha != sha:
        raise ReleaseManagerError("controller recovery exact main revision is not aligned")
    reviewed_digest = "sha256:" + hashlib.sha256(expected).hexdigest()
    candidate = repo / "tools" / "release_manager_host_runner.py"
    if (not candidate.is_file() or file_digest(candidate) != reviewed_digest
            or not installed.is_file() or installed.is_symlink()
            or installed.stat().st_uid != os.geteuid()
            or file_digest(installed) != reviewed_digest):
        raise ReleaseManagerError("controller recovery installed candidate differs from reviewed main")

    try:
        review = json.loads(CONTROLLER_RECOVERY_OWNER_REVIEW.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseManagerError("controller recovery exact owner review missing") from exc
    if (review.get("schema_version") != "1.0"
            or review.get("status") != "approved"
            or review.get("source_revision") != sha
            or review.get("recorded_by") != "person-al"):
        raise ReleaseManagerError("controller recovery exact owner review does not match source")
    return {
        "controller_recovery_mode": "canonical_owner_recovery",
        "controller_recovery_revision": sha,
        "controller_recovery_old_source": str(old_source),
        "controller_recovery_backup": str(backup),
        "controller_recovery_digest": reviewed_digest,
    }


def controller_identity(repo: Path) -> dict[str, Any]:
    policy_path = repo / "config" / "release-manager-policy.json"
    candidate_path = repo / "tools" / "release_manager_host_runner.py"
    if not policy_path.is_file():
        raise ReleaseManagerError("release-manager policy is missing")
    if not candidate_path.is_file():
        raise ReleaseManagerError("immutable candidate Production Manager source is missing")

    installed = Path.home() / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
    immutable = CONTROLLER_SOURCE
    # The systemd user timer executes a COPIED installed runner, not an
    # immutable /opt/jason/releases/<SHA>/tools path. A legitimate governed
    # install replaces that copied file while the old Python process is
    # running. Anchor N to its immutable release-manager-source BEFORE
    # mutation so the scheduled path can safely stage N+1 without losing N.
    if CONTROLLER_SOURCE == installed:
        source_link = installed.parent / "release-manager-source"
        if not source_link.is_symlink():
            raise ReleaseManagerError("active Release Manager immutable source link missing")
        immutable = source_link.resolve() / "tools" / "release_manager_host_runner.py"
        if not immutable.is_file():
            raise ReleaseManagerError("active Release Manager immutable source missing")
        if file_digest(immutable) != file_digest(installed):
            recovery = _operator_recovery_identity(repo, installed, immutable)
            return {
                "executing_controller_path": str(CONTROLLER_SOURCE),
                "executing_controller_immutable_path": str(installed),
                "executing_controller_revision": recovery["controller_recovery_revision"],
                "executing_controller_digest": recovery["controller_recovery_digest"],
                "candidate_controller_digest": file_digest(candidate_path),
                "policy_digest": file_digest(policy_path),
                "captured_at": now(),
                **recovery,
            }

    source_revision = immutable.parents[1].name.casefold()
    return {
        "executing_controller_path": str(CONTROLLER_SOURCE),
        "executing_controller_immutable_path": str(immutable),
        "executing_controller_revision": source_revision if SHA.fullmatch(source_revision) else "unknown",
        "executing_controller_digest": file_digest(immutable),
        "candidate_controller_digest": file_digest(candidate_path),
        "policy_digest": file_digest(policy_path),
        "captured_at": now(),
    }


def verify_controller_identity(
    pin: dict[str, Any], repo: Path, *, installed_candidate: bool = False,
    installed_runner: Path | None = None,
) -> dict[str, Any]:
    """Keep executing N immutable while verifying separately installed N+1.

    The active production transaction retains its flock and N's loaded code.
    The scheduled user service can replace the installed *copy* of the runner,
    but it must not alter the original immutable N source or policy.
    """
    if installed_candidate and pin.get("controller_recovery_mode") == "canonical_owner_recovery":
        # The root host reconciler may legitimately switch the source link to
        # new N+1. Verify the ORIGINAL recovery backup and root-owned N source
        # against the exact reviewed main Git object, independent of the link.
        recovered = _operator_recovery_identity(
            repo, CONTROLLER_SOURCE,
            Path(str(pin["controller_recovery_old_source"])),
        )
        if recovered != {key: pin.get(key) for key in recovered}:
            raise ReleaseManagerError("controller recovery provenance changed during promotion")
        candidate = repo / "tools" / "release_manager_host_runner.py"
        policy = repo / "config" / "release-manager-policy.json"
        current = {
            "executing_controller_path": str(CONTROLLER_SOURCE),
            "executing_controller_immutable_path": str(CONTROLLER_SOURCE),
            "executing_controller_revision": recovered["controller_recovery_revision"],
            "executing_controller_digest": recovered["controller_recovery_digest"],
            "candidate_controller_digest": file_digest(candidate),
            "policy_digest": file_digest(policy),
            "controller_recovery_mode": "canonical_owner_recovery",
        }
    elif installed_candidate:
        # Re-read immutable N from the pre-mutation pin, never infer the old
        # executing version from the installed file or retargeted source link.
        # Both are legitimately updated to N+1 by the guarded installer.
        immutable = Path(str(pin.get("executing_controller_immutable_path") or ""))
        policy = repo / "config" / "release-manager-policy.json"
        candidate = repo / "tools" / "release_manager_host_runner.py"
        if not immutable.is_file() or not policy.is_file() or not candidate.is_file():
            raise ReleaseManagerError("pinned controller, release policy or candidate missing")
        current = {
            "executing_controller_path": str(CONTROLLER_SOURCE),
            "executing_controller_immutable_path": str(immutable),
            "executing_controller_revision": (
                immutable.parents[1].name.casefold()
                if SHA.fullmatch(immutable.parents[1].name.casefold()) else "unknown"
            ),
            "executing_controller_digest": file_digest(immutable),
            "candidate_controller_digest": file_digest(candidate),
            "policy_digest": file_digest(policy),
        }
    else:
        current = controller_identity(repo)
    for field in (
        "executing_controller_path",
        "executing_controller_immutable_path",
        "executing_controller_revision",
        "executing_controller_digest",
        "candidate_controller_digest",
        "policy_digest",
    ):
        if current.get(field) != pin.get(field):
            raise ReleaseManagerError(f"active Production Manager controller changed mid-transaction: {field}")
    if installed_candidate:
        expected = pin["candidate_controller_digest"]
        installed_path = installed_runner or (
            Path.home() / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
        )
        if not installed_path.is_file() or file_digest(installed_path) != expected:
            raise ReleaseManagerError("installed Production Manager controller differs from candidate source")
        # Installer separately verifies source-link revision and immutable host
        # copy. No subprocess is run under candidate semantics in the active
        # transaction. Only future lock-acquiring invocations use N+1.
        current["installed_controller_path"] = str(installed_path)
        current["installed_controller_digest"] = expected
        current["controller_handoff"] = "staged_for_next_transaction"
    return current


def classify_change_risk(change_class: str, files: list[str]) -> str:
    paths = [str(value) for value in files]
    if any(
        path.startswith("tools/release_manager")
        or path in {
            "config/release-manager-policy.json",
            "config/production-desired-state.json",
            "tools/install_release_host_reconciler.py",
            "tools/install_release_control_transition.py",
            "tools/protected_root_policy_migration.py",
        }
        or path in {".dockerignore", "infrastructure/jason-runtime/Dockerfile"}
        or path in {
            "tools/reconcile_production_host_services.sh",
            "tools/reconcile_managed_unit_delta.py",
            "tools/release_exporter_port_guard.py",
            "tools/release_mobile_approval_consumer.py",
            "implementation/runtime_service/src/jason_runtime/mobile_release_approval.py",
            "implementation/runtime_service/src/jason_runtime/universal_teams_approval.py",
            "implementation/runtime_service/src/jason_runtime/playbook_autonomy_review.py",
            "implementation/connectors/microsoft_graph/teams_approval_channel.py",
        }
        or "release-host-reconcile" in path
        for path in paths
    ):
        return "production_control_core"
    if any(path.startswith("config/schemas/") or path.endswith(".schema.json") for path in paths):
        return "schema_or_contract"
    if change_class in {"support", "release_blocker", "production_incident"}:
        return "production_repair"
    return "normal"


def capture_production_manifest(expected_sha: str) -> dict[str, Any]:
    expected_sha = exact_sha(expected_sha, "expected_sha")
    alignment = live_production_alignment(expected_sha)
    runtime = live_runtime()
    mcp = live_mcp()
    manager_source = Path.home() / ".local" / "lib" / "jason" / "release-manager-source"
    manager_revision = "unknown"
    if manager_source.exists():
        manager_revision = manager_source.resolve().name.casefold()
    if manager_revision != expected_sha:
        raise ReleaseManagerError("Release Manager source revision is not aligned with production")
    timers = scheduled_control_alignment()
    return {
        "schema_version": "1.0",
        "revision": expected_sha,
        "runtime_revision": alignment["runtime_revision"],
        "runtime_image_id": runtime["image_id"],
        "mcp_revision": alignment["mcp_revision"],
        "mcp_image_id": mcp["image_id"],
        "host_revision": alignment["host_revision"],
        "host_release": alignment["host_release"],
        "release_manager_source_revision": manager_revision,
        "scheduled_control_units": timers,
        "desired_state_policy_digest": file_digest(
            Path("/opt/jason/current/config/production-desired-state.json")
        ) if Path("/opt/jason/current/config/production-desired-state.json").is_file() else None,
        "drift_evidence_path": "/var/lib/jason/openclaw/release-manager/production-drift.json",
        "complete": True,
        "observed_at": now(),
    }


def request_root_control_transition(state_root: Path, *, action: str, revision: str, release_id: str = "", reason: str = "") -> None:
    """Request a finite root-governed intent rather than write protected JSON."""
    if action not in {"open", "revalidate", "set_last_known_good"}:
        raise ReleaseManagerError("unsupported root-controlled release transition")
    revision = exact_sha(revision, "transition revision")
    request_id = uuid4().hex
    request_root = state_root / "protected-transitions"
    request_file = request_root / "requests" / (request_id + ".json")
    result_file = request_root / "results" / (request_id + ".json")
    if not request_file.parent.is_dir() or not result_file.parent.is_dir():
        raise ReleaseManagerError("governed root release transition worker not installed")
    atomic_json(request_file, {"request_id": request_id, "action": action, "revision": revision,
                               "release_id": release_id, "reason": reason[:300]})
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if result_file.is_file():
                data = json.loads(result_file.read_text(encoding="utf-8"))
                if data.get("request_id") != request_id or data.get("success") is not True:
                    raise ReleaseManagerError("governed root release transition rejected: " + str(data.get("detail") or "invalid response")[:350])
                if data.get("revision") != revision or data.get("action") != action:
                    raise ReleaseManagerError("governed root transition response identity mismatch")
                if control_state_path(state_root).stat().st_uid != 0:
                    raise ReleaseManagerError("governed root transition lost protected file ownership")
                return
            time.sleep(0.25)
        raise ReleaseManagerError("governed root transition result timed out")
    finally:
        result_file.unlink(missing_ok=True)


def set_last_known_good(
    state_root: Path,
    manifest: dict[str, Any],
    *,
    release_id: str,
) -> None:
    if control_state_path(state_root).exists() and control_state_path(state_root).stat().st_uid == 0 and os.geteuid() != 0:
        request_root_control_transition(state_root, action="set_last_known_good", revision=exact_sha(str(manifest.get("revision") or ""), "manifest revision"), release_id=release_id)
        return
    state = load_control_state(state_root)
    state["last_known_good"] = {
        "release_id": release_id,
        "manifest": manifest,
        "recorded_at": now(),
    }
    state["circuit_breaker"] = {
        "state": "closed",
        "reason": "production_verified",
        "updated_at": now(),
    }
    save_control_state(state_root, state)


def open_circuit_breaker(
    state_root: Path,
    record: dict[str, Any],
    *,
    reason: str,
    rollback_verified: bool,
) -> None:
    if control_state_path(state_root).exists() and control_state_path(state_root).stat().st_uid == 0 and os.geteuid() != 0:
        revision = exact_sha(str((record.get("release_candidate") or {}).get("candidate_sha") or ""), "candidate revision")
        request_root_control_transition(state_root, action="open", revision=revision, reason=reason)
        return
    state = load_control_state(state_root)
    state["circuit_breaker"] = {
        "state": "open",
        "reason": reason[:700],
        "release_id": str(record.get("release_id") or ""),
        "candidate_sha": str((record.get("release_candidate") or {}).get("candidate_sha") or ""),
        "rollback_verified": bool(rollback_verified),
        "opened_at": now(),
        "updated_at": now(),
    }
    save_control_state(state_root, state)


def revalidate_circuit_breaker(state_root: Path) -> dict[str, Any]:
    state = load_control_state(state_root)
    breaker = dict(state.get("circuit_breaker") or {})
    if breaker.get("state") != "open":
        return state
    lkg = dict(state.get("last_known_good") or {})
    manifest = dict(lkg.get("manifest") or {})
    revision = str(manifest.get("revision") or "")
    if not SHA.fullmatch(revision):
        raise ReleaseManagerError("production circuit breaker is open and no valid last-known-good manifest exists")
    try:
        verified = capture_production_manifest(revision)
    except Exception as exc:
        raise ReleaseManagerError(
            "production circuit breaker is open; authoritative health revalidation failed: " + str(exc)
        ) from exc
    if control_state_path(state_root).exists() and control_state_path(state_root).stat().st_uid == 0 and os.geteuid() != 0:
        request_root_control_transition(state_root, action="revalidate", revision=revision)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            snapshot = _read_protected_snapshot(state_root, "production-control-state.json")
            breaker = snapshot.get("circuit_breaker") or {}
            if breaker.get("state") == "closed" and breaker.get("revalidated_revision") == revision:
                return snapshot
            time.sleep(0.5)
        raise ReleaseManagerError("root-governed breaker transition succeeded but readback did not converge")
    state["circuit_breaker"] = {
        "state": "closed",
        "reason": "authoritative_health_revalidated",
        "revalidated_revision": revision,
        "revalidated_at": now(),
        "updated_at": now(),
    }
    state["last_revalidation"] = verified
    save_control_state(state_root, state)
    return state


def recover_missing_last_known_good(state_root: Path, revision: str, *, owner_approved: bool) -> dict[str, Any]:
    """Recover a lost baseline only when the live production and watchdog agree."""
    if not owner_approved:
        raise ReleaseManagerError("explicit owner approval required for baseline recovery")
    revision = exact_sha(revision, "revision")
    state = load_control_state(state_root)
    if (state.get("circuit_breaker") or {}).get("state") != "open":
        raise ReleaseManagerError("baseline recovery requires an open circuit breaker")
    if state.get("last_known_good"):
        raise ReleaseManagerError("baseline already exists; use normal revalidation")
    release_id = record_id(revision)
    record = load_record(state_root, release_id)
    production = record.get("production") or {}
    if record.get("state") != "closed" or not production.get("verified_at") or production.get("live_sha") != revision:
        raise ReleaseManagerError("no closed production-verified release record matches the baseline")
    # No state mutation before independent current desired-state and manifest checks.
    drift = production_drift_evidence(state_root)
    observed = str(drift.get("observed_at") or "")
    try:
        observation = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - observation).total_seconds()
    except (ValueError, TypeError):
        raise ReleaseManagerError("drift evidence timestamp missing or invalid")
    if observation.tzinfo is None or age < -30 or age > 300:
        raise ReleaseManagerError("drift evidence is not fresh")
    verified = capture_production_manifest(revision)
    if not verified.get("complete") or verified.get("revision") != revision:
        raise ReleaseManagerError("live production manifest is not independently verified")
    state["last_known_good"] = {"release_id": release_id, "manifest": verified, "recorded_at": now(), "recovered": True}
    state["circuit_breaker"] = {"state": "closed", "reason": "owner_approved_baseline_recovery_verified", "revalidated_revision": revision, "updated_at": now()}
    state["last_revalidation"] = verified
    save_control_state(state_root, state)
    return {"release_id": release_id, "revision": revision, "recovered": True, "verified_at": verified["observed_at"]}


def production_drift_evidence(state_root: Path) -> dict[str, Any]:
    path = state_root / "production-drift.json"
    if not path.is_file():
        raise ReleaseManagerError("production drift evidence is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except PermissionError:
        payload = _read_protected_snapshot(state_root, "production-drift.json")
    if str(payload.get("schema_version") or "") != "1.0":
        raise ReleaseManagerError("production drift evidence schema is invalid")
    if str(payload.get("status") or "") != "pass":
        problems = list(payload.get("problems") or [])
        raise ReleaseManagerError(
            f"production desired-state drift remains: {len(problems)} problem(s)"
        )
    return payload


def run_functional_smoke_tests(candidate_sha: str) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    alignment = live_production_alignment(candidate_sha)
    # Runtime 8080 is container-internal by design; the host does not publish
    # the port. Exercise the exact live container rather than host loopback.
    health_check = (
        "import urllib.request; "
        "response=urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=5); "
        "assert response.status == 200; print(response.status)"
    )
    status = int(output(["docker", "exec", "jason-runtime", "python", "-c", health_check]).strip())
    if status != 200:
        raise ReleaseManagerError(f"production runtime functional smoke returned HTTP {status}")
    if live_mcp()["revision"] != candidate_sha:
        raise ReleaseManagerError("production MCP functional smoke revision mismatch")
    return {
        "passed": True,
        "runtime_healthz_http_status": status,
        "runtime_mcp_host_alignment": True,
        "runtime_revision": alignment["runtime_revision"],
        "mcp_revision": alignment["mcp_revision"],
        "host_revision": alignment["host_revision"],
        "verified_at": now(),
    }


def live_runtime() -> dict[str, Any]:
    raw = json.loads(output(["docker", "inspect", "jason-runtime"]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    revision = str(labels.get("com.teamaot.jason.source_revision") or "").casefold()
    if not SHA.fullmatch(revision):
        raise ReleaseManagerError("live jason-runtime source revision is not an exact SHA")
    health = str((raw.get("State", {}).get("Health") or {}).get("Status") or "")
    if health != "healthy":
        raise ReleaseManagerError(f"live jason-runtime is not healthy: {health or 'unknown'}")
    return {
        "revision": revision,
        "image_id": str(raw["Image"]),
        "inspect": raw,
    }


def live_mcp() -> dict[str, Any]:
    raw = json.loads(output(["docker", "inspect", "jason-mcp-pilot"]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    revision = str(
        labels.get("com.teamaot.jason.source_revision") or ""
    ).casefold()
    if not SHA.fullmatch(revision):
        raise ReleaseManagerError(
            "live jason-mcp-pilot source revision is not an exact SHA"
        )
    if str(raw.get("State", {}).get("Status") or "") != "running":
        raise ReleaseManagerError("live jason-mcp-pilot is not running")
    return {
        "revision": revision,
        "image_id": str(raw["Image"]),
        "inspect": raw,
    }


def live_production_alignment(candidate_sha: str) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    runtime = live_runtime()
    mcp = live_mcp()
    mcp_revision = str(mcp["revision"])

    current_release = Path("/opt/jason/current").resolve()
    host_revision = current_release.name.casefold()
    if not SHA.fullmatch(host_revision):
        raise ReleaseManagerError("/opt/jason/current does not resolve to an exact SHA release")

    observed = {
        "runtime_revision": runtime["revision"],
        "mcp_revision": mcp_revision,
        "host_revision": host_revision,
        "host_release": str(current_release),
    }
    mismatches = [
        f"{name}={value}"
        for name, value in (
            ("runtime", observed["runtime_revision"]),
            ("mcp", observed["mcp_revision"]),
            ("host", observed["host_revision"]),
        )
        if value != candidate_sha
    ]
    if mismatches:
        raise ReleaseManagerError(
            "production alignment mismatch for candidate "
            + candidate_sha
            + ": "
            + ", ".join(mismatches)
        )
    return observed


def wait_live_runtime(attempts: int = 30, interval_seconds: int = 2) -> dict[str, Any]:
    last_health = "unknown"
    for _ in range(attempts):
        raw = json.loads(output(["docker", "inspect", "jason-runtime"]))[0]
        health = str((raw.get("State", {}).get("Health") or {}).get("Status") or "")
        last_health = health or "unknown"
        if health == "healthy":
            return live_runtime()
        if health == "unhealthy":
            break
        time.sleep(interval_seconds)
    raise ReleaseManagerError(
        f"live jason-runtime did not become healthy: {last_health}"
    )


def verify_candidate_on_main(repo: Path, candidate_sha: str) -> None:
    run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    run(["git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"], cwd=repo)
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, "origin/main"],
        cwd=repo,
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseManagerError("candidate SHA is not reachable from protected main")


def changed_files(repo: Path, rollback_sha: str, candidate_sha: str) -> list[str]:
    text = output(
        ["git", "diff", "--name-only", f"{rollback_sha}..{candidate_sha}"],
        cwd=repo,
    )
    return sorted(line.strip() for line in text.splitlines() if line.strip())


def required_checks(repo: Path) -> list[str]:
    config = json.loads(
        (repo / "config" / "development-release-coordinator.json").read_text(
            encoding="utf-8"
        )
    )
    return list(config.get("required_checks") or [])


def github_checks(candidate_sha: str, required: list[str]) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    # GitHub returns only 30 check runs by default. Busy merge SHAs can exceed
    # that easily (reruns/classifiers included), so required protected checks
    # may otherwise be falsely reported as missing. Traverse a bounded set of
    # 100-item pages and retain the newest run for each check name.
    for page in range(1, 11):
        url = (
            "https://api.github.com/repos/al-teamaot-com/jason/commits/"
            + candidate_sha
            + f"/check-runs?per_page=100&page={page}"
        )
        # Use the host's authenticated, read-only GitHub CLI rather than
        # anonymous REST requests, which are constrained by shared IP rate limits.
        endpoint = url.removeprefix("https://api.github.com/")
        payload = json.loads(output([
            "gh", "api", "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28", endpoint,
        ]))
        items = payload.get("check_runs") or []
        for item in items:
            name = str(item.get("name") or "")
            if name and (name not in latest or int(item.get("id", 0)) > int(latest[name].get("id", 0))):
                latest[name] = item
        if len(items) < 100:
            break
    else:
        raise ReleaseManagerError("GitHub check-run pagination exceeded bounded limit")
    failures = []
    for name in required:
        item = latest.get(name)
        if item is None:
            failures.append(name + ":missing")
        elif item.get("status") != "completed":
            failures.append(name + ":pending")
        elif item.get("conclusion") != "success":
            failures.append(name + ":" + str(item.get("conclusion")))
    return {
        "passed": not failures,
        "required": required,
        "failures": failures,
    }


def image_id(image: str) -> str:
    return output(["docker", "image", "inspect", image, "--format", "{{.Id}}"])


def worktree(repo: Path, state_root: Path, candidate_sha: str) -> Path:
    """Create a fresh, exact-SHA release worktree without deleting old ones.

    A previous deployment attempt may leave Git worktree registration behind.
    Reusing the same SHA-named path can then produce git exit 128 even when
    its directory was removed. Never blindly rmtree an existing checkout:
    every attempt receives a fresh, scoped worktree identity and Git owns
    its cleanup through remove_worktree().
    """
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    root = state_root / "worktrees"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or not root.is_dir():
        raise ReleaseManagerError("release worktree root is not a real directory")
    path = root / f"{candidate_sha}-{uuid4().hex[:12]}"
    if path.exists() or path.is_symlink():
        raise ReleaseManagerError("release worktree attempt path already exists")
    try:
        run(["git", "worktree", "add", "--detach", str(path), candidate_sha], cwd=repo)
    except subprocess.CalledProcessError as exc:
        detail = (str(exc.stdout or "")[-600:]).strip()
        raise ReleaseManagerError(
            "immutable release worktree materialization failed before production mutation: "
            + (detail or f"git exit {exc.returncode}")
        ) from exc
    return path


def remove_worktree(repo: Path, path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def build_candidate(repo: Path, state_root: Path, candidate_sha: str) -> tuple[str, str]:
    path = worktree(repo, state_root, candidate_sha)
    tag = f"jason-runtime:release-{candidate_sha[:12]}"
    try:
        run(
            [
                "docker", "build",
                "--label", f"org.opencontainers.image.revision={candidate_sha}",
                "--label", f"com.teamaot.jason.source_revision={candidate_sha}",
                "-t", tag,
                "-f", str(path / "infrastructure" / "jason-runtime" / "Dockerfile"),
                str(path),
            ]
        )
        # A Docker build can succeed even when a restrictive Git release
        # worktree leaves Python sources root-only in the resulting image.
        # Test the exact built artifact as the production UID/GID before a
        # preproduction state copy. No network, state mounts, secrets, or
        # provider connectors are available to this import-only smoke.
        run([
            "timeout", "--signal=TERM", "--kill-after=5s", "45s",
            "docker", "run", "--rm", "--pull", "never",
            "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m",
            "--user", "1000:1000", "--entrypoint", "python", tag,
            "-c", "from usage_ledger.ledger import SQLiteUsageLedger; import jason_runtime.main",
        ])
        return tag, image_id(tag)
    finally:
        remove_worktree(repo, path)


def build_mcp_candidate(
    repo: Path,
    state_root: Path,
    candidate_sha: str,
) -> tuple[str, str, str]:
    path = worktree(repo, state_root, candidate_sha)
    tag = f"jason-mcp:release-{candidate_sha[:12]}"
    # Stable governed base prevents stale source files from inheriting from live production.
    base = "jason-mcp:generic-governed-8f1e864947a2"
    base_id = image_id(base)
    try:
        run(
            [
                "docker", "build",
                "--pull=false",
                "--build-arg", f"BASE_IMAGE={base}",
                "--label", f"org.opencontainers.image.revision={candidate_sha}",
                "--label", f"com.teamaot.jason.source_revision={candidate_sha}",
                "-t", tag,
                "-f", str(path / "infrastructure" / "jason-mcp" / "Dockerfile"),
                str(path),
            ]
        )
        return tag, image_id(tag), base_id
    finally:
        remove_worktree(repo, path)


def user_systemd_env() -> dict[str, str]:
    env = os.environ.copy()
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault(
        "DBUS_SESSION_BUS_ADDRESS",
        f"unix:path=/run/user/{uid}/bus",
    )
    return env


def require_host_reconciler_ready(state_root: Path) -> None:
    root = state_root / "host-reconcile"
    requests = root / "requests"
    results = root / "results"
    if not requests.is_dir() or not results.is_dir():
        raise ReleaseManagerError(
            "root host reconciliation spool is not installed"
        )
    if not os.access(requests, os.W_OK) or not os.access(results, os.R_OK):
        raise ReleaseManagerError(
            "root host reconciliation spool permissions are unavailable"
        )
    worker = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
    if not worker.is_file():
        raise ReleaseManagerError("root host reconciliation worker is not installed")
    meta = worker.stat()
    if meta.st_uid != 0 or (meta.st_mode & 0o022):
        raise ReleaseManagerError(
            "root host reconciliation worker ownership/mode is unsafe"
        )
    completed = subprocess.run(
        ["systemctl", "is-active", "jason-release-host-reconcile.path"],
        env=user_systemd_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "active":
        raise ReleaseManagerError(
            "root host reconciliation path unit is not active"
        )


def request_host_reconcile(
    state_root: Path,
    source_revision: str,
    *,
    timeout_seconds: float = 420.0,
) -> dict[str, Any]:
    # The root worker may spend 200+ seconds activating system services,
    # followed by exporter checks and queue scheduling. Keep an absolute
    # finite deadline; never count a late result as an accepted release.
    source_revision = exact_sha(source_revision, "source_revision")
    require_host_reconciler_ready(state_root)
    request_id = "release-" + source_revision[:12] + "-" + uuid4().hex[:12]
    root = state_root / "host-reconcile"
    request_path = root / "requests" / f"{request_id}.json"
    result_path = root / "results" / f"{request_id}.json"
    atomic_json(
        request_path,
        {
            "request_id": request_id,
            "source_revision": source_revision,
            "requested_at": now(),
            "requested_by": "jason-release-manager",
        },
    )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if str(result.get("request_id") or "") != request_id:
                raise ReleaseManagerError(
                    "host reconciliation result request id mismatch"
                )
            if str(result.get("source_revision") or "").casefold() != source_revision:
                raise ReleaseManagerError(
                    "host reconciliation result revision mismatch"
                )
            if result.get("success") is not True:
                raise ReleaseManagerError(
                    "host reconciliation failed: "
                    + str(result.get("detail") or "unknown failure")[:600]
                )
            return result
        time.sleep(0.25)
    raise ReleaseManagerError("host reconciliation result timed out")




def verify_candidate_host_reconciliation_contract(
    deploy_worktree: Path, candidate_sha: str
) -> dict[str, bool]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    script = deploy_worktree / "tools" / "reconcile_production_host_services.sh"
    if not script.is_file():
        raise ReleaseManagerError("candidate host reconciliation script is missing")
    text = script.read_text(encoding="utf-8")
    developer_checkout = "/home/al/projects" + "/jason"
    if developer_checkout in text:
        raise ReleaseManagerError(
            "candidate host reconciliation script depends on developer checkout"
        )
    required = (
        'REPO_ROOT="/home/al/.local/lib/jason/engineering-source-repo"',
        'DOCUMENTATION_SOURCE_REPO="/home/al/.local/lib/jason/documentation-source-repo"',
        'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT',
        'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=',
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ReleaseManagerError(
            "candidate host reconciliation contract is incomplete: " + ",".join(missing)
        )
    return {
        "candidate_script_verified": True,
        "managed_engineering_source_verified": True,
        "managed_documentation_source_verified": True,
        "developer_checkout_absent": True,
    }


def verify_host_reconciliation_evidence(
    host_result: dict[str, Any], candidate_sha: str
) -> dict[str, bool]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    detail = str(host_result.get("detail") or "")
    required = (
        f"HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION={candidate_sha}",
        "MANAGED_ENGINEERING_SOURCE=PASS",
        "MANAGED_DOCUMENTATION_SOURCE=PASS",
        "DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT",
        "JASON_HOST_SERVICE_RECONCILIATION=PASS",
        "JASON_PRODUCTION_DRIFT_GUARD=PASS",
        "JASON_ROLLBACK_CONTAINER_RETENTION=PASS",
    )
    missing = [item for item in required if item not in detail]
    if missing:
        raise ReleaseManagerError(
            "host reconciliation evidence is incomplete: " + ",".join(missing)
        )
    return {
        "candidate_script_verified": True,
        "managed_engineering_source_verified": True,
        "managed_documentation_source_verified": True,
        "developer_checkout_absent": True,
    }


def install_release_manager_from_current(expected_sha: str) -> dict[str, Any]:
    expected_sha = exact_sha(expected_sha, "expected_sha")
    current = Path("/opt/jason/current").resolve()
    if current.name.casefold() != expected_sha:
        raise ReleaseManagerError(
            "immutable host release is not aligned before Release Manager install"
        )
    installer = current / "tools" / "install_release_manager.py"
    if not installer.is_file():
        raise ReleaseManagerError(
            "immutable Release Manager installer is missing"
        )
    output_text = run(
        ["/usr/bin/python3", str(installer), "--activate"],
        cwd=current,
        env=user_systemd_env(),
    )
    if "JASON_RELEASE_MANAGER_INSTALL=PASS" not in output_text:
        raise ReleaseManagerError("Release Manager installer did not report PASS")

    source_link = Path.home() / ".local" / "lib" / "jason" / "release-manager-source"
    if source_link.resolve().name.casefold() != expected_sha:
        raise ReleaseManagerError(
            "Release Manager source link is not bound to the immutable host release"
        )
    installed_runner = Path.home() / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
    expected_runner = current / "tools" / "release_manager_host_runner.py"
    if hashlib.sha256(installed_runner.read_bytes()).digest() != hashlib.sha256(
        expected_runner.read_bytes()
    ).digest():
        raise ReleaseManagerError("installed Release Manager runner differs from host release")

    timer = subprocess.run(
        ["systemctl", "--user", "is-active", "jason-release-manager.timer"],
        env=user_systemd_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if timer.returncode != 0 or timer.stdout.strip() != "active":
        raise ReleaseManagerError("Release Manager timer is not active after install")
    return {
        "source_revision": expected_sha,
        "timer_active": True,
        "source_link": str(source_link.resolve()),
    }


_PREPROD_OPENCLAW_EXCLUDED = frozenset({
    "orchestration-events.sqlite3",
    "orchestration-events.sqlite3-wal",
    "orchestration-events.sqlite3-shm",
})


def _preprod_sqlite_sidecar(name: str) -> bool:
    """Sidecars are transient; a consistent SQLite backup includes committed WAL."""
    return any(
        name.endswith(".sqlite3" + suffix)
        and len(name) > len(".sqlite3" + suffix)
        for suffix in ("-wal", "-shm", "-journal")
    )


def verified_live_openclaw_bind() -> Path:
    """Resolve only the real runtime's exact bind, never a developer checkout."""
    try:
        containers = json.loads(output(["docker", "inspect", "jason-runtime"]))
        mounts = containers[0]["Mounts"] if len(containers) == 1 else []
        matches = [mount for mount in mounts
                   if mount.get("Type") == "bind"
                   and mount.get("Destination") == "/var/lib/jason/openclaw"
                   and mount.get("RW") is True]
        if len(matches) != 1:
            raise ReleaseManagerError("live OpenClaw bind identity is ambiguous")
        path = Path(matches[0]["Source"])
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ReleaseManagerError("live OpenClaw bind is unsafe")
        return path
    except (IndexError, TypeError, KeyError, ValueError, OSError) as exc:
        raise ReleaseManagerError("live OpenClaw bind cannot be verified") from exc


def transactional_preprod_sqlite_backup(source: Path, target: Path) -> None:
    """Read committed data, including WAL, into a private consistent snapshot.

    Never copy raw journal/WAL files out from under SQLite writers. Use the
    SQLite online backup API against the proven live bind, with a readonly
    connection and a separate isolated target. No live process is restarted.
    """
    if (source.suffix != ".sqlite3" or source.is_symlink()
            or not source.is_file() or target.exists() or target.is_symlink()):
        raise ReleaseManagerError("live SQLite source or isolated target is unsafe")
    try:
        uri = source.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=4.0)) as live:
            live.execute("PRAGMA query_only=ON")
            pages = int(live.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(live.execute("PRAGMA page_size").fetchone()[0])
            estimate = pages * page_size
            if (estimate > _PREPROD_CLONE_MAX_BYTES
                    or shutil.disk_usage(target.parent).free <
                    estimate + _PREPROD_DISK_RESERVE_BYTES):
                raise ReleaseManagerError("SQLite snapshot exceeds bounded isolated capacity")
            started = time.monotonic()
            def bounded_progress(status: int, remaining: int, total: int) -> None:
                if time.monotonic() - started > 120:
                    raise ReleaseManagerError("SQLite snapshot exceeded bounded time")
            with closing(sqlite3.connect(str(target), timeout=4.0)) as clone:
                live.backup(clone, pages=128, progress=bounded_progress, sleep=0.1)
                # An online backup of a WAL-mode source inherits the WAL-mode
                # header. Convert ONLY this isolated target to a self-contained
                # DELETE journal database, never touch the live source.
                mode = clone.execute("PRAGMA journal_mode=DELETE").fetchone()
                if mode is None or mode[0].lower() != "delete":
                    raise ReleaseManagerError("isolated SQLite snapshot is not self-contained")
        target.chmod(0o600)
    except (sqlite3.Error, OSError, ValueError, ReleaseManagerError) as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc, ReleaseManagerError):
            raise
        raise ReleaseManagerError("transactional preprod SQLite snapshot failed") from exc


_PREPROD_CLONE_MAX_BYTES = 4 * 1024**3
_PREPROD_DISK_RESERVE_BYTES = 3 * 1024**3
# These are recursively nested *snapshots/build trees*, not operational
# release/approval state. Re-cloning them multiplies prior preprod snapshots
# and can exceed the bounded isolation disk budget even on a healthy host.
_PREPROD_RELEASE_SCRATCH_EXCLUDED = frozenset({"preprod", "worktrees"})
_PREPROD_REQUIRED_RELEASE_RECORDS = frozenset({
    "records", "protected-readback", "production-control-state.json",
})


def bounded_preprod_openclaw_entries(raw: str) -> list[str]:
    """Exclude only the large append-only event journal, not authority data."""
    entries = raw.splitlines()
    if not entries or len(entries) > 256:
        raise ReleaseManagerError("invalid preproduction OpenClaw state listing")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}
           for name in entries) or len(set(entries)) != len(entries):
        raise ReleaseManagerError("unsafe preproduction OpenClaw state name")
    return [
        name for name in entries
        if name not in _PREPROD_OPENCLAW_EXCLUDED
        and not _preprod_sqlite_sidecar(name)
    ]


def bounded_preprod_release_manager_entries(raw: str) -> list[str]:
    """Copy operational release evidence but not stale isolated/build caches."""
    # Reuse the exact same bounded container-name and traversal validation as
    # the OpenClaw top level. Missing protected evidence fails closed.
    names = bounded_preprod_openclaw_entries(raw)
    if not _PREPROD_REQUIRED_RELEASE_RECORDS.issubset(names):
        raise ReleaseManagerError("preproduction release-manager critical state missing")
    return [name for name in names
            if name not in _PREPROD_RELEASE_SCRATCH_EXCLUDED]


def copy_state_from_live_container(
    container_path: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if container_path == "/var/lib/jason/openclaw":
        # Non-SQLite state copies from the live container; selected SQLite
        # databases use the readonly online backup API against the verified
        # live container bind, never a mutable developer checkout. A whole-tree
        # docker cp would also multiply years of append-only event history.
        free_at_start = shutil.disk_usage(destination).free
        if free_at_start < _PREPROD_CLONE_MAX_BYTES + _PREPROD_DISK_RESERVE_BYTES:
            raise ReleaseManagerError("insufficient disk headroom for isolated preproduction state")
        names = bounded_preprod_openclaw_entries(run([
            "docker", "exec", "jason-runtime", "python", "-c",
            "import os; print('\\n'.join(sorted(os.listdir('/var/lib/jason/openclaw'))))",
        ]))
        def verify_disk_budget() -> None:
            free_now = shutil.disk_usage(destination).free
            if (free_now < _PREPROD_DISK_RESERVE_BYTES
                    or free_at_start - free_now > _PREPROD_CLONE_MAX_BYTES):
                raise ReleaseManagerError("isolated preproduction state exceeded bounded disk capacity")

        def guarded_copy(source: str, target: Path) -> None:
            run(["docker", "cp", f"jason-runtime:{source}", str(target)])
            verify_disk_budget()

        live_sqlite_bind: Path | None = None

        for name in names:
            if name == "release-manager":
                # Do not recursively copy previous preprod snapshots and
                # Git worktree caches nested inside the release-manager
                # operational directory. Preserve every other bounded entry,
                # including release records, approvals and protected readback.
                nested = bounded_preprod_release_manager_entries(run([
                    "docker", "exec", "jason-runtime", "python", "-c",
                    "import os; print('\\n'.join(sorted(os.listdir('/var/lib/jason/openclaw/release-manager'))))",
                ]))
                target = destination / name
                target.mkdir(mode=0o700)
                for child in nested:
                    guarded_copy(container_path + "/" + name + "/" + child,
                                 target / child)
            elif name.endswith(".sqlite3"):
                # Verify the bind at first use, and refuse any ambiguous bind.
                # The backup API includes committed WAL without racing a
                # disappearing -wal, -shm or -journal sidecar.
                if live_sqlite_bind is None:
                    live_sqlite_bind = verified_live_openclaw_bind()
                transactional_preprod_sqlite_backup(
                    live_sqlite_bind / name, destination / name,
                )
                verify_disk_budget()
            else:
                guarded_copy(container_path + "/" + name, destination / name)
        if (destination / "release-manager").is_dir() and any(
            (destination / "release-manager" / name).exists()
            for name in _PREPROD_RELEASE_SCRATCH_EXCLUDED
        ):
            raise ReleaseManagerError("preproduction release cache isolation failed")
        if any((destination / name).exists() for name in _PREPROD_OPENCLAW_EXCLUDED):
            raise ReleaseManagerError("excluded production event journal was copied")
        if any(_preprod_sqlite_sidecar(name) for name in os.listdir(destination)):
            raise ReleaseManagerError("isolated preproduction SQLite sidecar was copied")
        # Runtime startup initializes a fresh isolated orchestration journal.
        return
    run(
        [
            "docker",
            "cp",
            f"jason-runtime:{container_path}/.",
            str(destination),
        ]
    )


def preprod_scratch_path(state_root: Path, release_id: str) -> Path:
    return state_root.parent.parent / "release-manager-preprod" / release_id


def _preprod_cleanup_on_failure(function):
    """Remove only canonical scratch and preprod container on partial failure."""
    def guarded(*, state_root: Path, release_id: str, candidate_sha: str, **kwargs):
        try:
            return function(state_root=state_root, release_id=release_id,
                            candidate_sha=candidate_sha, **kwargs)
        except BaseException:
            if (re.fullmatch(r"release-[0-9a-f]{16}(?:-retry-[1-9][0-9]{0,2})?", release_id)
                    and SHA.fullmatch(candidate_sha)):
                scratch = preprod_scratch_path(state_root, release_id)
                expected = state_root.parent.parent / "release-manager-preprod"
                if scratch.parent.resolve() == expected.resolve() and not scratch.is_symlink():
                    shutil.rmtree(scratch, ignore_errors=True)
                subprocess.run(["docker", "rm", "-f",
                                "jason-runtime-preprod-" + candidate_sha[:12]],
                               check=False, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            raise
    return guarded


@_preprod_cleanup_on_failure
def create_preprod_container(
    *,
    live: dict[str, Any],
    candidate_image: str,
    candidate_sha: str,
    state_root: Path,
    release_id: str,
) -> tuple[str, Path]:
    src = live["inspect"]
    name = "jason-runtime-preprod-" + candidate_sha[:12]
    subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Pre-production clones must live outside the live OpenClaw state tree.
    # Production state_root is /var/lib/jason/openclaw/release-manager; placing
    # scratch below state_root recursively copies the destination back into
    # itself when cloning /var/lib/jason/openclaw.
    scratch = preprod_scratch_path(state_root, release_id)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, mode=0o700)

    mount_sources: dict[str, str] = {}
    for mount in src.get("Mounts") or []:
        destination = str(mount.get("Destination") or "")
        source = str(mount.get("Source") or "")
        if destination in {"/var/lib/jason/authority", "/var/lib/jason/openclaw"}:
            clone = scratch / destination.rsplit("/", 1)[-1]
            source_path = Path(source).resolve()
            clone_path = clone.resolve()
            if clone_path == source_path or source_path in clone_path.parents:
                raise ReleaseManagerError(
                    f"pre-production clone destination is nested under live state source: {destination}"
                )
            try:
                copy_state_from_live_container(destination, clone)
            except BaseException:
                # A failed state clone must never leave its temporary bytes on disk.
                shutil.rmtree(scratch, ignore_errors=True)
                raise
            mount_sources[destination] = str(clone)

    config = src["Config"]
    host = src["HostConfig"]
    env_map: dict[str, str] = {}
    for item in config.get("Env") or []:
        if "=" in item:
            key, value = item.split("=", 1)
            env_map[key] = value
    env_map["JASON_SOURCE_REVISION"] = candidate_sha
    env_map.update(MUTATION_ENV_OVERRIDES)

    args = ["docker", "create", "--name", name, "--restart", "no"]
    if config.get("User"):
        args += ["--user", config["User"]]
    if config.get("WorkingDir"):
        args += ["--workdir", config["WorkingDir"]]
    if host.get("ReadonlyRootfs"):
        args += ["--read-only"]
    for capability in host.get("CapDrop") or []:
        args += ["--cap-drop", capability]
    for option in host.get("SecurityOpt") or []:
        args += ["--security-opt", option]
    for destination, options in (host.get("Tmpfs") or {}).items():
        args += ["--tmpfs", f"{destination}:{options}"]
    for key, value in sorted(env_map.items()):
        args += ["--env", f"{key}={value}"]

    skipped_nested: set[str] = set()
    for mount in src.get("Mounts") or []:
        mtype = str(mount.get("Type") or "")
        source = str(mount.get("Source") or "")
        destination = str(mount.get("Destination") or "")
        writable = bool(mount.get("RW", False))
        if destination.startswith("/var/lib/jason/openclaw/"):
            skipped_nested.add(destination)
            continue
        if destination in mount_sources:
            source = mount_sources[destination]
            mtype = "bind"
            writable = True
        spec = f"type={mtype},src={source},dst={destination}"
        if not writable:
            spec += ",readonly"
        args += ["--mount", spec]

    primary_network = str(host.get("NetworkMode") or "")
    if primary_network and primary_network not in {"default", "bridge"}:
        args += ["--network", primary_network]

    labels = dict(config.get("Labels") or {})
    labels["org.opencontainers.image.revision"] = candidate_sha
    labels["com.teamaot.jason.source_revision"] = candidate_sha
    labels["com.teamaot.jason.deployment-purpose"] = "preproduction"
    for key, value in sorted(labels.items()):
        args += ["--label", f"{key}={value}"]

    health = config.get("Healthcheck") or {}
    test = health.get("Test") or []
    if test:
        if test[0] == "CMD-SHELL":
            args += ["--health-cmd", test[1]]
        elif test[0] == "CMD":
            args += ["--health-cmd", " ".join(test[1:])]
    args.append(candidate_image)

    run(args, env=os.environ.copy())
    secondary = [
        network
        for network in sorted((src.get("NetworkSettings", {}).get("Networks") or {}))
        if network != primary_network
    ]
    for network in secondary:
        run(["docker", "network", "connect", network, name])
    return name, scratch


def preprod_failure_state(name: str) -> str:
    """Return narrowly bounded diagnostic fields, never container logs/env.

    A rejected isolated health check currently deletes the test container;
    preserve only its state/exit information for a safe actionable error.
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .State}}", name],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=5, check=False,
        )
        if result.returncode != 0:
            return "container_state=unavailable"
        record = json.loads(result.stdout)
        if not isinstance(record, dict):
            return "container_state=unavailable"
        status = str(record.get("Status") or "unknown")
        exit_code = record.get("ExitCode")
        oom_killed = record.get("OOMKilled")
        health = (record.get("Health") or {}).get("Status")
        if status not in {"created", "running", "restarting", "exited", "dead", "paused"}:
            status = "unknown"
        if type(exit_code) is not int:
            exit_code = "unknown"
        if type(oom_killed) is not bool:
            oom_killed = "unknown"
        if health not in {None, "starting", "healthy", "unhealthy"}:
            health = "unknown"
        return (
            f"container_state={status} exit_code={exit_code} "
            f"oom_killed={oom_killed} health={health or 'none'}"
        )
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return "container_state=unavailable"


def wait_health(name: str, attempts: int = 30) -> None:
    script = (
        "import urllib.request; "
        "r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3); "
        "assert r.status == 200"
    )
    for _ in range(attempts):
        result = subprocess.run(
            ["docker", "exec", name, "python", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise ReleaseManagerError(
        "pre-production candidate failed health acceptance: "
        + preprod_failure_state(name)
    )


def verify_preprod_env(name: str, candidate_sha: str) -> None:
    raw = json.loads(output(["docker", "inspect", name]))[0]
    labels = raw.get("Config", {}).get("Labels") or {}
    if labels.get("com.teamaot.jason.source_revision") != candidate_sha:
        raise ReleaseManagerError("pre-production source revision mismatch")
    env = dict(
        item.split("=", 1)
        for item in raw.get("Config", {}).get("Env") or []
        if "=" in item
    )
    for key, expected in MUTATION_ENV_OVERRIDES.items():
        if env.get(key, "") != expected:
            raise ReleaseManagerError(f"pre-production mutation guard mismatch: {key}")


def native_deploy_environment(
    candidate_tree: Path,
    runtime_image: str,
    mcp_image: str,
    candidate_sha: str,
    *,
    worker_uid: str | None = None,
) -> dict[str, str]:
    """Build the SAME exact source-bound environment in preprod and promotion.

    The runtime and MCP scripts compare the rollback-profile environment to
    the immutable source declaration. Validate this against the REAL live LKG
    before advertising readiness, never after a live deployment starts.
    """
    env = os.environ.copy()
    env["JASON_RUNTIME_PRODUCTION_IMAGE"] = runtime_image
    env["JASON_MCP_PRODUCTION_IMAGE"] = mcp_image
    env["JASON_SOURCE_REVISION_OVERRIDE"] = exact_sha(candidate_sha, "candidate_sha")
    if worker_uid is not None:
        env[worker_enrollment.ENV_NAME] = worker_uid
    declared = declared_autotask_read_profiles(candidate_tree)
    if declared is not None:
        source_profile, declared_rollback = declared
        actual_live = live_autotask_read_profile()
        if actual_live != declared_rollback:
            raise ReleaseManagerError(
                "source-declared Autotask rollback profile disagrees with verified live LKG"
            )
        if os.environ.get("JASON_PROVIDER_READ_ACTIVATION_PROFILE") not in (None, source_profile):
            raise ReleaseManagerError("invoking Autotask profile override conflicts with immutable candidate")
        if os.environ.get("JASON_PROVIDER_READ_ROLLBACK_PROFILE") not in (None, declared_rollback):
            raise ReleaseManagerError("invoking Autotask rollback override conflicts with immutable candidate")
        env["JASON_PROVIDER_READ_ACTIVATION_PROFILE"] = source_profile
        env["JASON_PROVIDER_READ_ROLLBACK_PROFILE"] = declared_rollback
    quickbooks = declared_quickbooks_read_profile(candidate_tree)
    if quickbooks is not None:
        if os.environ.get("JASON_QUICKBOOKS_READ_PROFILE") not in (None, quickbooks):
            raise ReleaseManagerError("invoking QuickBooks profile override conflicts with immutable candidate")
        env["JASON_QUICKBOOKS_READ_PROFILE"] = quickbooks
    return env


_NATIVE_DEPLOY_CONTRACT_KEYS = (
    "JASON_RUNTIME_PRODUCTION_IMAGE",
    "JASON_MCP_PRODUCTION_IMAGE",
    "JASON_SOURCE_REVISION_OVERRIDE",
    "JASON_PROVIDER_READ_ACTIVATION_PROFILE",
    "JASON_PROVIDER_READ_ROLLBACK_PROFILE",
    "JASON_QUICKBOOKS_READ_PROFILE",
)


def native_deploy_contract_digest(env: Mapping[str, str]) -> str:
    """Attest only non-secret, source-bound values shared by both scripts."""
    scope = {key: str(env.get(key, "")) for key in _NATIVE_DEPLOY_CONTRACT_KEYS}
    raw = json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def production_preflight(
    repo: Path,
    state_root: Path,
    image: str,
    mcp_image: str,
    candidate_sha: str,
) -> str:
    require_host_reconciler_ready(state_root)
    candidate_tree = worktree(repo, state_root, candidate_sha)
    try:
        env = native_deploy_environment(candidate_tree, image, mcp_image, candidate_sha)
        run(
            [
                str(
                    candidate_tree
                    / "infrastructure"
                    / "jason-runtime"
                    / "production-deploy.sh"
                ),
                "--preflight",
            ],
            cwd=candidate_tree,
            env=env,
        )
        run(
            [
                str(
                    candidate_tree
                    / "infrastructure"
                    / "jason-mcp"
                    / "production-deploy.sh"
                ),
                "--preflight",
            ],
            cwd=candidate_tree,
            env=env,
        )
        return native_deploy_contract_digest(env)
    finally:
        remove_worktree(repo, candidate_tree)


SUPPORT_ACTIVE_PHASES = frozenset(
    {
        "diagnosing",
        "implementing",
        "ci_repair_needed",
        "ci_repairing",
        "pr_validating",
        "merged_waiting_deployment",
        "production_verifying",
        "closure_validating",
        "closure_merging",
    }
)
SUPPORT_ID_IN_TITLE = re.compile(r"\b(SUPPORT-[A-Z]+-[A-Z0-9]+)\b")


def open_support_issue_ids(repo: Path) -> set[str]:
    raw = run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--search",
            "SUPPORT- in:title",
            "--limit",
            "100",
            "--json",
            "title",
        ],
        cwd=repo,
    )
    values = json.loads(raw) if raw else []
    result: set[str] = set()
    for issue in values if isinstance(values, list) else []:
        title = str(issue.get("title") or "") if isinstance(issue, dict) else ""
        match = SUPPORT_ID_IN_TITLE.search(title)
        if match:
            result.add(match.group(1).upper())
    return result


def verify_support_release_binding(
    repo: Path, candidate_sha: str, support_item: str | None,
    support_pr_number: int | None,
) -> dict[str, Any]:
    """Validate exact, open Support item and reviewed merged PR provenance."""
    candidate_sha = exact_sha(candidate_sha, 'candidate_sha')
    if (not isinstance(support_item, str)
            or SUPPORT_ID_IN_TITLE.fullmatch(support_item) is None
            or type(support_pr_number) is not int or support_pr_number < 1):
        raise ReleaseManagerError('support release requires exact Support and PR identities')
    listed = gate.parse_support((repo / 'SUPPORT.md').read_text(encoding='utf-8'))
    if support_item not in {item['id'] for item in listed}:
        raise ReleaseManagerError('support item is absent from current Support List')
    raw = run([
        'gh', 'pr', 'view', str(support_pr_number),
        '--json', 'number,state,mergedAt,mergeCommit,body',
    ], cwd=repo)
    try:
        pr = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ReleaseManagerError('support PR evidence malformed') from exc
    if not isinstance(pr, dict):
        raise ReleaseManagerError('support PR evidence not an object')
    commit = pr.get('mergeCommit') or {}
    if (not isinstance(commit, dict) or type(pr.get('number')) is not int
            or pr['number'] != support_pr_number
            or pr.get('state') != 'MERGED'
            or not pr.get('mergedAt')
            or commit.get('oid') != candidate_sha):
        raise ReleaseManagerError('support PR is not the exact merged release SHA')
    body = str(pr.get('body') or '')
    heading = re.findall(
        rf'(?m)^## +{re.escape(support_item)} +/ +#([1-9][0-9]*) *$',
        body,
    )
    labelled = re.findall(
        rf'(?im)^- *Support item: *{re.escape(support_item)} *$',
        body,
    )
    reference = re.findall(
        r'(?im)^- *Support issue: *#([1-9][0-9]*) *$',
        body,
    )
    matches = heading if heading else (reference if labelled else [])
    if len(matches) != 1:
        raise ReleaseManagerError('support PR lacks a unique canonical Support issue')
    issue_number = int(matches[0])
    raw = run([
        'gh', 'issue', 'view', str(issue_number),
        '--json', 'number,state,title',
    ], cwd=repo)
    try:
        issue = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ReleaseManagerError('support issue evidence malformed') from exc
    if not isinstance(issue, dict):
        raise ReleaseManagerError('support issue evidence not an object')
    marker = SUPPORT_ID_IN_TITLE.search(str(issue.get('title') or ''))
    if (type(issue.get('number')) is not int
            or issue['number'] != issue_number
            or issue.get('state') != 'OPEN'
            or marker is None or marker.group(1) != support_item):
        raise ReleaseManagerError('support issue is not open and bound to the Support ID')
    return {
        'support_item': support_item,
        'support_pr_number': support_pr_number,
        'support_issue_number': issue_number,
        'support_merge_sha': candidate_sha,
    }


def support_repair_state_context(state_root: Path) -> tuple[list[str], list[str]]:
    path = state_root.parent / "support-repair" / "state.json"
    if not path.exists():
        return [], []
    value = json.loads(path.read_text(encoding="utf-8"))
    items = value.get("items") if isinstance(value, dict) else {}
    if not isinstance(items, dict):
        return [], []
    active = sorted(
        str(item_id)
        for item_id, record in items.items()
        if isinstance(record, dict)
        and str(record.get("phase") or "") in SUPPORT_ACTIVE_PHASES
    )
    blocked = sorted(
        str(item_id)
        for item_id, record in items.items()
        if isinstance(record, dict)
        and str(record.get("phase") or "") == "blocked"
    )
    return active, blocked


def gate_transition(
    repo: Path,
    state_root: Path,
    record: dict[str, Any],
    target: str,
) -> None:
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    support = gate.parse_support(
        (repo / "SUPPORT.md").read_text(encoding="utf-8")
    )
    if (
        target == "development"
        and str(record.get("change_class") or "")
        in {"todo", "feature", "enhancement"}
    ):
        eligible_support = open_support_issue_ids(repo)
        support = [
            item for item in support
            if item["id"] in eligible_support
        ]
        active_support, blocked_support = support_repair_state_context(state_root)
        record["active_support_repairs"] = active_support
        record["blocked_support_repairs"] = blocked_support
        record["eligible_support_items"] = sorted(eligible_support)
    todos = gate.parse_todos(
        (repo / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md").read_text(
            encoding="utf-8"
        )
    )
    result = gate.evaluate_transition(
        record,
        target,
        policy,
        support_items=support,
        todos=todos,
    )
    if not result["allowed"]:
        raise ReleaseManagerError(
            f"release transition {record.get('state')} -> {target} rejected: "
            + "; ".join(result["reasons"])
        )
    record["state"] = target
    record.setdefault("history", []).append(
        {"at": now(), "state": target, "gate": "pass"}
    )


def create_record(
    *,
    repo: Path,
    state_root: Path,
    candidate_sha: str,
    rollback_sha: str,
    change_class: str,
    owner_approved: bool,
    support_item: str | None = None,
    support_pr_number: int | None = None,
    release_id_override: str | None = None,
) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    rollback_sha = exact_sha(rollback_sha, "rollback_sha")
    alignment = live_production_alignment(rollback_sha)
    if alignment["runtime_revision"] != rollback_sha:
        raise ReleaseManagerError(
            "rollback SHA must equal the exact aligned production revision"
        )
    verify_candidate_on_main(repo, candidate_sha)
    if change_class == 'support':
        binding = verify_support_release_binding(
            repo, candidate_sha, support_item, support_pr_number,
        )
    else:
        if support_item is not None or support_pr_number is not None:
            raise ReleaseManagerError('non-Support releases cannot claim Support identity')
        binding = {}
    files = changed_files(repo, rollback_sha, candidate_sha)
    checks = github_checks(candidate_sha, required_checks(repo))
    if not checks["passed"]:
        raise ReleaseManagerError(
            "required protected checks are not green: " + ", ".join(checks["failures"])
        )

    release_id = release_id_override or record_id(candidate_sha)
    if release_id_override and not re.fullmatch(re.escape(record_id(candidate_sha)) + r"-retry-[1-9][0-9]{0,2}", release_id_override):
        raise ReleaseManagerError("invalid recovery attempt identity")
    risk_profile = classify_change_risk(change_class, files)
    record = {
        "schema_version": "2.0",
        "release_id": release_id,
        "state": "requested",
        "change_class": change_class,
        **binding,
        "description": release_description(repo, candidate_sha),
        "risk_profile": risk_profile,
        "created_at": now(),
        "updated_at": now(),
        "rollback_sha": rollback_sha,
        "changed_files": files,
        "active_support_repairs": [],
        "support_impact": {"checked": True, "blocking_items": []},
        "development": {
            "source_sha": candidate_sha,
            "tests_passed": True,
            "required_checks_passed": True,
            "check_summary": checks,
        },
        "owner_approval": {
            "approved": bool(owner_approved),
            "candidate_sha": candidate_sha if owner_approved else None,
            "source": "explicit_owner_instruction" if owner_approved else None,
            "recorded_at": now() if owner_approved else None,
        },
        "history": [{"at": now(), "state": "requested", "gate": "created"}],
    }
    gate_transition(repo, state_root, record, "development")
    gate_transition(repo, state_root, record, "dev_verified")

    image, digest = build_candidate(repo, state_root, candidate_sha)
    mcp_image, mcp_digest, mcp_base_digest = build_mcp_candidate(
        repo,
        state_root,
        candidate_sha,
    )
    record["release_candidate"] = {
        "candidate_sha": candidate_sha,
        "artifact_digest": digest,
        "image": image,
        "mcp_artifact_digest": mcp_digest,
        "mcp_image": mcp_image,
        "mcp_base_artifact_digest": mcp_base_digest,
        "immutable": True,
        "built_at": now(),
        "provenance": {
            "source_sha": candidate_sha,
            "builder_host": os.uname().nodename,
            "builder_process": "release_manager_host_runner",
            "runtime_artifact_digest": digest,
            "mcp_artifact_digest": mcp_digest,
            "policy_digest": file_digest(repo / "config" / "release-manager-policy.json"),
            "desired_state_policy_digest": file_digest(
                repo / "config" / "production-desired-state.json"
            ),
        },
    }
    record["release_manifest"] = {
        "schema_version": "1.0",
        "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha,
        "change_class": change_class,
        "risk_profile": risk_profile,
        **binding,
        "changed_files": files,
        "surfaces": [
            "runtime",
            "mcp",
            "immutable_host",
            "scheduled_control_units",
            "release_manager",
            "configuration",
        ],
        "runtime_artifact_digest": digest,
        "mcp_artifact_digest": mcp_digest,
        "policy_digest": file_digest(repo / "config" / "release-manager-policy.json"),
        "desired_state_policy_digest": file_digest(
            repo / "config" / "production-desired-state.json"
        ),
    }
    gate_transition(repo, state_root, record, "release_candidate")
    save_record(state_root, record)
    return record



def approve_release(
    repo: Path,
    state_root: Path,
    *,
    release_id: str,
    candidate_sha: str,
    source: str = "explicit_owner_instruction",
) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    record = load_record(state_root, release_id)
    if str(record.get("state") or "") != "production_eligible":
        raise ReleaseManagerError(
            "owner approval may only be recorded for a production_eligible release"
        )
    candidate = record.get("release_candidate")
    if not isinstance(candidate, dict):
        raise ReleaseManagerError("release candidate metadata is missing")
    recorded_sha = exact_sha(str(candidate.get("candidate_sha") or ""), "candidate_sha")
    if recorded_sha != candidate_sha:
        raise ReleaseManagerError("owner approval candidate SHA does not match release record")
    verify_candidate_on_main(repo, candidate_sha)
    if image_id(str(candidate.get("image") or "")) != str(candidate.get("artifact_digest") or ""):
        raise ReleaseManagerError("candidate runtime artifact changed before owner approval")
    if image_id(str(candidate.get("mcp_image") or "")) != str(candidate.get("mcp_artifact_digest") or ""):
        raise ReleaseManagerError("candidate MCP artifact changed before owner approval")
    approval = record.get("owner_approval")
    if isinstance(approval, dict) and approval.get("approved") is True:
        if str(approval.get("candidate_sha") or "") != candidate_sha:
            raise ReleaseManagerError("existing owner approval is bound to a different SHA")
        return record
    record["owner_approval"] = {
        "approved": True,
        "candidate_sha": candidate_sha,
        "source": str(source or "explicit_owner_instruction"),
        "recorded_at": now(),
    }
    record.setdefault("history", []).append(
        {"at": now(), "state": "production_eligible", "gate": "owner_approval_recorded"}
    )
    save_record(state_root, record)
    return record

def consume_owner_approval_requests(repo: Path, state_root: Path) -> int:
    request_root = state_root / "owner-approval-requests"
    if not request_root.exists():
        return 0
    processed_root = state_root / "owner-approval-requests-processed"
    count = 0
    for path in sorted(request_root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str(payload.get("schema_version") or "") != "1.0":
            raise ReleaseManagerError("owner approval request schema is invalid")
        release_id = str(payload.get("release_id") or "").strip().casefold()
        candidate_sha = exact_sha(str(payload.get("candidate_sha") or ""), "candidate_sha")
        approved_by = str(payload.get("approved_by") or "").strip()
        organization_id = str(payload.get("organization_id") or "").strip()
        if release_id != record_id(candidate_sha):
            raise ReleaseManagerError("owner approval request release ID does not match candidate SHA")
        if not approved_by or not organization_id:
            raise ReleaseManagerError("owner approval request identity metadata is incomplete")
        approve_release(
            repo,
            state_root,
            release_id=release_id,
            candidate_sha=candidate_sha,
            source="governed_mcp_owner:" + approved_by,
        )
        processed_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = processed_root / path.name
        if destination.exists():
            existing = json.loads(destination.read_text(encoding="utf-8"))
            if existing != payload:
                raise ReleaseManagerError("processed owner approval request conflicts with pending request")
            path.unlink()
        else:
            os.replace(path, destination)
        count += 1
    return count


def require_candidate_controller_for_preproduction(repo: Path, candidate_sha: str) -> None:
    """Refuse to certify a release using a superseded Production Manager.

    For a controller-changing release, the installed N controller cannot
    attest to the native preflight semantics of N+1. An operator must use the
    immutable reviewed candidate runner. No existing release record is changed
    by this guard and it never starts a production mutation.
    """
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    try:
        reviewed_bytes = subprocess.check_output(
            ["git", "-C", str(repo), "show",
             candidate_sha + ":tools/release_manager_host_runner.py"],
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseManagerError("candidate Production Manager source cannot be verified") from exc
    reviewed_digest = "sha256:" + hashlib.sha256(reviewed_bytes).hexdigest()
    if file_digest(CONTROLLER_SOURCE) != reviewed_digest:
        raise ReleaseManagerError(
            "preproduction requires the exact candidate Production Manager controller"
        )


def run_preproduction(repo: Path, state_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    require_candidate_controller_for_preproduction(
        repo, str((record.get("release_candidate") or {}).get("candidate_sha") or ""),
    )
    gate_transition(repo, state_root, record, "preproduction")
    candidate = record["release_candidate"]
    image = str(candidate["image"])
    digest = str(candidate["artifact_digest"])
    mcp_image = str(candidate["mcp_image"])
    mcp_digest = str(candidate["mcp_artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed before pre-production")
    if image_id(mcp_image) != mcp_digest:
        raise ReleaseManagerError("candidate MCP image changed before pre-production")

    # Hold the existing serialized release lock only during the temporary
    # preproduction container lifecycle. The independent production watchdog
    # already defers while this lock is held; no container allowlist or drift
    # policy is weakened. This also prevents a concurrent production promotion
    # from starting while preproduction has a live ephemeral container.
    preprod_lock = acquire_production_transaction_lock(repo, state_root, record)
    name = ""
    scratch: Path | None = None
    try:
        live = live_runtime()
        name, scratch = create_preprod_container(
            live=live,
            candidate_image=image,
            candidate_sha=str(candidate["candidate_sha"]),
            state_root=state_root,
            release_id=str(record["release_id"]),
        )
        run(["docker", "start", name])
        wait_health(name)
        verify_preprod_env(name, str(candidate["candidate_sha"]))
        preflight_contract_digest = production_preflight(
            repo,
            state_root,
            image,
            mcp_image,
            str(candidate["candidate_sha"]),
        )
        if (not isinstance(preflight_contract_digest, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", preflight_contract_digest)):
            raise ReleaseManagerError("preproduction native deployment contract not proven")
        rollback_image = image_id("jason-runtime:rollback-current")
        if not rollback_image:
            raise ReleaseManagerError("runtime rollback-current image alias is unavailable")
        mcp_rollback_image = image_id("jason-mcp:rollback-current")
        if not mcp_rollback_image:
            raise ReleaseManagerError("MCP rollback-current image alias is unavailable")
        record["preproduction"] = {
            "deployed_sha": candidate["candidate_sha"],
            "artifact_digest": digest,
            "mcp_artifact_digest": mcp_digest,
            "acceptance_passed": True,
            "native_deploy_contract_digest": preflight_contract_digest,
            "sqlite_snapshot_consistency_checked": True,
            "failure_path_tests_passed": True,
            "rollback_readiness_passed": True,
            "writable_state_isolated": True,
            "provider_mutations_disabled": True,
            "verified_at": now(),
        }
        gate_transition(repo, state_root, record, "preprod_verified")
        gate_transition(repo, state_root, record, "production_eligible")
        write_owner_notification_event(
            state_root, record, "production_queue_entered"
        )
        save_record(state_root, record)
        return record
    finally:
        try:
            if name:
                subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if scratch and scratch.exists():
                shutil.rmtree(scratch, ignore_errors=True)
        finally:
            # No stale lock if preproduction fails in health, CCC preflight,
            # rollback verification, or even the cleanup subprocess.
            release_production_transaction_lock(preprod_lock)


def publish_production_closeout(repo: Path, candidate_sha: str) -> dict[str, str]:
    script = repo / "tools" / "publish_documentation_reconciliation.sh"
    if not script.is_file():
        raise ReleaseManagerError("production evidence publisher is missing")
    env = os.environ.copy()
    env["JASON_DOCUMENTATION_REPO_ROOT"] = str(repo)
    publication = run(
        [str(script), "production", candidate_sha],
        cwd=repo,
        env=env,
    )
    if "DOCUMENTATION_SUCCESS_RECONCILIATION=PASS mode=production" not in publication:
        raise ReleaseManagerError("production documentation reconciliation did not pass")
    if "CONTROL_BOARD_PUBLICATION=PASS" not in publication:
        raise ReleaseManagerError("production control-board publication did not pass")
    return {
        "documentation": "pass",
        "control_board": "pass",
    }


def validate_release_record_contract(record: dict[str, Any]) -> None:
    """Reject legacy/incomplete release evidence before production mutation.

    A historical record produced by an older controller may have passed CI
    and preproduction without ever constructing final closeout fields.
    """
    candidate = record.get('release_candidate') or {}
    manifest = record.get('release_manifest')
    risk = record.get('risk_profile')
    sha = str(candidate.get('candidate_sha') or '')
    rollback = str(record.get('rollback_sha') or '')
    # create_record/classify_change_risk emits the canonical enum string.
    # Earlier test records may carry a structured risk object; preserve that
    # compatible form, while rejecting absent, empty or unknown classifications.
    allowed_risks = {'normal', 'production_repair', 'production_control_core', 'schema_or_contract'}
    risk_valid = (
        isinstance(risk, str) and risk in allowed_risks
        or isinstance(risk, dict) and bool(risk)
    )
    if not isinstance(manifest, dict) or not risk_valid:
        raise ReleaseManagerError('release record lacks valid release_manifest or risk_profile; reprepare through current controller')
    if not SHA.fullmatch(sha) or not SHA.fullmatch(rollback):
        raise ReleaseManagerError('release record has invalid exact revision identities')
    if manifest.get('candidate_sha') != sha or manifest.get('rollback_sha') != rollback:
        raise ReleaseManagerError('release manifest identities do not match candidate and rollback baseline')
    if manifest.get('risk_profile') != risk:
        raise ReleaseManagerError('release manifest risk classification differs from release record')


CCC_REQUIRED_CHECKS = frozenset({
    "checker-currentness", "runtime-source-alignment", "j002-article-matrix",
    "system-registry", "j900-release-validation",
    "mcp-constitutional-production-equivalent", "systemd-failed-units",
    "prometheus-targets", "openclaw-authority-health", "immutable-runtime-release",
    "mcp-governance-boundary", "governed-provider-boundary-canaries",
})


def verify_release_ccc_report(
    report: dict[str, Any], *, candidate_sha: str, runtime_sha: str,
    before_mutation: bool,
) -> dict[str, Any]:
    """Fail closed on any CCC exception other than expected predeploy alignment.

    A runtime-changing candidate cannot align with LIVE runtime before deployment.
    This grants no CCC PASS: it only admits a scoped transition supported by
    immutable preprod artifacts and a mandatory post-deploy PASS/rollback.
    """
    if report.get("schema_version") != "1.0":
        raise ReleaseManagerError("CCC evidence schema is not recognized")
    if report.get("source_revision") != exact_sha(candidate_sha, "candidate_sha"):
        raise ReleaseManagerError("CCC evidence source is not the exact release candidate")
    if report.get("runtime_revision") != exact_sha(runtime_sha, "runtime_sha"):
        raise ReleaseManagerError("CCC evidence runtime revision does not match expected live revision")
    if str(report.get("trigger") or "") not in {"material_change", "cadence"}:
        raise ReleaseManagerError("CCC evidence must be a forced material/cadence review")
    if not str(report.get("run_id") or "").strip():
        raise ReleaseManagerError("CCC evidence run identifier is missing")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ReleaseManagerError("CCC evidence checks are missing")
    indexed: dict[str, str] = {}
    for entry in checks:
        if not isinstance(entry, dict):
            raise ReleaseManagerError("CCC evidence includes malformed check")
        key = str(entry.get("check_id") or "")
        if not key or key in indexed:
            raise ReleaseManagerError("CCC evidence has an empty or duplicate check")
        indexed[key] = str(entry.get("status") or "")
    required = CCC_REQUIRED_CHECKS | (
        {"material-change-owner-review"} if report.get("material_changes") else set()
    )
    missing = required - set(indexed)
    if missing:
        raise ReleaseManagerError("CCC mandatory checks are missing: " + ", ".join(sorted(missing)))
    exceptional = {key: status for key, status in indexed.items() if status != "PASS"}
    if before_mutation:
        expected = {"runtime-source-alignment": "NOT_PROVEN"}
        if not (report.get("status") == "PASS" and not exceptional or
                report.get("status") == "NOT_PROVEN" and exceptional == expected):
            # Report schema, exact source/runtime identities and all required
            # checks were validated above. A *sole* known checker-currentness
            # gap is an operational upgrade prerequisite, not a failed
            # deployment. No production state has been mutated at this gate.
            upgrade_only = (
                report.get("status") == "NOT_PROVEN"
                and exceptional in (
                    {"checker-currentness": "NOT_PROVEN"},
                    {
                        "checker-currentness": "NOT_PROVEN",
                        "runtime-source-alignment": "NOT_PROVEN",
                    },
                )
            )
            if upgrade_only:
                raise CCCCheckerUpgradeRequired(
                    "pre-mutation CCC requires independently certified checker upgrade"
                )
            # A report from the current trusted checker can independently
            # attest the absence of the *separate* human material review.
            # Only the canonical missing-review detail and exact path evidence
            # constitute a deferrable human dependency. Neither the owner
            # release approval nor an arbitrary NOT_PROVEN check is sufficient.
            review_entry = next((
                entry for entry in checks
                if entry.get("check_id") == "material-change-owner-review"
            ), {})
            material_paths = report.get("material_changes")
            review_evidence = review_entry.get("evidence")
            expected_review_status = {
                "material-change-owner-review": "NOT_PROVEN",
            }
            expected_review_and_alignment = {
                **expected_review_status,
                "runtime-source-alignment": "NOT_PROVEN",
            }
            review_pending = (
                report.get("status") == "NOT_PROVEN"
                and exceptional in (
                    expected_review_status, expected_review_and_alignment,
                )
                and isinstance(material_paths, list) and bool(material_paths)
                and all(isinstance(path, str) and path for path in material_paths)
                and review_entry.get("detail")
                    == "Material change requires an exact owner review record for this source revision."
                and isinstance(review_evidence, dict)
                and review_evidence.get("paths") == material_paths
            )
            if review_pending:
                raise CCCMaterialReviewRequired(
                    "pre-mutation CCC requires independently recorded exact-owner material review"
                )
            raise ReleaseManagerError("pre-mutation CCC denied: " + str(exceptional)[:300])
        mode = "candidate_transition" if exceptional else "aligned"
    else:
        if report.get("status") != "PASS" or exceptional:
            raise ReleaseManagerError("post-mutation CCC did not certify exact live candidate")
        mode = "live_certified"
    return {
        "status": report["status"], "mode": mode,
        "source_revision": candidate_sha, "runtime_revision": runtime_sha,
        "run_id": str(report.get("run_id") or ""),
        "finished_at": str(report.get("finished_at") or ""),
        "checks": indexed,
    }


# Keep the CCC itself authoritative. The only permitted bounded retry is an
# independently refreshed post-deployment checker report whose sole failing
# check is an approved bounded transient monitoring failure or an exact,
# read-only provider exception. Neither failing report is accepted as PASS.
# Every report remains subject to exact SHA, required checks and freshness.
CCC_POSTFLIGHT_MONITORING_RETRY_DELAYS = (15, 20, 25)
# A live, governed provider read may briefly raise at provider initialization
# or transport level. These are never PASS. Two fresh *full* CCC reruns are
# allowed only for the specific reviewed read canaries, with unchanged exact
# source/runtime identity, all other gates passing, and new report identifiers.
CCC_POSTFLIGHT_PROVIDER_EXCEPTION_RETRY_DELAYS = (10, 15)
CCC_RETRYABLE_READ_CANARIES = {
    # Both Datto checks are read-only. If provider initialization or transient
    # SQLite contention raises during a live read, the independent checker may
    # run a bounded, FRESH full CCC report. A failed report never counts as PASS.
    # Incident 2026-10-22: two Datto-only exceptions did not qualify because
    # this mapping omitted endpoint.device.read, stranding an approved release.
    "datto_rmm": "endpoint.device.read",
    "datto_edr": "endpoint.security.status.read",
    "dnsfilter": "dns.protection.organization.read",
}


def retryable_ccc_provider_exceptions(report: Mapping[str, Any]) -> bool:
    """Classify only named exception records, never auth/denial/data failures."""
    if report.get("status") != "FAIL":
        return False
    checks = report.get("checks")
    if not isinstance(checks, list):
        return False
    failed = [check for check in checks
              if isinstance(check, Mapping) and check.get("status") != "PASS"]
    if (len(failed) != 1
            or failed[0].get("check_id") != "governed-provider-boundary-canaries"
            or failed[0].get("status") != "FAIL"):
        return False
    evidence = failed[0].get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    failures = evidence.get("failures")
    results = evidence.get("results")
    expected_count = evidence.get("expected_canary_count")
    if (not isinstance(failures, list) or not 1 <= len(failures) <= 2
            or not isinstance(results, list)
            or type(expected_count) is not int or not 4 <= expected_count <= 25
            or len(results) != expected_count):
        return False
    names = [row.get("name") for row in results if isinstance(row, Mapping)]
    if len(names) != len(results) or len(set(names)) != len(names):
        return False
    seen: set[str] = set()
    for entry in failures:
        if not isinstance(entry, Mapping):
            return False
        name = entry.get("name")
        expected = entry.get("expected")
        if (not isinstance(name, str) or name not in CCC_RETRYABLE_READ_CANARIES
                or name in seen
                or entry.get("status") != "exception"
                or entry.get("expected_status") != "succeeded"
                or not isinstance(expected, Mapping)
                or expected.get("expected_status") != "succeeded"
                or expected.get("name") != name
                or expected.get("capability") != CCC_RETRYABLE_READ_CANARIES[name]
                or expected.get("expected_provider") != name):
            return False
        seen.add(name)
    indexed = [entry for entry in results if isinstance(entry, Mapping)
               and entry.get("name") in seen]
    return (len(indexed) == len(seen)
            and all(entry.get("status") == "exception" for entry in indexed))


def run_release_ccc_gate(
    candidate_sha: str, runtime_sha: str, *, before_mutation: bool,
    ccc_runner: Path = Path("/opt/jason/ccc-current/tools/run_ccc.py"),
    ccc_config: Path = Path("/var/lib/jason/ccc/ccc.json"),
    latest: Path = Path("/var/lib/jason/ccc/latest.json"),
) -> dict[str, Any]:
    """Demand a fresh independent CCC PASS; boundedly recheck scrape races.

    Never reinterpret FAIL as PASS. For a single transient monitoring FAIL,
    request a completely new checker run while keeping the production
    transaction lock held. All non-monitoring failures fail immediately.
    """
    if not ccc_runner.is_file() or not ccc_config.is_file():
        raise ReleaseManagerError("independent CCC checker/config unavailable")
    failed_monitoring_runs: list[str] = []
    failed_provider_runs: list[str] = []
    max_runs = (1 + len(CCC_POSTFLIGHT_MONITORING_RETRY_DELAYS)
                + len(CCC_POSTFLIGHT_PROVIDER_EXCEPTION_RETRY_DELAYS))
    for _ in range(max_runs):
        started = datetime.now(timezone.utc)
        try:
            completed = subprocess.run(
                ["python3", str(ccc_runner), "--config", str(ccc_config),
                 "--force", "--trigger", "material_change",
                 "--candidate-sha", candidate_sha],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False, timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReleaseManagerError("independent CCC execution did not complete") from exc
        if not latest.is_file():
            raise ReleaseManagerError("independent CCC did not persist a report")
        report = json.loads(latest.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ReleaseManagerError("CCC report is not a JSON object")
        try:
            finished = datetime.fromisoformat(str(report.get("finished_at") or ""))
        except (ValueError, TypeError) as exc:
            raise ReleaseManagerError("CCC completion timestamp missing") from exc
        if (finished.tzinfo is None or
                finished < started - timedelta(seconds=2) or
                finished > datetime.now(timezone.utc) + timedelta(seconds=15)):
            raise ReleaseManagerError(
                "CCC report is stale, future-dated or not independently refreshed"
            )
        try:
            evidence = verify_release_ccc_report(
                report, candidate_sha=candidate_sha, runtime_sha=runtime_sha,
                before_mutation=before_mutation,
            )
        except ReleaseManagerError as exc:
            # verify_release_ccc_report checked exact candidate and runtime SHA,
            # required check set, unique IDs, and report schema BEFORE raising
            # this specific failure. A missing/unverified check can never retry.
            nonpassing = [
                (x["check_id"], x["status"]) for x in report["checks"]
                if x["status"] != "PASS"
            ] if isinstance(report.get("checks"), list) else []
            transient = (
                not before_mutation
                and str(exc) == "post-mutation CCC did not certify exact live candidate"
                and report.get("status") == "FAIL"
                and nonpassing == [("prometheus-targets", "FAIL")]
                and completed.returncode != 0
            )
            provider_exception = (
                not before_mutation
                and str(exc) == "post-mutation CCC did not certify exact live candidate"
                and completed.returncode != 0
                and retryable_ccc_provider_exceptions(report)
            )
            if transient and len(failed_monitoring_runs) < len(CCC_POSTFLIGHT_MONITORING_RETRY_DELAYS):
                run_id = str(report["run_id"])
                if run_id in failed_monitoring_runs or run_id in failed_provider_runs:
                    raise ReleaseManagerError("CCC repeated a prior monitoring report")
                retry_index = len(failed_monitoring_runs)
                failed_monitoring_runs.append(run_id)
                print(
                    f"CCC_MONITORING_TRANSIENT=RECHECK run_id={run_id} "
                    f"attempt={retry_index + 1}",
                    flush=True,
                )
                time.sleep(CCC_POSTFLIGHT_MONITORING_RETRY_DELAYS[retry_index])
                continue
            if provider_exception and len(failed_provider_runs) < len(CCC_POSTFLIGHT_PROVIDER_EXCEPTION_RETRY_DELAYS):
                run_id = str(report["run_id"])
                if run_id in failed_monitoring_runs or run_id in failed_provider_runs:
                    raise ReleaseManagerError("CCC repeated a prior provider canary report")
                retry_index = len(failed_provider_runs)
                failed_provider_runs.append(run_id)
                print(
                    f"CCC_PROVIDER_CANARY_EXCEPTION=RECHECK run_id={run_id} "
                    f"attempt={retry_index + 1}",
                    flush=True,
                )
                time.sleep(CCC_POSTFLIGHT_PROVIDER_EXCEPTION_RETRY_DELAYS[retry_index])
                continue
            raise
        if completed.returncode != 0 and evidence["status"] == "PASS":
            raise ReleaseManagerError("independent CCC process failed despite PASS report")
        if failed_monitoring_runs or failed_provider_runs:
            if str(evidence["run_id"]) in (*failed_monitoring_runs, *failed_provider_runs):
                raise ReleaseManagerError("CCC reused an earlier failed report identifier")
        if failed_monitoring_runs:
            evidence["transient_monitoring_retries"] = len(failed_monitoring_runs)
            evidence["failed_monitoring_run_ids"] = failed_monitoring_runs
        if failed_provider_runs:
            evidence["transient_provider_exception_retries"] = len(failed_provider_runs)
            evidence["failed_provider_exception_run_ids"] = failed_provider_runs
        return evidence
    raise ReleaseManagerError("independent CCC postflight checks never certified")



# Recovery of a script that started but returned nonzero must not assume the
# subordinate deploy_live_container.py successfully restored everything. Its
# best-effort Docker rename/start and tag restoration intentionally use
# check=False; a preflight error, however, may leave the baseline untouched.
# Pin only these two known image surfaces and verified LKG image IDs.
_ROLLBACK_SURFACE_TAGS = {
    "runtime": ("jason-runtime:rollback-current", "jason-runtime:production"),
    "mcp": ("jason-mcp:rollback-current", "jason-mcp:production"),
}


def rollback_surface_is_verified(
    surface: str, rollback_sha: str, baseline_manifest: dict[str, Any],
) -> bool:
    if surface not in _ROLLBACK_SURFACE_TAGS:
        raise ReleaseManagerError("unsupported rollback surface")
    expected_id = str(baseline_manifest[f"{surface}_image_id"])
    try:
        current = live_runtime() if surface == "runtime" else live_mcp()
        production_tag = _ROLLBACK_SURFACE_TAGS[surface][1]
        return (
            current["revision"] == rollback_sha
            and current["image_id"] == expected_id
            and image_id(production_tag) == expected_id
        )
    except (KeyError, ValueError, ReleaseManagerError, subprocess.CalledProcessError, OSError):
        # Unreadable state is not a proof of successful rollback.
        return False


def pin_exact_rollback_image(
    surface: str, baseline_manifest: dict[str, Any],
) -> None:
    """Repair only a stale rollback-current tag from immutable LKG evidence.

    A failed forward deploy may occur before the helper retags rollback-current,
    leaving the *previous-previous* image. Never use that stale alias to
    restore a release with a different exact rollback SHA.
    """
    if surface not in _ROLLBACK_SURFACE_TAGS:
        raise ReleaseManagerError("unsupported rollback surface")
    expected_id = str(baseline_manifest[f"{surface}_image_id"])
    if re.fullmatch(r"sha256:[a-f0-9]{64}", expected_id) is None:
        raise ReleaseManagerError("verified immutable rollback image ID is invalid")
    rollback_tag = _ROLLBACK_SURFACE_TAGS[surface][0]
    try:
        existing = image_id(rollback_tag)
    except (ReleaseManagerError, subprocess.CalledProcessError, OSError):
        existing = None
    if existing != expected_id:
        # This controlled Docker tag operation is within the already
        # owner-authorized, exclusive Production Manager rollback transaction.
        run(["docker", "tag", expected_id, rollback_tag])
        if image_id(rollback_tag) != expected_id:
            raise ReleaseManagerError("pinned rollback image tag readback mismatch")


def _deploy_production_locked(repo: Path, state_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    if record.get("state") != "production_eligible":
        raise ReleaseManagerError("release is not Production Eligible")
    validate_release_record_contract(record)
    candidate = record["release_candidate"]
    candidate_sha = str(candidate["candidate_sha"])
    image = str(candidate["image"])
    digest = str(candidate["artifact_digest"])
    mcp_image = str(candidate["mcp_image"])
    mcp_digest = str(candidate["mcp_artifact_digest"])
    if image_id(image) != digest:
        raise ReleaseManagerError("candidate image changed after pre-production")
    if image_id(mcp_image) != mcp_digest:
        raise ReleaseManagerError("candidate MCP image changed after pre-production")

    # Do not begin a disruptive production transaction unless the privileged
    # host boundary is already installed and the rollback baseline is aligned.
    require_host_reconciler_ready(state_root)
    rollback_sha = str(record["rollback_sha"])
    live_production_alignment(rollback_sha)

    # Prove the exact candidate source is materializable before recording that
    # production deployment has begun. A repository/source failure must leave
    # the durable release in production_eligible rather than stranding a false
    # production state with no provider/runtime mutation performed.
    deploy_worktree = worktree(repo, state_root, candidate_sha)
    runtime_script = (
        deploy_worktree / "infrastructure" / "jason-runtime" / "production-deploy.sh"
    )
    mcp_script = (
        deploy_worktree / "infrastructure" / "jason-mcp" / "production-deploy.sh"
    )
    if not runtime_script.is_file() or not mcp_script.is_file():
        remove_worktree(repo, deploy_worktree)
        raise ReleaseManagerError(
            "exact candidate worktree is missing a required production deploy script"
        )
    candidate_quickbooks_profile = declared_quickbooks_read_profile(deploy_worktree)
    candidate_worker_uid = worker_enrollment.approved_diagnostic_uid(deploy_worktree)
    previous_worker_uid = worker_enrollment.live_diagnostic_uid(output)
    prior_quickbooks_profile = live_quickbooks_read_profile()
    candidate_autotask_profile = declared_autotask_read_profile(deploy_worktree)
    prior_autotask_profile = (
        live_autotask_read_profile() if candidate_autotask_profile is not None else None
    )
    # Run the identical deployment-input validator used by preproduction.
    # This must happen before CCC and any production state transition.
    deployment_env = native_deploy_environment(
        deploy_worktree, image, mcp_image, candidate_sha,
        worker_uid=candidate_worker_uid,
    )
    verified_contract = (record.get("preproduction") or {}).get(
        "native_deploy_contract_digest"
    )
    if (not isinstance(verified_contract, str)
            or verified_contract != native_deploy_contract_digest(deployment_env)):
        raise ReleaseManagerError(
            "native deployment arguments differ from preproduction-verified contract"
        )
    host_contract = verify_candidate_host_reconciliation_contract(
        deploy_worktree, candidate_sha
    )

    # The existing live runtime can differ from a valid new candidate. This
    # narrowly scoped preflight is NOT a CCC PASS and requires full post CCC.
    verify_candidate_on_main(repo, candidate_sha)
    ccc_preflight = run_release_ccc_gate(
        candidate_sha, rollback_sha, before_mutation=True,
    )
    record["ccc_pre_mutation_gate"] = ccc_preflight

    controller_pin = controller_identity(deploy_worktree)
    baseline_manifest = capture_production_manifest(rollback_sha)
    owner_read_canary_session = None
    if (candidate_autotask_profile is not None
            and candidate_autotask_profile != prior_autotask_profile):
        # Start the post-deploy *real connected owner* acceptance witness before
        # any production mutation. Empty/stale/synthetic evidence cannot pass.
        owner_read_canary_session = owner_read_canary.begin_authenticated_read_canary(
            state_root, candidate_sha=candidate_sha,
            profile=candidate_autotask_profile,
        )
    record["controller_pin"] = controller_pin
    record["last_known_good_manifest"] = baseline_manifest
    record["pre_mutation_health"] = {
        "passed": True,
        "observed_at": baseline_manifest["observed_at"],
        "revision": rollback_sha,
        "manifest_complete": bool(baseline_manifest.get("complete")),
    }
    # Protected baseline is already a root-owned, verified last-known-good.
    # The root transition worker only accepts approved candidate release IDs,
    # not synthetic baseline IDs. Preserve the existing root baseline when it
    # matches the independently verified current production revision.
    protected_path = control_state_path(state_root)
    if protected_path.exists() and protected_path.stat().st_uid == 0 and os.geteuid() != 0:
        protected_state = load_control_state(state_root)
        existing_manifest = dict((protected_state.get("last_known_good") or {}).get("manifest") or {})
        if existing_manifest.get("revision") != rollback_sha or existing_manifest.get("complete") is not True:
            raise ReleaseManagerError("root protected rollback baseline differs from verified production")
        if dict(protected_state.get("circuit_breaker") or {}).get("state") != "closed":
            raise ReleaseManagerError("root protected circuit breaker is not closed")
    else:
        set_last_known_good(
            state_root,
            baseline_manifest,
            release_id="baseline-" + rollback_sha[:16],
        )
    save_record(state_root, record)

    # Recheck after CCC/manifest work, immediately before the first production
    # transition. A GitHub merge during long preflight must not make a
    # formerly-current candidate silently supersede newer protected work.
    require_current_protected_release_source(repo, record)
    require_current_manual_scope_review(repo, state_root, record)
    require_owner_production_deployment_unfrozen(state_root)
    gate_transition(repo, state_root, record, "production")
    save_record(state_root, record)

    env = deployment_env

    runtime_attempted = False
    mcp_attempted = False
    host_attempted = False
    release_manager_installed = False

    try:
        # Mark *attempt* BEFORE executing the helper. A failed helper may have
        # already stopped/renamed/replaced live state before returning nonzero.
        runtime_attempted = True
        runtime_output = run(
            [str(runtime_script)],
            cwd=deploy_worktree,
            env=env,
        )
        wait_live_runtime()

        mcp_attempted = True
        mcp_output = run(
            [str(mcp_script)],
            cwd=deploy_worktree,
            env=env,
        )
        if worker_enrollment.live_diagnostic_uid(output) != candidate_worker_uid:
            raise ReleaseManagerError("diagnostic worker enrollment failed dual-plane readback")
        if live_mcp()["revision"] != candidate_sha:
            raise ReleaseManagerError(
                "MCP did not report the exact candidate revision after deployment"
            )
        if (candidate_autotask_profile is not None
                and live_autotask_read_profile() != candidate_autotask_profile):
            raise ReleaseManagerError("post-deploy Autotask read activation profile mismatch")

        host_attempted = True
        host_result = request_host_reconcile(state_root, candidate_sha)
        host_evidence = verify_host_reconciliation_evidence(
            host_result, candidate_sha
        )

        manager_result = install_release_manager_from_current(candidate_sha)
        release_manager_installed = True

        alignment = live_production_alignment(candidate_sha)
        live = wait_live_runtime()
        live_digest = image_id("jason-runtime:production")
        live_mcp_digest = image_id("jason-mcp:production")
        if live_digest != digest:
            raise ReleaseManagerError(
                "production runtime image differs from pre-production artifact"
            )
        if live_mcp_digest != mcp_digest:
            raise ReleaseManagerError(
                "production MCP image differs from pre-production artifact"
            )

        controller_verified = verify_controller_identity(controller_pin, deploy_worktree, installed_candidate=True)
        smoke = run_functional_smoke_tests(candidate_sha)
        verified_owner_read_canary = None
        if owner_read_canary_session is not None:
            # This waits for genuine OAuth-bound, governed MCP tool reads:
            # ticket count, exact pagination, exact ticket read and the newly
            # added generic Projects query. No synthetic provider-health
            # canary, status endpoint or fixture may satisfy this gate.
            verified_owner_read_canary = owner_read_canary.require_authenticated_read_canary(
                state_root, owner_read_canary_session,
            )
        # Certification is mandatory BEFORE verified/closed or new LKG. A
        # non-PASS or stale/wrong-SHA report raises inside the rollback block.
        ccc_postflight = run_release_ccc_gate(
            candidate_sha, candidate_sha, before_mutation=False,
        )
        record["ccc_post_mutation_gate"] = ccc_postflight
        drift_evidence = production_drift_evidence(state_root)
        production_manifest = capture_production_manifest(candidate_sha)

        closeout = publish_production_closeout(deploy_worktree, candidate_sha)

        record["production"] = {
            "live_sha": live["revision"],
            "artifact_digest": live_digest,
            "mcp_artifact_digest": live_mcp_digest,
            "health_passed": True,
            "ccc_pre_mutation": ccc_preflight,
            "ccc_post_mutation": ccc_postflight,
            "functional_smoke_tests_passed": bool(smoke.get("passed")),
            "functional_smoke_tests": smoke,
            "authenticated_owner_read_canary": verified_owner_read_canary,
            "controller_identity_verified": True,
            "controller_handoff": controller_verified["controller_handoff"],
            "executing_controller_revision": controller_verified["executing_controller_revision"],
            "executing_controller_digest": controller_verified["executing_controller_digest"],
            "installed_controller_digest": controller_verified["installed_controller_digest"],
            "last_known_good_manifest_captured": bool(baseline_manifest.get("complete")),
            "pre_mutation_health_passed": bool(record["pre_mutation_health"].get("passed")),
            "production_manifest_complete": bool(production_manifest.get("complete")),
            "production_manifest": production_manifest,
            "desired_state_converged": True,
            "desired_state_drift_problem_count": len(drift_evidence.get("problems") or []),
            "desired_state_drift_observed_at": drift_evidence.get("observed_at"),
            "deployment_script_passed": "DEPLOYMENT=PASS" in runtime_output,
            "mcp_deployment_script_passed": "DEPLOYMENT=PASS" in mcp_output,
            "host_reconciliation_passed": bool(host_result.get("success")),
            "host_reconciliation_candidate_script_verified": host_evidence["candidate_script_verified"],
            "managed_engineering_source_verified": host_evidence["managed_engineering_source_verified"],
            "managed_documentation_source_verified": host_evidence["managed_documentation_source_verified"],
            "developer_checkout_dependency_absent": host_evidence["developer_checkout_absent"],
            "host_reconciliation_preflight_passed": all(host_contract.values()),
            "release_manager_install_passed": True,
            "release_manager_source_revision": manager_result["source_revision"],
            "release_manager_timer_active": manager_result["timer_active"],
            "alignment_verified": True,
            "runtime_revision": alignment["runtime_revision"],
            "mcp_revision": alignment["mcp_revision"],
            "host_revision": alignment["host_revision"],
            "host_release": alignment["host_release"],
            "documentation_reconciliation": closeout["documentation"],
            "control_board_publication": closeout["control_board"],
            "verified_at": now(),
        }
        record["evidence_bundle"] = {
            "release_id": record["release_id"],
            "candidate_sha": candidate_sha,
            "release_manifest": record["release_manifest"],
            "risk_profile": record["risk_profile"],
            "owner_approval": record.get("owner_approval"),
            "ccc_pre_mutation": ccc_preflight,
            "ccc_post_mutation": ccc_postflight,
            "preproduction": record.get("preproduction"),
            "pre_mutation_health": record.get("pre_mutation_health"),
            "functional_smoke_tests": smoke,
            "authenticated_owner_read_canary": verified_owner_read_canary,
            "production_manifest": production_manifest,
            "desired_state_drift_evidence": drift_evidence,
            "rollback_target": baseline_manifest,
            "final_state": "closed",
            "closed_at": now(),
        }
        # The final root-governed last-known-good commit is part of production
        # acceptance. No verified/closed state or success notification may be
        # emitted until that protected transition independently succeeds.
        set_last_known_good(
            state_root,
            production_manifest,
            release_id=str(record["release_id"]),
        )
        gate_transition(repo, state_root, record, "production_verified")
        gate_transition(repo, state_root, record, "closed")
        save_record(state_root, record)
        write_owner_notification_event(
            state_root, record, "production_queue_completed"
        )
        return record
    except Exception as error:
        rollback_env = quickbooks_rollback_environment(
            os.environ, rollback_sha=rollback_sha, prior_profile=prior_quickbooks_profile
        )
        if prior_autotask_profile is not None:
            # The immutable candidate script is the sole authority for choosing
            # its declared rollback profile. Supplying the old profile as the
            # *candidate activation* override makes both native rollback
            # scripts reject the transition before touching their containers.
            # Preserve the exact audited rollback SHA and verify the expected
            # profile separately without overriding the source profile.
            rollback_env = autotask_rollback_environment(
                rollback_env, prior_autotask_profile=prior_autotask_profile
            )
        rollback_env[worker_enrollment.ENV_NAME] = previous_worker_uid

        rollback_errors: list[str] = []
        recovery_steps = {"mcp": "not_attempted", "host": "not_attempted",
                          "manager": "not_attempted", "runtime": "not_attempted"}

        # Reverse the forward transaction in dependency order. A script can
        # return nonzero AFTER mutating production; do not trust its exit code
        # or its best-effort internal rollback as proof. A healthy, exact-LKG
        # surface need not be restarted merely because preflight failed.
        if mcp_attempted:
            try:
                if rollback_surface_is_verified("mcp", rollback_sha, baseline_manifest):
                    recovery_steps["mcp"] = "already_verified_at_baseline"
                else:
                    recovery_steps["mcp"] = "restoration_attempted"
                    pin_exact_rollback_image("mcp", baseline_manifest)
                    run([str(mcp_script)], cwd=deploy_worktree, env=rollback_env)
                    if not rollback_surface_is_verified("mcp", rollback_sha, baseline_manifest):
                        raise ReleaseManagerError("MCP rollback image/alias/live revision is not verified")
                    recovery_steps["mcp"] = "restored_and_verified"
            except Exception as exc:
                recovery_steps["mcp"] = "unverified"
                rollback_errors.append("mcp=" + type(exc).__name__ + ":" + str(exc)[:200])

        if host_attempted:
            try:
                recovery_steps["host"] = "restoration_attempted"
                request_host_reconcile(state_root, rollback_sha)
                recovery_steps["host"] = "reconciled_baseline"
            except Exception as exc:
                recovery_steps["host"] = "unverified"
                rollback_errors.append("host=" + type(exc).__name__ + ":" + str(exc)[:200])

        if release_manager_installed or host_attempted:
            try:
                recovery_steps["manager"] = "restoration_attempted"
                install_release_manager_from_current(rollback_sha)
                recovery_steps["manager"] = "reconciled_baseline"
            except Exception as exc:
                recovery_steps["manager"] = "unverified"
                rollback_errors.append(
                    "release_manager=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        if runtime_attempted:
            try:
                if rollback_surface_is_verified("runtime", rollback_sha, baseline_manifest):
                    recovery_steps["runtime"] = "already_verified_at_baseline"
                else:
                    recovery_steps["runtime"] = "restoration_attempted"
                    pin_exact_rollback_image("runtime", baseline_manifest)
                    run([str(runtime_script)], cwd=deploy_worktree, env=rollback_env)
                    # Docker may have started the correct immutable LKG image
                    # while its health probe still reports "starting". The
                    # promotion closeout also waits; rollback must too.
                    wait_live_runtime()
                    if not rollback_surface_is_verified("runtime", rollback_sha, baseline_manifest):
                        raise ReleaseManagerError("runtime rollback image/alias/health is not verified")
                    recovery_steps["runtime"] = "restored_and_verified"
            except Exception as exc:
                recovery_steps["runtime"] = "unverified"
                rollback_errors.append(
                    "runtime=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        rollback_ok = False
        if not rollback_errors:
            try:
                # Read-only, full-manifest verification includes runtime health,
                # exact immutable image IDs, MCP, host, controller and timers.
                # Do not reinstall/restart an unchanged controller a second
                # time just to verify it.
                live_production_alignment(rollback_sha)
                verified_manifest = capture_production_manifest(rollback_sha)
                if verified_manifest.get("complete") is not True:
                    raise ReleaseManagerError("rollback baseline manifest is incomplete")
                for surface in ("runtime", "mcp"):
                    if (verified_manifest[f"{surface}_image_id"]
                            != baseline_manifest[f"{surface}_image_id"]):
                        raise ReleaseManagerError("rollback image ID differs from pinned LKG")
                rollback_ok = True
            except Exception as exc:
                rollback_errors.append(
                    "verification=" + type(exc).__name__ + ":" + str(exc)[:200]
                )

        record["failure"] = {
            "at": now(),
            "error": type(error).__name__,
            "message": str(error)[:700],
            "rollback_verified": rollback_ok,
            "rollback_errors": rollback_errors,
            "rollback_actions": recovery_steps,
        }
        record["state"] = "rolled_back" if rollback_ok else "failed"
        record.setdefault("history", []).append(
            {"at": now(), "state": record["state"], "gate": "deployment_failure"}
        )
        open_circuit_breaker(
            state_root,
            record,
            reason=type(error).__name__ + ": " + str(error),
            rollback_verified=rollback_ok,
        )
        if not rollback_ok:
            write_owner_notification_event(
                state_root,
                record,
                "production_owner_action_required",
                owner_action=(
                    "Production recovery could not be fully verified. Review the "
                    "release failure and rollback evidence before further promotion."
                ),
            )
        save_record(state_root, record)
        raise
    finally:
        remove_worktree(repo, deploy_worktree)


def manual_release_scope_review(
    repo: Path, state_root: Path, record: dict[str, Any], *,
    include_prs: tuple[int, ...] = (),
    include_commits: tuple[str, ...] = (),
    acknowledged_prs: tuple[int, ...] = (),
    acknowledged_worktrees: tuple[str, ...] = (),
    record_review: bool = False,
) -> dict[str, Any]:
    """Review a full exact-main release; no deployment or developer checkout edits.

    A scope acknowledgement is technical change-integration evidence, NOT
    owner deployment authorization. It is bound to the candidate and baseline
    and must be recomputed under the production lock before any mutation.
    """
    import importlib.util
    source = repo / "tools/manual_release_scope.py"
    if source.is_symlink() or not source.is_file():
        raise ReleaseManagerError("canonical manual scope reviewer is unavailable")
    spec = importlib.util.spec_from_file_location("jason_manual_release_scope", source)
    if spec is None or spec.loader is None:
        raise ReleaseManagerError("canonical manual scope reviewer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidate = exact_sha(str(
        (record.get("release_candidate") or {}).get("candidate_sha") or ""
    ), "candidate_sha")
    baseline = exact_sha(str(record.get("rollback_sha") or ""), "rollback_sha")
    try:
        result = module.review(
            repo, module.repository_from_origin(repo), baseline, candidate,
            allowed_prs=include_prs,
            allowed_commits=include_commits,
            acknowledged_prs=acknowledged_prs,
            acknowledged_worktrees=acknowledged_worktrees,
        )
    except module.ScopeBlocked as exc:
        raise ReleaseManagerError("manual scope review failed closed: " + str(exc)) from exc
    if record_review:
        if record.get("state") != "production_eligible":
            raise ReleaseManagerError("scope review requires production_eligible release")
        if result.get("status") != "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED":
            raise ReleaseManagerError(
                "scope review blocked unacknowledged merged changes or parallel work"
            )
        record["manual_scope_review"] = {
            "schema_version": "1.0",
            "candidate_sha": candidate,
            "baseline_sha": baseline,
            "scope_sha256": result["scope_sha256"],
            "included_prs": sorted(set(include_prs)),
            "included_commits": sorted(set(include_commits)),
            "acknowledged_prs": sorted(set(acknowledged_prs)),
            "acknowledged_worktrees": sorted(set(acknowledged_worktrees)),
            "recorded_at": now(),
        }
        save_record(state_root, record)
    return result


def require_current_manual_scope_review(
    repo: Path, state_root: Path, record: dict[str, Any]
) -> None:
    """Reject promotions without a fresh complete review of *all* merged work."""
    receipt = record.get("manual_scope_review")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "1.0":
        raise ReleaseManagerError(
            "manual release blocked: full change/parallel-work review is missing"
        )
    candidate = exact_sha(str(
        (record.get("release_candidate") or {}).get("candidate_sha") or ""
    ), "candidate_sha")
    baseline = exact_sha(str(record.get("rollback_sha") or ""), "rollback_sha")
    if receipt.get("candidate_sha") != candidate or receipt.get("baseline_sha") != baseline:
        raise ReleaseManagerError("manual scope review is for a different release")
    result = manual_release_scope_review(
        repo, state_root, record,
        include_prs=tuple(receipt.get("included_prs") or ()),
        include_commits=tuple(receipt.get("included_commits") or ()),
        acknowledged_prs=tuple(receipt.get("acknowledged_prs") or ()),
        acknowledged_worktrees=tuple(receipt.get("acknowledged_worktrees") or ()),
    )
    if (result.get("status") != "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED"
            or receipt.get("scope_sha256") != result.get("scope_sha256")):
        raise ReleaseManagerError(
            "manual release scope changed: repeat review of merged and unfinished work"
        )


def require_owner_production_deployment_unfrozen(state_root: Path) -> None:
    """Refuse any production promotion while an exact owner freeze is recorded.

    The existing auto-promotion incident hold controls unattended scheduling
    and intentional manual mode. This separate marker freezes BOTH entry
    points without preventing read-only diagnostics, isolated preproduction,
    or emergency rollback to the independently verified baseline.

    A symlink, directory, or unreadable marker fails closed; no caller can
    bypass this check by passing an absent/unreadable marker value.
    """
    marker = state_root / "production-deployment-freeze"
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ReleaseManagerError(
            "owner production deployment freeze status cannot be verified"
        ) from exc
    raise ReleaseManagerError(
        "owner production deployment freeze is active: "
        "manual and automatic promotions are prohibited"
    )


def deploy_production(repo: Path, state_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    require_owner_production_deployment_unfrozen(state_root)
    lock = acquire_production_transaction_lock(repo, state_root, record)
    try:
        require_owner_production_deployment_unfrozen(state_root)
        require_current_manual_scope_review(repo, state_root, record)
        # Check fresh authoritative source before retention, breaker work, or
        # production deployment. Applies to explicit/manual and automatic paths.
        require_current_protected_release_source(repo, record)
        # Verify that the independent root reconciler is installed and active
        # before even bounded stopped-container retention maintenance.
        require_host_reconciler_ready(state_root)
        # Explicit/manual promotion needs the same bounded rollback retention
        # headroom already reserved by prepare_release and the automatic timer.
        # Remove only historical stopped rollback containers under the exclusive
        # production lock, BEFORE root breaker revalidation and any live change.
        reconcile_stopped_rollback_retention()
        revalidate_circuit_breaker(state_root)
        return _deploy_production_locked(repo, state_root, record)
    finally:
        release_production_transaction_lock(lock)


def prepare_release(
    repo: Path,
    state_root: Path,
    candidate_sha: str,
    change_class: str,
    *,
    owner_approved: bool = False,
    reissue_rolled_back: bool = False,
    support_item: str | None = None,
    support_pr_number: int | None = None,
) -> dict[str, Any]:
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    if change_class == 'support':
        verify_support_release_binding(
            repo, candidate_sha, support_item, support_pr_number,
        )
    elif support_item is not None or support_pr_number is not None:
        raise ReleaseManagerError('non-Support release cannot claim Support identity')
    # Routine promotion and explicit owner-authorized preparation must share the
    # same bounded, stopped-container-only retention hygiene. It must run
    # before breaker revalidation (which checks drift including retention).
    # Any Docker failure fails closed rather than masking real drift.
    reconcile_stopped_rollback_retention()
    revalidate_circuit_breaker(state_root)
    release_id = record_id(candidate_sha)
    if reissue_rolled_back:
        original = load_record(state_root, release_id)
        if original.get("state") != "rolled_back" or (original.get("failure") or {}).get("rollback_verified") is not True:
            raise ReleaseManagerError("reissue requires a verified rolled-back release")
        if (original.get("release_candidate") or {}).get("candidate_sha") != candidate_sha:
            raise ReleaseManagerError("reissue source does not match historical attempt")
        for attempt in range(1, 1000):
            next_id = f"{release_id}-retry-{attempt}"
            if record_path(state_root, next_id).exists():
                existing = load_record(state_root, next_id)
                if (existing.get("release_candidate") or {}).get("candidate_sha") != candidate_sha:
                    raise ReleaseManagerError("existing retry attempt has mismatched source")
                if existing.get("state") not in {"rolled_back", "failed"}:
                    raise ReleaseManagerError("an existing retry attempt must be completed or explicitly resolved before reissue")
                continue
            if not record_path(state_root, next_id).exists():
                release_id = next_id
                break
        else:
            raise ReleaseManagerError("reissue attempt limit exceeded")
    path = record_path(state_root, release_id)

    if path.exists():
        record = load_record(state_root, release_id)
        if record.get('change_class') != change_class:
            raise ReleaseManagerError('existing release changed its reviewed change class')
        if change_class == 'support' and (
            record.get('support_item') != support_item
            or record.get('support_pr_number') != support_pr_number
        ):
            raise ReleaseManagerError('existing release Support identity does not match')
        state = str(record.get("state") or "")
        if state in {
            "production_eligible",
            "production",
            "production_verified",
            "closed",
        }:
            return record
        if state == "release_candidate":
            return run_preproduction(repo, state_root, record)
        if state == "development" and record.get("revalidation_required"):
            previous = {
                "rollback_sha": record.get("rollback_sha"),
                "revalidation_required": record.get("revalidation_required"),
                "history": list(record.get("history") or []),
            }
            live = live_runtime()
            rollback_sha = exact_sha(str(live["revision"]), "rollback_sha")
            rebuilt = create_record(
                repo=repo,
                state_root=state_root,
                candidate_sha=candidate_sha,
                rollback_sha=rollback_sha,
                change_class=str(record.get("change_class") or change_class),
                owner_approved=bool((record.get("owner_approval") or {}).get("approved")),
                support_item=support_item,
                support_pr_number=support_pr_number,
            )
            rebuilt["prior_revalidation"] = previous
            save_record(state_root, rebuilt)
            return run_preproduction(repo, state_root, rebuilt)
        raise ReleaseManagerError(
            f"existing release {release_id} is not safely resumable from state {state}"
        )

    live = live_runtime()
    rollback_sha = exact_sha(str(live["revision"]), "rollback_sha")
    record = create_record(
        repo=repo,
        state_root=state_root,
        candidate_sha=candidate_sha,
        rollback_sha=rollback_sha,
        change_class=change_class,
        owner_approved=owner_approved,
        support_item=support_item,
        support_pr_number=support_pr_number,
        release_id_override=release_id if reissue_rolled_back else None,
    )
    if reissue_rolled_back:
        record["reissued_from"] = record_id(candidate_sha)
        save_record(state_root, record)
    return run_preproduction(repo, state_root, record)


def production_gate_result(repo: Path, record: dict[str, Any]) -> dict[str, Any]:
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    support = gate.parse_support((repo / "SUPPORT.md").read_text(encoding="utf-8"))
    todos = gate.parse_todos(
        (repo / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md").read_text(
            encoding="utf-8"
        )
    )
    return gate.evaluate_transition(
        record,
        "production",
        policy,
        support_items=support,
        todos=todos,
    )


def reconcile_stopped_rollback_retention(*, keep: int = 16) -> int:
    """Reserve room for rollback containers created during a promotion.

    Only historical exited rollback containers qualify. Image-based rollback
    authority, live containers, and durable release records are never touched.
    """
    output = run(['docker', 'ps', '-a', '--filter', 'status=exited',
                  '--format', '{{.CreatedAt}}|{{.Names}}'])
    eligible = []
    for line in output.splitlines():
        created, sep, name = line.partition('|')
        if sep and re.fullmatch(r'jason-(?:runtime|mcp-pilot|mcp|teams-gateway)-rollback-[0-9T]+Z', name):
            eligible.append((created, name))
    eligible.sort(reverse=True)
    for _, name in eligible[keep:]:
        run(['docker', 'rm', name])
    return len(eligible[:keep])


def authoritative_auto_promotion_head(repo: Path) -> str:
    """Read the exact protected remote-main tip, never a stale local checkout."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
            cwd=repo, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseManagerError("protected main cannot be verified for automatic promotion") from exc
    if result.returncode != 0:
        raise ReleaseManagerError("protected main cannot be verified for automatic promotion")
    lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if (len(lines) != 1 or len(lines[0]) != 2
            or lines[0][1] != "refs/heads/main"
            or not SHA.fullmatch(lines[0][0])):
        raise ReleaseManagerError("protected main returned an invalid exact revision")
    return lines[0][0]


def require_current_protected_release_source(repo: Path, record: dict[str, Any]) -> None:
    """Reject a superseded/manual candidate before a production transaction.

    Automatic selection already compares to main; manual promotion must obey the
    same immutable source rule. Neither a past exact-SHA approval nor a successful
    preproduction run authorizes replacing more recent protected-main work.
    """
    candidate = str((record.get("release_candidate") or {}).get("candidate_sha") or "")
    baseline = str(record.get("rollback_sha") or "")
    if not SHA.fullmatch(candidate) or not SHA.fullmatch(baseline):
        raise ReleaseManagerError("production candidate or baseline SHA is invalid")
    current_main = authoritative_auto_promotion_head(repo)
    if candidate != current_main:
        raise ReleaseManagerError(
            "production release candidate is behind protected main; "
            "reprepare and revalidate the exact current main revision"
        )
    # A valid candidate on main must also include the installed production
    # history; otherwise promoting it would drop production changes.
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, candidate],
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if ancestry.returncode != 0:
        raise ReleaseManagerError(
            "production release candidate does not descend from the active baseline"
        )


def live_release_mobile_approval_mode(runtime: dict[str, Any]) -> str:
    """Read only the trusted *running* container's release-approval mode.

    A policy file upgraded on disk cannot activate new risk classes while
    production is still running the older owner-only pilot. No other
    env variables or secrets are included in output.
    """
    config = (runtime.get("inspect") or {}).get("Config") or {}
    values = config.get("Env")
    if not isinstance(values, list):
        return "off"
    selected = [str(value).split("=", 1)[1] for value in values
                if isinstance(value, str)
                and value.startswith("JASON_RELEASE_MOBILE_APPROVAL_MODE=")]
    if len(selected) != 1:
        return "off"
    return selected[0] if selected[0] in {"owner_only_pilot", "owner_reviewed"} else "off"


def signed_owner_offer_purpose(
    record: dict[str, Any], candidate_sha: str, reviewed_policy: Any,
    live_mode: str, *, ccc_root: Path,
) -> str | None:
    """Return narrow actionable Teams purpose or None. No authority mutation.

    V1 remains normal-risk and can only offer a full unapproved release.
    V2 can offer a CCC-only card for an ALREADY approved exact release whose
    separately authenticated CCC material review is missing. A fully reviewed
    release gets no redundant card. Neither case certifies CCC or deploys.
    """
    expected_mode = ("owner_only_pilot" if reviewed_policy.schema_version == "1.0"
                     else "owner_reviewed")
    if live_mode != expected_mode:
        return None
    if str(record.get("risk_profile") or "unknown") not in reviewed_policy.allowed_risk_profiles:
        return None
    owner = record.get("owner_approval") or {}
    if owner.get("approved") is not True:
        return "release_and_ccc"
    if (reviewed_policy.schema_version != "2.0"
            or owner.get("candidate_sha") != candidate_sha):
        return None
    named = ccc_root / ("material-review-" + candidate_sha[:16] + ".json")
    if named.is_file():
        prior = json.loads(named.read_text(encoding="utf-8"))
        if (prior.get("source_revision") == candidate_sha
                and prior.get("recorded_by") == "person-al"
                and prior.get("status") == "approved"):
            return None
        # A conflicting stored review is an authority problem, not an
        # invitation to issue a new card that would overwrite audit evidence.
        raise ReleaseManagerError("existing CCC material review conflicts with exact release")
    return "ccc_material_review_only"


@contextmanager
def approval_only_production_transaction_gate(state_root: Path):
    """Serialize nonexecuting approval processing with the REAL release mutex.

    An in-flight release may temporarily have a new runtime/MCP but the old
    protected LKG. This is not evidence of a permanently inconsistent baseline.
    Deferring the entire approval-only cycle while that exclusive transaction
    lock is held avoids a spurious failed user unit and downstream root drift.

    Use the same inode as native promotion, never its written metadata or a
    timestamp as evidence of activity. All other lock errors fail closed.
    """
    path = state_root / "production-transaction.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(path, flags, 0o660)
    except OSError as exc:
        raise ReleaseManagerError(
            "approval-only release transaction lock cannot be opened safely"
        ) from exc
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o002):
            raise ReleaseManagerError(
                "approval-only release transaction lock ownership or mode is unsafe"
            )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Still no approval, no Teams card and no production state read.
            yield False
            return
        except OSError as exc:
            raise ReleaseManagerError(
                "approval-only release transaction lock state is unavailable"
            ) from exc
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def approval_only_while_promotion_held(repo: Path, state_root: Path) -> bool:
    """Issue nonexecuting owner Teams offers, NEVER during a release transaction.

    The same exclusive lock governs the *whole* approved-only read and any
    signed decision, so a simultaneous production promotion cannot begin after
    we first check the version but before issuing or consuming a Teams offer.
    A collision is a benign IDLE deferral, never permission to bypass drift.
    """
    if Path(state_root).resolve() != DEFAULT_STATE.resolve():
        raise ReleaseManagerError("approval-only worker requires canonical live state")
    if not (state_root / "auto-promotion-incident-hold").is_file():
        print("RELEASE_APPROVAL_ONLY=HOLD_NOT_ACTIVE", flush=True)
        return False
    with approval_only_production_transaction_gate(state_root) as stable:
        if not stable:
            print("RELEASE_APPROVAL_ONLY=PRODUCTION_TRANSITION_IN_PROGRESS", flush=True)
            return False
        return _approval_only_on_stable_production(repo, state_root)


def _approval_only_on_stable_production(repo: Path, state_root: Path) -> bool:
    """Private locked implementation; never call outside the serialized gate."""
    # Trust only fresh root-published evidence and a healthy, aligned live
    # production baseline; never revalidate or close an opened breaker here.
    control = _read_protected_snapshot(state_root, "production-control-state.json")
    drift = _read_protected_snapshot(state_root, "production-drift.json")
    if ((control.get("circuit_breaker") or {}).get("state") != "closed"
            or drift.get("status") != "pass" or drift.get("problems")):
        # Expected safety hold is NOT a broken systemd service: returning
        # nonzero makes this failed user unit show up as production drift,
        # which opens the root breaker again indefinitely. Stay completely
        # nonexecuting, but report the blocked condition for supervision.
        print("RELEASE_APPROVAL_ONLY=SAFETY_GATE_BLOCKED", flush=True)
        return False
    live = live_runtime()
    live_sha = exact_sha(live["revision"], "live_production_sha")
    live_production_alignment(live_sha)
    lkg = ((control.get("last_known_good") or {}).get("manifest") or {}).get("revision")
    if lkg != live_sha:
        raise ReleaseManagerError("approval-only production baseline does not match LKG")

    policy_path = MOBILE_APPROVAL_POLICY
    if not policy_path.is_file():
        print("RELEASE_APPROVAL_ONLY=OWNER_POLICY_UNAVAILABLE", flush=True)
        return False
    tools_root = str(repo / "tools")
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
    from release_mobile_approval_consumer import (
        MobileReleaseEvidenceBusy, _install_repo_modules, consume_mobile_release_decisions,
    )
    _install_repo_modules(Path(repo))
    from jason_runtime.mobile_release_approval import read_mobile_release_policy
    from jason_runtime.owner_release_approval_containment import read_release_approval_containment
    containment = read_release_approval_containment(state_root)
    if containment.active:
        print("RELEASE_APPROVAL_ONLY=OWNER_APPROVAL_CONTAINMENT", flush=True)
        return False
    reviewed_policy = read_mobile_release_policy(policy_path)
    mode = live_release_mobile_approval_mode(live)
    expected_mode = ("owner_only_pilot" if reviewed_policy.schema_version == "1.0"
                     else "owner_reviewed")
    if mode != expected_mode:
        print("RELEASE_APPROVAL_ONLY=REVIEWED_MODE_NOT_ACTIVE", flush=True)
        return False

    # This consumer independently verifies original signed owner evidence,
    # release record, role/binding, policy, replay and CCC material review. It
    # records only the existing exact-SHA owner/CCC authorization; it does not
    # call deploy_production or change the incident hold.
    try:
        consume_mobile_release_decisions(
            repo=repo, state_root=state_root, approve_release=approve_release,
        )
    except MobileReleaseEvidenceBusy:
        print("RELEASE_APPROVAL_ONLY=SIGNED_OWNER_EVIDENCE_BUSY", flush=True)
        return False

    # A newer protected HEAD or changed baseline makes old offers invalid.
    main_sha = authoritative_auto_promotion_head(repo)
    record_file = record_path(state_root, record_id(main_sha))
    if not record_file.is_file():
        print("RELEASE_APPROVAL_ONLY=NO_CURRENT_ELIGIBLE_RELEASE", flush=True)
        return False
    record = load_record(state_root, record_id(main_sha))
    if (record.get("state") != "production_eligible"
            or (record.get("release_candidate") or {}).get("candidate_sha") != main_sha
            or (record.get("release_manifest") or {}).get("candidate_sha") != main_sha
            or record.get("rollback_sha") != live_sha
            or not (record.get("preproduction") or {}).get("acceptance_passed")
            or not (record.get("preproduction") or {}).get("rollback_readiness_passed")
            or not (record.get("development") or {}).get("required_checks_passed")):
        print("RELEASE_APPROVAL_ONLY=NO_CURRENT_ELIGIBLE_RELEASE", flush=True)
        return False
    purpose = signed_owner_offer_purpose(
        record, main_sha, reviewed_policy, mode,
        ccc_root=Path("/var/lib/jason/ccc"),
    )
    if purpose is None:
        print("RELEASE_APPROVAL_ONLY=NO_OWNER_ACTION_REQUIRED", flush=True)
        return False

    # Recheck hold and protected source before durable offer publication.
    if (not (state_root / "auto-promotion-incident-hold").is_file()
            or authoritative_auto_promotion_head(repo) != main_sha
            or exact_sha(live_runtime()["revision"], "live_production_sha") != live_sha):
        raise ReleaseManagerError("approval-only offer source, hold or baseline changed")
    offer_root = state_root / "mobile-release-offers"
    offer = offer_root / (record_id(main_sha) + ".json")
    if offer.exists():
        existing = json.loads(offer.read_text(encoding="utf-8"))
        if (existing.get("candidate_sha") != main_sha
                or existing.get("live_rollback_sha") != live_sha
                or existing.get("release_id") != record_id(main_sha)):
            raise ReleaseManagerError("existing Teams owner offer conflicts with exact release")
        # Never bump an old offer TTL, reissue a card or overwrite evidence
        # after an uncertain transport outcome or a previous owner decision.
        print("RELEASE_APPROVAL_ONLY=EXISTING_OFFER_PRESERVED", flush=True)
        return False
    manifest_digest = hashlib.sha256(json.dumps(
        record["release_manifest"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    atomic_json(offer, {
        "schema_version": "1.0",
        "release_id": record_id(main_sha),
        "candidate_sha": main_sha,
        "manifest_sha256": manifest_digest,
        "protected_main_sha": main_sha,
        "live_rollback_sha": live_sha,
        **({"review_only": True} if purpose == "ccc_material_review_only" else {}),
        "published_at": now(),
    })
    print("RELEASE_APPROVAL_ONLY=OFFER_PUBLISHED_NONEXECUTING", flush=True)
    return True



def request_expired_owner_card_renewal(
    repo: Path, state_root: Path, *, release_id: str, candidate_sha: str,
    mobile_db: Path = Path("/var/lib/jason/openclaw/mobile-release-approvals.sqlite3"),
) -> dict[str, str]:
    """Interactive OS-owner request for a *new Teams card*, never approval.

    Requires owner account at an actual terminal. Revalidates protected main,
    root safety, live rollback baseline, risk/policy and every previous terminal
    card. Writes one new immutable private intent; no database expiry resets.
    """
    if (state_root.resolve() != DEFAULT_STATE.resolve()
            or pwd.getpwuid(os.getuid()).pw_name != "al"
            or not sys.stdin.isatty() or os.getuid() != state_root.stat().st_uid):
        raise ReleaseManagerError("a local interactive authenticated al owner session is required")
    candidate_sha = exact_sha(candidate_sha, "candidate_sha")
    if release_id != record_id(candidate_sha):
        raise ReleaseManagerError("renewal release ID and exact SHA do not match")
    if not (state_root / "auto-promotion-incident-hold").is_file():
        raise ReleaseManagerError("manual-promotion incident hold is not active")
    control = _read_protected_snapshot(state_root, "production-control-state.json")
    drift = _read_protected_snapshot(state_root, "production-drift.json")
    if ((control.get("circuit_breaker") or {}).get("state") != "closed"
            or drift.get("status") != "pass" or drift.get("problems")):
        raise ReleaseManagerError("host baseline or release breaker is not safe")
    live = live_runtime()
    live_sha = exact_sha(live["revision"], "live_sha")
    live_production_alignment(live_sha)
    if (control.get("last_known_good") or {}).get("manifest", {}).get("revision") != live_sha:
        raise ReleaseManagerError("live production is not the last-known-good revision")
    if authoritative_auto_promotion_head(repo) != candidate_sha:
        raise ReleaseManagerError("source is not the current protected main SHA")
    policy_path = MOBILE_APPROVAL_POLICY
    if not policy_path.is_file():
        raise ReleaseManagerError("the approved owner Teams policy is unavailable")
    from release_mobile_approval_consumer import _install_repo_modules
    _install_repo_modules(repo)
    from jason_runtime.mobile_release_approval import (
        CAPABILITY, RENEWAL_LIMIT, read_eligible_release, read_mobile_release_policy,
    )
    from jason_runtime.owner_release_approval_containment import read_release_approval_containment
    containment = read_release_approval_containment(state_root)
    if containment.active:
        raise ReleaseManagerError("owner Teams release approval is contained")
    policy = read_mobile_release_policy(policy_path)
    expected_mode = ("owner_only_pilot" if policy.schema_version == "1.0"
                     else "owner_reviewed")
    if live_release_mobile_approval_mode(live) != expected_mode:
        raise ReleaseManagerError("reviewed Teams approval mode does not match live runtime")
    candidate = read_eligible_release(state_root, release_id, policy)
    if candidate.candidate_sha != candidate_sha or candidate.rollback_sha != live_sha:
        raise ReleaseManagerError("release rollback or signed source has changed")
    db = Path(mobile_db)
    con = sqlite3.connect("file:" + str(db.absolute()) + "?mode=ro", uri=True, timeout=2)
    try:
        related = []
        for raw, in con.execute("SELECT payload FROM approval_requests"):
            doc = json.loads(raw)
            if (doc.get("capability") == CAPABILITY
                    and (doc.get("metadata") or {}).get("release_id") == release_id):
                related.append(doc)
        if not related or len(related) > RENEWAL_LIMIT:
            raise ReleaseManagerError("no expired request or owner renewal limit reached")
        if any(doc.get("status") != "expired" for doc in related):
            raise ReleaseManagerError("existing owner Teams request is not an expired undecided card")
        prior = max(related, key=lambda doc: doc["requested_at"])
        if (any((doc.get("metadata") or {}).get(k) != expected
                for k, expected in (
                    ("candidate_sha", candidate_sha),
                    ("rollback_sha", live_sha),
                    ("manifest_sha256", candidate.manifest_sha256),
                    ("owner_policy_sha256", policy.policy_sha256),
                ) for doc in related)):
            raise ReleaseManagerError("previous Teams request does not match exact current release")
        for doc in related:
            if con.execute("SELECT 1 FROM approval_decision_receipts WHERE approval_id=?",
                           (doc["approval_id"],)).fetchone():
                raise ReleaseManagerError("a previous signed Teams decision already exists")
    finally:
        con.close()
    instant = datetime.now(timezone.utc)
    if datetime.fromisoformat(prior["expires_at"]) >= instant:
        raise ReleaseManagerError("previous owner request is not past its expiration")
    folder = state_root / "mobile-release-renewals"
    folder.mkdir(mode=0o700, parents=False, exist_ok=True)
    if (folder.is_symlink() or stat.S_IMODE(folder.stat().st_mode) != 0o700
            or folder.stat().st_uid != os.getuid()):
        raise ReleaseManagerError("renewal intent directory is not private")
    lock_path = folder / "owner-renewal.lock"
    lockfd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lockfd, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = list(folder.glob(release_id + "-renew-*.json"))
        if len(existing) >= RENEWAL_LIMIT:
            raise ReleaseManagerError("maximum explicit owner renewals reached")
        for file in existing:
            data = json.loads(file.read_text(encoding="utf-8"))
            if data.get("previous_approval_id") == prior["approval_id"]:
                raise ReleaseManagerError("an owner renewal already exists for the latest expired card")
        nonce = secrets.token_hex(16)
        marker = folder / (release_id + "-renew-" + nonce + ".json")
        record = {
            "schema_version": "1.0", "release_id": release_id,
            "candidate_sha": candidate_sha, "rollback_sha": live_sha,
            "manifest_sha256": candidate.manifest_sha256,
            "owner_policy_sha256": policy.policy_sha256, "renewal_nonce": nonce,
            "previous_approval_id": prior["approval_id"],
            "requested_at": instant.isoformat(),
            "requester_identity": "person-al", "requester_os_account": "al",
        }
        # Exclusive creation: no timestamp bump, overwrite or second owner request.
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        dirfd = os.open(folder, os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    return {
        "release_id": release_id, "candidate_sha": candidate_sha,
        "previous_approval_id": prior["approval_id"],
        "status": "fresh_card_requested_not_authorized",
        "requested_at": record["requested_at"],
    }


def promote_eligible(repo: Path, state_root: Path) -> bool:
    # Keep the required five-minute timer active, but do not allow it to
    # execute a production promotion while Owner has selected manual mode.
    # The normal explicit approve + promote path remains governed and usable.
    policy = gate.load_json(repo / "config" / "release-manager-policy.json")
    if (policy.get("schedule") or {}).get("automatic_promotion_enabled") is not True:
        return False
    # Mobile Teams owner decisions are checked independently against the
    # registered gateway signature, active Entra/Jason owner binding, exact
    # release manifest, 0600 versioned policy and durable single-use receipt.
    # Disabled by default: no policy/ledger => no mobile authorization.
    tools_root = str(repo / "tools")
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
    from release_mobile_approval_consumer import (
        MobileReleaseEvidenceBusy, _install_repo_modules,
        consume_mobile_release_decisions,
    )
    # The host runner also operates from a lightweight systemd/unittest
    # environment without PYTHONPATH. Install ONLY modules from the pinned
    # release source before importing the shared runtime safety policy.
    _install_repo_modules(Path(repo))
    from jason_runtime.owner_release_approval_containment import read_release_approval_containment
    from jason_runtime.mobile_release_approval import read_mobile_release_policy
    release_teams_containment = read_release_approval_containment(state_root)
    # SECURITY: the default mobile approval database contains LIVE signed owner
    # decisions. Isolated/preproduction release-manager state roots MUST never
    # consume them into a different release/CCC state or test fixture.
    # Existing explicit test invocation of the consumer uses injected test DBs.
    if Path(state_root).resolve() == DEFAULT_STATE.resolve():
        try:
            consume_mobile_release_decisions(
                repo=repo, state_root=state_root, approve_release=approve_release,
            )
        except MobileReleaseEvidenceBusy:
            # Only an independently typed SQLITE_BUSY/LOCKED condition permits
            # this bounded scheduled-cycle deferral. NEVER approve/deploy while
            # signed owner evidence cannot be read. Other identity, trust,
            # policy, schema and receipt failures remain hard denials.
            print("RELEASE_MANAGER_AUTO_DEFERRED=signed_owner_evidence_busy",
                  flush=True)
            return False
    consume_owner_approval_requests(repo, state_root)
    if not production_window_open():
        return False
    records = state_root / "records"
    if not records.exists():
        return False
    try:
        main_sha = authoritative_auto_promotion_head(repo)
    except ReleaseManagerError:
        # Network failure is an explicit *deferral*, not a production-service
        # outage. No approval or queued release state is changed.
        print("RELEASE_MANAGER_AUTO_DEFERRED=authoritative_main_unavailable", flush=True)
        return False
    # Cards are issued only for the exact release independently found at
    # protected GitHub main and the still-matching live rollback baseline.
    # A 5-minute signed-review offer eliminates stale historical approval spam.
    offer_root = state_root / "mobile-release-offers"
    if (Path("/var/lib/jason/authority/mobile-release-approval-policy.json").is_file()
            and offer_root.is_dir()):
        for old in offer_root.glob("release-*.json"):
            if old.stem != record_id(main_sha):
                old.unlink()
    superseded = 0
    for path in sorted(records.glob("*.json"), key=lambda item: item.stat().st_mtime):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("state") != "production_eligible":
            continue
        candidate_sha = str((record.get("release_candidate") or {}).get("candidate_sha") or "")
        if not SHA.fullmatch(candidate_sha):
            print("RELEASE_MANAGER_AUTO_DEFERRED=invalid_candidate_identity", flush=True)
            continue
        # A prior explicit Owner approval remains valid for its exact SHA,
        # but must never be selected unattended after a newer protected
        # source becomes authoritative. Preserve its record as evidence.
        if candidate_sha != main_sha:
            superseded += 1
            continue

        # A queued release is tied to the production baseline against which it
        # passed pre-production. If production has advanced, do not repeatedly
        # attempt promotion with an obsolete rollback target. Demote it to a
        # clean revalidation state and let the normal preparation path rebuild
        # evidence against the current production baseline.
        current_sha = exact_sha(str(live_runtime()["revision"]), "current_production_sha")
        live_production_alignment(current_sha)
        recorded_rollback = exact_sha(str(record.get("rollback_sha") or ""), "rollback_sha")
        if recorded_rollback != current_sha:
            record["state"] = "development"
            record["revalidation_required"] = {
                "reason": "production_baseline_advanced",
                "previous_rollback_sha": recorded_rollback,
                "current_production_sha": current_sha,
                "detected_at": now(),
            }
            record.setdefault("history", []).append(
                {
                    "at": now(),
                    "state": "development",
                    "gate": "queued_release_baseline_stale",
                }
            )
            save_record(state_root, record)
            continue

        reviewed_policy_path = Path("/var/lib/jason/authority/mobile-release-approval-policy.json")
        owner_teams_eligible = False
        if (not release_teams_containment.active
                and reviewed_policy_path.is_file()):
            reviewed_policy = read_mobile_release_policy(reviewed_policy_path)
            live_mode = live_release_mobile_approval_mode(live_runtime())
            expected_mode = ("owner_only_pilot" if reviewed_policy.schema_version == "1.0"
                             else "owner_reviewed")
            requested_risk = str(record.get("risk_profile") or "unknown")
            purpose = signed_owner_offer_purpose(
                record, candidate_sha, reviewed_policy, live_mode,
                ccc_root=Path("/var/lib/jason/ccc"),
            )
            owner_teams_eligible = purpose is not None
            review_only = purpose == "ccc_material_review_only"
            if live_mode != expected_mode:
                print("RELEASE_TEAMS_APPROVAL_UNAVAILABLE=runtime_mode_mismatch"
                      + f" expected={expected_mode} active={live_mode}", flush=True)
            elif requested_risk not in reviewed_policy.allowed_risk_profiles:
                print("RELEASE_TEAMS_APPROVAL_UNAVAILABLE=reviewed_policy_excludes_risk"
                      + f" risk={requested_risk}", flush=True)
        if owner_teams_eligible:
            offer_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            offer = offer_root / (record_id(candidate_sha) + ".json")
            atomic_json(offer, {
                "schema_version": "1.0", "release_id": record_id(candidate_sha),
                "candidate_sha": candidate_sha,
                "manifest_sha256": hashlib.sha256(json.dumps(
                    record["release_manifest"], sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")).hexdigest(),
                "protected_main_sha": main_sha, "live_rollback_sha": current_sha,
                **({"review_only": True} if review_only else {}),
                "published_at": now(),
            })
        result = production_gate_result(repo, record)
        if result.get("allowed") is True:
            # Close the TOCTOU gap between scanning the queue and opening the
            # production transaction. A newer protected merge defers the
            # unattended release without redefining Owner authorization.
            try:
                if authoritative_auto_promotion_head(repo) != candidate_sha:
                    print("RELEASE_MANAGER_AUTO_DEFERRED=protected_main_advanced", flush=True)
                    return False
            except ReleaseManagerError:
                print("RELEASE_MANAGER_AUTO_DEFERRED=authoritative_main_unavailable", flush=True)
                return False
            # No rollback retention mutation until exact-source Owner and
            # production gates are verified for the current protected HEAD.
            reconcile_stopped_rollback_retention()
            try:
                deploy_production(repo, state_root, record)
            except ReleaseManagerBusy:
                return False
            except (CCCCheckerUpgradeRequired, CCCMaterialReviewRequired) as prerequisite:
                # An exact attested preflight prerequisite is a scheduled
                # WAIT, never deployment permission. ALL other CCC denials
                # remain hard failures; explicit 'promote' still raises.
                reason = (
                    "ccc_checker_upgrade_required"
                    if isinstance(prerequisite, CCCCheckerUpgradeRequired)
                    else "ccc_exact_material_owner_review_required"
                )
                print(
                    "RELEASE_MANAGER_AUTO_DEFERRED=" + reason
                    + f" candidate={candidate_sha} release_id={record['release_id']}",
                    flush=True,
                )
                return False
            return True
        reasons = [str(value) for value in result.get("reasons") or []]
        # Missing owner approval is a normal waiting state for every release
        # class, not a production health failure. Other denials still fail closed.
        owner_only_reasons = {
            'production release requires explicit owner approval',
            'protected-core release requires explicit owner approval',
            'owner approval is not bound to the exact candidate sha',
        }
        owner_only = bool(reasons) and all(
            reason.strip().casefold() in owner_only_reasons for reason in reasons
        )
        if owner_only:
            # An informational Teams message is NOT an approval card. Publish
            # the actual lane/blocker rather than implying that a protected
            # release can be approved through an ineligible channel.
            if owner_teams_eligible:
                owner_instruction = (
                    "STATUS ONLY - NOT AN APPROVAL CARD. A signed Teams approval "
                    "offer was published for the exact release. Only a separate "
                    "authenticated owner Approve click can authorize it; "
                    "delivery and a click must each be verified."
                )
            else:
                owner_instruction = (
                    "BLOCKED: no actionable Teams approval is enabled for "
                    "this exact release risk under the running mode and "
                    "reviewed policy. This notice is NOT an approval card. "
                    "Existing exact-SHA owner authorization remains required."
                )
            write_owner_notification_event(
                state_root,
                record,
                "production_owner_action_required",
                owner_action=owner_instruction,
            )
            continue
        raise ReleaseManagerError(
            "Production Eligible release failed production gate: "
            + "; ".join(reasons)
        )
    if superseded:
        print(f"RELEASE_MANAGER_AUTO_DEFERRED=superseded_candidate_count:{superseded}", flush=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--candidate-sha", required=True)
    create.add_argument("--rollback-sha", required=True)
    create.add_argument("--change-class", default="feature")
    create.add_argument("--support-item")
    create.add_argument("--support-pr-number", type=int)
    create.add_argument("--owner-approved", action="store_true")

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--candidate-sha", required=True)
    prepare.add_argument("--change-class", default="feature")
    prepare.add_argument("--support-item")
    prepare.add_argument("--support-pr-number", type=int)
    prepare.add_argument("--owner-approved", action="store_true")
    prepare.add_argument("--reissue-rolled-back", action="store_true")

    preprod = sub.add_parser("preprod")
    preprod.add_argument("--release-id", required=True)

    impact = sub.add_parser("review-impact")
    impact.add_argument("--release-id", required=True)
    impact.add_argument("--include-pr", type=int, action="append", default=[])
    impact.add_argument("--include-commit", action="append", default=[])
    impact.add_argument("--acknowledge-overlapping-pr", type=int, action="append", default=[])
    impact.add_argument("--acknowledge-dirty-worktree", action="append", default=[])
    impact.add_argument("--record", action="store_true")

    approve = sub.add_parser("approve")
    approve.add_argument("--release-id", required=True)
    approve.add_argument("--candidate-sha", required=True)
    approve.add_argument("--source", default="explicit_owner_instruction")

    promote = sub.add_parser("promote")
    promote.add_argument("--release-id", required=True)

    recovery = sub.add_parser("recover-baseline")
    recovery.add_argument("--revision", required=True)
    recovery.add_argument("--owner-approved", action="store_true")

    sub.add_parser("promote-eligible")
    sub.add_parser("approval-only-held")
    renew = sub.add_parser("renew-expired-owner-card")
    renew.add_argument("--release-id", required=True)
    renew.add_argument("--candidate-sha", required=True)
    status = sub.add_parser("status")
    status.add_argument("--release-id")

    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    state_root = args.state_root.expanduser().resolve()
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    if args.command == "create":
        record = create_record(
            repo=repo,
            state_root=state_root,
            candidate_sha=args.candidate_sha,
            rollback_sha=args.rollback_sha,
            change_class=args.change_class,
            owner_approved=args.owner_approved,
            support_item=args.support_item,
            support_pr_number=args.support_pr_number,
        )
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "recover-baseline":
        print(json.dumps(recover_missing_last_known_good(state_root, args.revision, owner_approved=args.owner_approved), indent=2))
        return 0
    if args.command == "prepare":
        record = prepare_release(
            repo=repo,
            state_root=state_root,
            candidate_sha=args.candidate_sha,
            change_class=args.change_class,
            owner_approved=args.owner_approved,
            reissue_rolled_back=args.reissue_rolled_back,
            support_item=args.support_item,
            support_pr_number=args.support_pr_number,
        )
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "preprod":
        record = run_preproduction(repo, state_root, load_record(state_root, args.release_id))
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "review-impact":
        record = load_record(state_root, args.release_id)
        # A durable acknowledgment updates a production-eligible record.
        # Serialize it with promotion, then re-read under the same exclusive
        # transaction lock; a stale record must never overwrite a newer state.
        lock = acquire_production_transaction_lock(repo, state_root, record) if args.record else None
        try:
            if args.record:
                record = load_record(state_root, args.release_id)
            result = manual_release_scope_review(
                repo, state_root, record,
                include_prs=tuple(args.include_pr),
                include_commits=tuple(args.include_commit),
                acknowledged_prs=tuple(args.acknowledge_overlapping_pr),
                acknowledged_worktrees=tuple(args.acknowledge_dirty_worktree),
                record_review=args.record,
            )
        finally:
            if lock is not None:
                release_production_transaction_lock(lock)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED" else 2
    if args.command == "approve":
        record = approve_release(
            repo,
            state_root,
            release_id=args.release_id,
            candidate_sha=args.candidate_sha,
            source=args.source,
        )
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "promote":
        record = deploy_production(repo, state_root, load_record(state_root, args.release_id))
        print(json.dumps(record, indent=2))
        return 0
    if args.command == "approval-only-held":
        print("RELEASE_APPROVAL_ONLY=" + (
            "PUBLISHED" if approval_only_while_promotion_held(repo, state_root)
            else "IDLE"))
        return 0
    if args.command == "renew-expired-owner-card":
        print(json.dumps(request_expired_owner_card_renewal(
            repo, state_root, release_id=args.release_id,
            candidate_sha=args.candidate_sha,
        ), indent=2))
        return 0
    if args.command == "promote-eligible":
        if not production_window_open():
            print("RELEASE_MANAGER=WINDOW_CLOSED")
            return 0
        print("RELEASE_MANAGER=" + ("PROMOTED" if promote_eligible(repo, state_root) else "IDLE"))
        return 0
    if args.command == "status":
        if args.release_id:
            print(json.dumps(load_record(state_root, args.release_id), indent=2))
        else:
            records = state_root / "records"
            payload = []
            if records.exists():
                for path in sorted(records.glob("*.json")):
                    payload.append(json.loads(path.read_text(encoding="utf-8")))
            print(json.dumps(payload, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
