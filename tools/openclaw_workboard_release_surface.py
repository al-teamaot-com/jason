"""One additional release surface inside the EXISTING Jason Release Manager.

No independent release command, approval adapter, or gateway mutation CLI.
Only the already-signed, serialized, exact-revision native transaction may call
activate(). Preproduction may call plan() without side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from openclaw_workboard_release_scope import candidate_for, verify, WorkboardScopeError, sha

SOURCE_DECLARATION = Path("config/openclaw-workboard-activation.json")
GATEWAY_CONFIG = Path("/opt/jason/services/openclaw/data/config/openclaw.json")
GATEWAY_COMPOSE = Path("/opt/jason/services/openclaw/docker-compose.yml")
GATEWAY_NAME = "openclaw-openclaw-gateway-1"
SIGNED_OWNER_SOURCE = re.compile(r"^authenticated_mobile_teams_owner:relapproval-[0-9a-f]{32}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class WorkboardReleaseError(RuntimeError):
    pass


def source_declaration(repo: Path) -> dict[str, Any]:
    path = repo / SOURCE_DECLARATION
    if path.is_symlink():
        raise WorkboardReleaseError("source Workboard declaration symlink rejected")
    if not path.exists():
        # Historical known-good releases predate this optional surface.
        return {"schema_version": "1.0", "profile": "off"}
    if not path.is_file():
        raise WorkboardReleaseError("source Workboard declaration must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkboardReleaseError("Workboard source declaration invalid") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise WorkboardReleaseError("unsupported Workboard declaration schema")
    if value.get("profile") == "off" and set(value) == {"schema_version", "profile"}:
        return value
    required = {"schema_version", "profile", "candidate_id",
                "base_config_sha256", "candidate_config_sha256",
                "rollback_config_sha256", "reviewed_scope_sha256", "image_id"}
    if set(value) != required or value.get("profile") != "j-man-j-dev-workboard-v1":
        raise WorkboardReleaseError("unreviewed Workboard activation profile")
    image_id = value.get("image_id")
    if not isinstance(image_id, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise WorkboardReleaseError("exact gateway image ID missing")
    return value


def plan(repo: Path, config_path: Path = GATEWAY_CONFIG) -> dict[str, Any]:
    """Read-only immutable release preflight. Returns no sensitive configuration."""
    declaration = source_declaration(repo)
    if declaration["profile"] == "off":
        return {"status": "off", "requires_gateway_restart": False}
    if config_path.is_symlink() or not config_path.is_file():
        raise WorkboardReleaseError("gateway configuration path unsafe")
    try:
        baseline = config_path.read_bytes()
        target = candidate_for(json.loads(baseline))
        candidate = (json.dumps(target, indent=2, ensure_ascii=False) + "\n").encode()
        result = verify(baseline, declaration, candidate_bytes=candidate)
    except (OSError, ValueError, WorkboardScopeError) as exc:
        raise WorkboardReleaseError("candidate does not match reviewed source scope") from exc
    return {**result, "status": "ready", "requires_gateway_restart": True,
            "image_id": declaration["image_id"], "candidate": candidate}


def require_teams_owner_release(record: dict[str, Any]) -> str:
    if not isinstance(record, dict):
        raise WorkboardReleaseError("release record absent")
    approval = record.get("owner_approval") or {}
    candidate_sha = (record.get("release_candidate") or {}).get("candidate_sha")
    if (not isinstance(candidate_sha, str) or HEX40.fullmatch(candidate_sha) is None
            or approval.get("approved") is not True
            or approval.get("candidate_sha") != candidate_sha
            or not isinstance(approval.get("source"), str)
            or SIGNED_OWNER_SOURCE.fullmatch(approval["source"]) is None):
        raise WorkboardReleaseError("no exact signed Teams Owner release grant")
    return candidate_sha


def _atomic_write(path: Path, content: bytes) -> None:
    fd, raw = tempfile.mkstemp(prefix=".jason-workboard-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode))
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


class GatewayOps:
    """All mutations happen only after the calling Release Manager verifies Teams and freeze."""
    def image_id(self) -> str:
        result = subprocess.run(
            ["docker", "inspect", GATEWAY_NAME, "--format", "{{.Image}}"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return result.stdout.strip()

    def restart(self) -> None:
        subprocess.run(
            ["docker", "compose", "-f", str(GATEWAY_COMPOSE), "up", "-d",
             "--no-deps", "--no-build", "--force-recreate", "openclaw-gateway"],
            cwd=GATEWAY_COMPOSE.parent, timeout=120, check=True,
            capture_output=True, text=True,
        )

    def workboard_enabled(self) -> bool:
        # The new plugin must actually load after the exact container restart.
        result = subprocess.run(
            ["docker", "exec", GATEWAY_NAME,
             "openclaw", "workboard", "list", "--json"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return result.returncode == 0 and (
            result.stdout.strip().startswith("{") or
            result.stdout.strip().startswith("[")
        )

    def health(self) -> bool:
        for _ in range(12):
            result = subprocess.run(
                ["docker", "inspect", GATEWAY_NAME, "--format",
                 "{{if .State.Health}}{{.State.Health.Status}}{{end}}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if result.returncode == 0 and result.stdout.strip() == "healthy":
                return True
            time.sleep(5)
        return False



def verify_active(
    repo: Path, config_path: Path = GATEWAY_CONFIG, ops: GatewayOps | None = None,
) -> dict[str, Any]:
    """Read-only native postflight; does not initiate, retry, or approve changes."""
    declaration = source_declaration(repo)
    if declaration["profile"] == "off":
        return {"status": "off"}
    if config_path.is_symlink() or not config_path.is_file():
        raise WorkboardReleaseError("gateway config postflight unsafe")
    agent = ops or GatewayOps()
    if (sha(config_path.read_bytes()) != declaration["candidate_config_sha256"]
            or agent.image_id() != declaration["image_id"]
            or not agent.health() or not agent.workboard_enabled()):
        raise WorkboardReleaseError("Workboard gateway active state not verified")
    return {"status": "active_verified", "config_sha256": declaration["candidate_config_sha256"]}



def _backup_path(state_root: Path, release_id: str) -> Path:
    if not re.fullmatch(r"release-[0-9a-f]{16}", release_id):
        raise WorkboardReleaseError("invalid release identity")
    folder = state_root / "openclaw-workboard-release-backups"
    if folder.is_symlink():
        raise WorkboardReleaseError("backup folder is a symlink")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder / (release_id + ".baseline")




def _journal_path(backup: Path) -> Path:
    return backup.with_name(backup.name + ".journal.json")


def _write_journal(path: Path, document: dict[str, Any], *, first: bool = False) -> None:
    raw = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    if first:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        if path.is_symlink() or not path.is_file():
            raise WorkboardReleaseError("journal is unavailable for verified update")
        _atomic_write(path, raw)


def _journal_transition(path: Path, new_status: str) -> None:
    if new_status not in {"applied", "restored", "committed"}:
        raise WorkboardReleaseError("unknown Workboard journal status")
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise WorkboardReleaseError("release journal could not be read") from exc
    if doc.get("status") not in {"prepared", "applied", "restored"}:
        raise WorkboardReleaseError("Workboard journal state is not transitionable")
    doc["status"] = new_status
    doc["updated_at"] = int(time.time())
    _write_journal(path, doc)


def recover_interrupted(
    state_root: Path, *,
    config_path: Path = GATEWAY_CONFIG,
    ops: GatewayOps | None = None,
) -> list[dict[str, str]]:
    """Reconcile previously signed unfinished gateway changes UNDER native lock.

    Never activate, never request approval. A closed release is preserved only
    when its recorded exact active gateway bytes, image and plugin verify.
    Otherwise an interrupted pre-close transaction restores its own 0600 backup.
    """
    directory = state_root / "openclaw-workboard-release-backups"
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise WorkboardReleaseError("unsafe recovery journal directory")
    if config_path.is_symlink() or not config_path.is_file():
        raise WorkboardReleaseError("unsafe gateway configuration for recovery")
    agent = ops or GatewayOps()
    actions = []
    for journal_path in sorted(directory.glob("release-*.baseline.journal.json")):
        if journal_path.is_symlink() or not journal_path.is_file():
            raise WorkboardReleaseError("unsafe Workboard recovery journal")
        try:
            journal = json.loads(journal_path.read_text())
        except (OSError, ValueError) as exc:
            raise WorkboardReleaseError("malformed recovery journal") from exc
        status = journal.get("status")
        if status in {"restored", "committed"}:
            continue
        if status not in {"prepared", "applied"}:
            raise WorkboardReleaseError("unknown active Workboard recovery state")
        release_id = journal.get("release_id")
        if not isinstance(release_id, str) or not re.fullmatch(r"release-[0-9a-f]{16}", release_id):
            raise WorkboardReleaseError("invalid recovery release ID")
        if journal_path != _journal_path(_backup_path(state_root, release_id)):
            raise WorkboardReleaseError("recovery journal path does not match release identity")
        backup = _backup_path(state_root, release_id)
        if backup.is_symlink() or not backup.is_file():
            raise WorkboardReleaseError("recovery baseline is missing")
        baseline = backup.read_bytes()
        if sha(baseline) != journal.get("baseline_sha256"):
            raise WorkboardReleaseError("recovery backup modified")
        path = state_root / "records" / (release_id + ".json")
        if path.is_symlink() or not path.is_file():
            raise WorkboardReleaseError("native release record missing for recovery")
        record = json.loads(path.read_text())
        require_teams_owner_release(record)
        if record.get("release_id") != release_id:
            raise WorkboardReleaseError("recovery record identity mismatch")
        if journal.get("candidate_sha") != (record.get("release_candidate") or {}).get("candidate_sha"):
            raise WorkboardReleaseError("recovery journal revision differs from signed release")
        if agent.image_id() != journal.get("image_id"):
            raise WorkboardReleaseError("gateway image changed during recovery")
        current_sha = sha(config_path.read_bytes())
        candidate_sha256 = journal.get("candidate_config_sha256")
        if current_sha not in {journal["baseline_sha256"], candidate_sha256}:
            raise WorkboardReleaseError("gateway configuration drift; refuse automatic overwrite")
        if record.get("state") == "closed":
            if current_sha != candidate_sha256 or not agent.health() or not agent.workboard_enabled():
                raise WorkboardReleaseError("closed release gateway no longer matches reviewed active state")
            _journal_transition(journal_path, "committed")
            actions.append({"release_id": release_id, "result": "committed_verified"})
            continue
        if current_sha != journal["baseline_sha256"]:
            _atomic_write(config_path, baseline)
            agent.restart()
        if config_path.read_bytes() != baseline or not agent.health() or agent.image_id() != journal["image_id"]:
            raise WorkboardReleaseError("interrupted gateway rollback not verified")
        _journal_transition(journal_path, "restored")
        actions.append({"release_id": release_id, "result": "interrupted_restored"})
    return actions



def activate(
    repo: Path, state_root: Path, record: dict[str, Any],
    *, config_path: Path = GATEWAY_CONFIG, ops: GatewayOps | None = None,
) -> dict[str, Any]:
    """Called ONLY inside an existing exact Teams-approved native release transaction."""
    declaration = source_declaration(repo)
    if declaration["profile"] == "off":
        return {"status": "off"}
    candidate_sha = require_teams_owner_release(record)
    expected_id = "release-" + candidate_sha[:16]
    if record.get("release_id") != expected_id:
        raise WorkboardReleaseError("native release identity does not match exact SHA")
    current = plan(repo, config_path)
    agent = ops or GatewayOps()
    if agent.image_id() != declaration["image_id"]:
        raise WorkboardReleaseError("gateway image differs from reviewed scope")
    baseline = config_path.read_bytes()
    backup = _backup_path(state_root, expected_id)
    if backup.exists() or backup.is_symlink():
        raise WorkboardReleaseError("release backup already exists; replay blocked")
    fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(baseline)
        stream.flush()
        os.fsync(stream.fileno())
    journal = _journal_path(backup)
    _write_journal(journal, {
        "schema_version": "1.0",
        "release_id": expected_id,
        "candidate_sha": candidate_sha,
        "baseline_sha256": declaration["rollback_config_sha256"],
        "candidate_config_sha256": declaration["candidate_config_sha256"],
        "image_id": declaration["image_id"],
        "status": "prepared",
        "recorded_at": int(time.time()),
    }, first=True)
    # From this point an exception must restore the exact baseline.
    try:
        _atomic_write(config_path, current["candidate"])
        agent.restart()
        if (not agent.health() or not agent.workboard_enabled()
                or sha(config_path.read_bytes()) != declaration["candidate_config_sha256"]
                or agent.image_id() != declaration["image_id"]):
            raise WorkboardReleaseError("gateway activation verification failed")
        _journal_transition(journal, "applied")
    except BaseException:
        _atomic_write(config_path, baseline)
        agent.restart()
        if (not agent.health() or config_path.read_bytes() != baseline
                or agent.image_id() != declaration["image_id"]):
            raise WorkboardReleaseError("gateway rollback verification FAILED")
        _journal_transition(journal, "restored")
        raise
    return {"status": "active", "candidate_sha": candidate_sha,
            "config_sha256": declaration["candidate_config_sha256"],
            "backup_path": str(backup), "image_id": declaration["image_id"]}




def rollback_if_prepared(
    repo: Path, state_root: Path, record: dict[str, Any],
    *, config_path: Path = GATEWAY_CONFIG, ops: GatewayOps | None = None,
) -> dict[str, Any]:
    """Native catch-path: no backup means activation never mutated the gateway.

    The release backup is created and fsynced BEFORE any gateway write. If an
    earlier image/baseline preflight failed, safely verify the unchanged config
    without causing a redundant restart or a fabricated failed rollback.
    """
    declaration = source_declaration(repo)
    if declaration["profile"] == "off":
        return {"status": "off"}
    candidate_sha = require_teams_owner_release(record)
    if record.get("release_id") != "release-" + candidate_sha[:16]:
        raise WorkboardReleaseError("native release identity invalid")
    backup = _backup_path(state_root, record["release_id"])
    if not backup.exists() and not backup.is_symlink():
        if (config_path.is_symlink() or not config_path.is_file()
                or sha(config_path.read_bytes()) != declaration["base_config_sha256"]):
            raise WorkboardReleaseError("missing Workboard backup but configuration drifted")
        return {"status": "not_mutated_prebackup"}
    return rollback(repo, state_root, record, config_path=config_path, ops=ops)



def rollback(
    repo: Path, state_root: Path, record: dict[str, Any],
    *, config_path: Path = GATEWAY_CONFIG, ops: GatewayOps | None = None,
) -> dict[str, Any]:
    """Release Manager rollback only, not a separately authorized command."""
    declaration = source_declaration(repo)
    if declaration["profile"] == "off":
        return {"status": "off"}
    candidate_sha = require_teams_owner_release(record)
    backup = _backup_path(state_root, "release-" + candidate_sha[:16])
    if backup.is_symlink() or not backup.is_file():
        raise WorkboardReleaseError("verified rollback baseline missing")
    baseline = backup.read_bytes()
    if sha(baseline) != declaration["rollback_config_sha256"]:
        raise WorkboardReleaseError("rollback baseline hash differs from source")
    agent = ops or GatewayOps()
    # Safe to skip an unnecessary restart if exact baseline is already active.
    if config_path.read_bytes() != baseline:
        _atomic_write(config_path, baseline)
        agent.restart()
    if (not agent.health() or config_path.read_bytes() != baseline
            or agent.image_id() != declaration["image_id"]):
        raise WorkboardReleaseError("gateway rollback verification FAILED")
    journal = _journal_path(backup)
    if journal.is_file():
        _journal_transition(journal, "restored")
    return {"status": "restored_and_verified",
            "rollback_config_sha256": declaration["rollback_config_sha256"]}
