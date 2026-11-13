#!/usr/bin/env python3
"""Exact Owner-authenticated sparse root-source bootstrap (not self-installing).

This is a fixed-scope future root-installed tool. It stages only the 13
reviewed Stage A0 source blobs under /opt/jason/releases/<current-main-SHA>,
without switching /opt/jason/current or replacing containers. Its code,
source validator and CI attestor MUST be separately installed root-owned
under an approved trust bootstrap. Running this mutable checkout as root
is denied even if the operator can sudo.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import time
from typing import Any, Callable, Mapping
import uuid

ACTION = "pmv4-stage-a0-sparse-root-source-v1"
ROOT_SCRIPT = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_root_stage.py")
SOURCE_TOOL = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_source.py")
ROOT_CI = Path("/usr/local/lib/jason/pmv4_shadow_ci.py")
AUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
TRUST = Path("/etc/jason-owner-release/verified-owner-public-key.json")
POLICY = Path("/etc/jason-owner-release/pmv4-stage-a0-sparse-root-stage.json")
AUDIT = Path("/etc/jason-owner-release/pmv4-stage-a0-sparse-root-stage-ledger")
LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
CURRENT = Path("/opt/jason/current")
RELEASES = Path("/opt/jason/releases")
REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
MCP = "jason-mcp-pilot"
RUNTIME = "jason-runtime"
FIELDS = {
    "schema_version", "action", "one_shot", "candidate_sha", "lkg_sha",
    "sparse_scope_sha256", "archive_path", "archive_sha256",
    "freeze_sha256", "promotion_hold_sha256", "mcp_image_sha256",
    "runtime_image_sha256", "script_sha256", "source_tool_sha256",
    "ci_attestor_sha256", "auth_helper_sha256", "owner_verifier_sha256",
    "owner_authentication", "install_scope", "no_services_changed",
    "no_provider_writes",
}


class StageRootDenied(PermissionError):
    pass


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def secure_root_read(path: Path, *, max_bytes: int = 128 * 1024,
                     root_parent: bool = True) -> bytes:
    if path.is_symlink():
        raise StageRootDenied("A0_STAGE_ROOT_SYMLINK")
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022
            or (root_parent and parent.st_uid != 0)):
        raise StageRootDenied("A0_STAGE_ROOT_PARENT_UNTRUSTED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_uid != 0 or meta.st_mode & 0o022
                or meta.st_size > max_bytes):
            raise StageRootDenied("A0_STAGE_ROOT_FILE_UNTRUSTED")
        raw = os.read(fd, max_bytes + 1)
        if len(raw) != meta.st_size:
            raise StageRootDenied("A0_STAGE_ROOT_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def trusted_policy() -> dict[str, Any]:
    p = json.loads(secure_root_read(POLICY, max_bytes=8192))
    if (not isinstance(p, dict) or set(p) != FIELDS
            or p["schema_version"] != "1.0" or p["action"] != ACTION
            or p["one_shot"] is not True
            or p["owner_authentication"] != "fresh-entra-oauth-signed-exact-action"
            or p["install_scope"] != "only-13-pinned-stage-a0-source-files"
            or p["no_services_changed"] is not True
            or p["no_provider_writes"] is not True):
        raise StageRootDenied("A0_STAGE_ROOT_POLICY_SCOPE_INVALID")
    import re
    for key in ("candidate_sha", "lkg_sha"):
        if not isinstance(p[key], str) or re.fullmatch(r"[0-9a-f]{40}", p[key]) is None:
            raise StageRootDenied("A0_STAGE_ROOT_SHA_INVALID")
    if p["candidate_sha"] == p["lkg_sha"]:
        raise StageRootDenied("A0_STAGE_ROOT_SOURCE_EQUALS_ROLLBACK")
    for key in ("mcp_image_sha256", "runtime_image_sha256"):
        if not isinstance(p[key], str) or re.fullmatch(r"sha256:[0-9a-f]{64}", p[key]) is None:
            raise StageRootDenied("A0_STAGE_ROOT_IMAGE_INVALID")
    for key in ("sparse_scope_sha256", "archive_sha256", "freeze_sha256",
                "promotion_hold_sha256"):
        if not isinstance(p[key], str) or re.fullmatch(r"[0-9a-f]{64}", p[key]) is None:
            raise StageRootDenied("A0_STAGE_ROOT_DIGEST_INVALID")
    archive = Path(p["archive_path"])
    if (archive != Path("/srv/jason/archive") /
                 ("pmv4-stage-a0-sparse-" + p["candidate_sha"] + ".tar")):
        raise StageRootDenied("A0_STAGE_ROOT_ARCHIVE_PATH_MISMATCH")
    for key, filename in (
        ("script_sha256", ROOT_SCRIPT), ("source_tool_sha256", SOURCE_TOOL),
        ("ci_attestor_sha256", ROOT_CI), ("auth_helper_sha256", AUTH),
        ("owner_verifier_sha256", VERIFIER),
    ):
        item = p[key]
        if (not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None
                or digest(secure_root_read(filename, max_bytes=1024 * 1024)) != item):
            raise StageRootDenied("A0_STAGE_ROOT_EXECUTABLE_HASH_MISMATCH")
    return p


def _load_trusted(path: Path, name: str) -> Any:
    secure_root_read(path, max_bytes=1024 * 1024)
    module = importlib.util.spec_from_file_location(name, path)
    if module is None or module.loader is None:
        raise StageRootDenied("A0_STAGE_ROOT_LIBRARY_LOAD_FAILED")
    obj = importlib.util.module_from_spec(module)
    module.loader.exec_module(obj)
    return obj


def docker(name: str) -> dict[str, Any]:
    out = subprocess.check_output(["docker", "inspect", name], timeout=15, text=True)
    rows = json.loads(out)
    if not isinstance(rows, list) or len(rows) != 1:
        raise StageRootDenied("A0_STAGE_DOCKER_INCOMPLETE")
    return rows[0]


def protected_preflight(policy: Mapping[str, Any]) -> dict[str, str]:
    control = json.loads(secure_root_read(CONTROL, root_parent=False))
    drift = json.loads(secure_root_read(DRIFT, root_parent=False))
    lkg = (control.get("last_known_good") or {}).get("manifest") or {}
    if (control.get("circuit_breaker", {}).get("state") != "closed"
            or lkg.get("complete") is not True
            or drift.get("status") != "pass" or drift.get("problems") != []):
        raise StageRootDenied("A0_STAGE_BREAKER_OR_DRIFT_UNHEALTHY")
    stamp = datetime.fromisoformat(str(drift.get("observed_at") or "").replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    if stamp.tzinfo is None or not -10 <= age <= 180:
        raise StageRootDenied("A0_STAGE_STALE_ROOT_DRIFT")
    if (CURRENT.resolve(strict=True) != RELEASES / policy["lkg_sha"]
            or digest(FREEZE.read_bytes()) != policy["freeze_sha256"]
            or digest(HOLD.read_bytes()) != policy["promotion_hold_sha256"]):
        raise StageRootDenied("A0_STAGE_PROTECTED_PRODUCTION_CHANGED")
    for key, expected in (
        ("revision", policy["lkg_sha"]),
        ("host_revision", policy["lkg_sha"]),
        ("runtime_revision", policy["lkg_sha"]),
        ("mcp_revision", policy["lkg_sha"]),
        ("runtime_image_id", policy["runtime_image_sha256"]),
        ("mcp_image_id", policy["mcp_image_sha256"]),
    ):
        if lkg.get(key) != expected:
            raise StageRootDenied("A0_STAGE_LKG_DRIFT:" + key)
    runtime, mcp = docker(RUNTIME), docker(MCP)
    if (runtime.get("Image") != policy["runtime_image_sha256"]
            or mcp.get("Image") != policy["mcp_image_sha256"]
            or runtime.get("State", {}).get("Health", {}).get("Status") != "healthy"
            or mcp.get("State", {}).get("Status") != "running"):
        raise StageRootDenied("A0_STAGE_LIVE_CONTAINER_DRIFT")
    for obj in (runtime, mcp):
        if (obj.get("Config", {}).get("Labels") or {}).get(
                "com.teamaot.jason.source_revision") != policy["lkg_sha"]:
            raise StageRootDenied("A0_STAGE_LIVE_SOURCE_DRIFT")
    return {"runtime_id": runtime["Id"], "mcp_id": mcp["Id"]}


@contextmanager
def existing_host_lock():
    fd = os.open(LOCK, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 1000
                or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o664):
            raise StageRootDenied("A0_STAGE_LEGACY_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StageRootDenied("A0_STAGE_LEGACY_LOCK_BUSY") from exc
        yield
    finally:
        os.close(fd)


def _write_root(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, mode)
        if os.write(fd, data) != len(data):
            raise StageRootDenied("A0_STAGE_ROOT_PARTIAL_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)


def exact_source_archive(policy: Mapping[str, Any],
                         module: Any) -> tuple[dict[str, Any], bytes]:
    # Fixed archive name and checksum; never execute any bytes from this file.
    source = Path(policy["archive_path"])
    if source.is_symlink():
        raise StageRootDenied("A0_STAGE_ARCHIVE_UNAVAILABLE")
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != 1000 or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 16 * 1024 * 1024):
            raise StageRootDenied("A0_STAGE_ARCHIVE_UNTRUSTED_METADATA")
        raw = os.read(fd, info.st_size + 1)
        if len(raw) != info.st_size or digest(raw) != policy["archive_sha256"]:
            raise StageRootDenied("A0_STAGE_ARCHIVE_DIGEST_CHANGED")
    finally:
        os.close(fd)
    blob = module.git_object(REPO)
    scope = module.source_manifest(
        policy["candidate_sha"], blob,
        freeze_sha256=policy["freeze_sha256"],
        current_lkg=policy["lkg_sha"],
    )
    if scope["scope_sha256"] != policy["sparse_scope_sha256"]:
        raise StageRootDenied("A0_STAGE_SCOPE_MISMATCH")
    module.verify_package(raw, scope)
    # Independently compare every admitted blob to exact Git objects.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for row in scope["files"]:
            entry = archive.extractfile(row["path"])
            if entry is None or entry.read() != blob(policy["candidate_sha"], row["path"]):
                raise StageRootDenied("A0_STAGE_GIT_OBJECT_MISMATCH")
    return scope, raw


def _rename_no_replace(source: Path, target: Path) -> None:
    """Never overwrite even an empty directory created in a race."""
    import ctypes
    import errno
    libc = ctypes.CDLL(None, use_errno=True)
    fn = getattr(libc, "renameat2", None)
    if fn is None:
        raise StageRootDenied("A0_STAGE_ATOMIC_RENAME_UNAVAILABLE")
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p,
                   ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    rc = fn(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    if rc != 0:
        raise StageRootDenied("A0_STAGE_ATOMIC_CREATE_REFUSED")


def recover_exact_source(release_root: Path,
                         scope: Mapping[str, Any]) -> bool:
    """Only owned Stage A0 sources, including partial writes, may be removed."""
    target = release_root / scope["candidate_sha"]
    scratch = release_root / (".pmv4-a0-stage-" + scope["candidate_sha"])
    existing = [p for p in (target, scratch) if p.exists() or p.is_symlink()]
    if len(existing) > 1:
        raise StageRootDenied("A0_STAGE_MULTIPLE_RECOVERY_TARGETS")
    if not existing:
        return True
    root = existing[0]
    if (root.is_symlink() or not root.is_dir()
            or root.stat().st_uid != 0
            or stat.S_IMODE(root.stat().st_mode) not in (0o700, 0o755)):
        raise StageRootDenied("A0_STAGE_RECOVERY_ROOT_UNTRUSTED")
    allowed = {row["path"]: row for row in scope["files"]}
    dirs: set[str] = set()
    for name in allowed:
        path = Path(name).parent
        while str(path) != ".":
            dirs.add(path.as_posix())
            path = path.parent
    # Verify *all* existing inodes before touching any of them.
    for node in root.rglob("*"):
        if node.is_symlink():
            raise StageRootDenied("A0_STAGE_RECOVERY_FOREIGN_LINK")
        rel = node.relative_to(root).as_posix()
        meta = node.lstat()
        if node.is_dir():
            if (rel not in dirs or meta.st_uid != 0 or meta.st_gid != 0
                    or stat.S_IMODE(meta.st_mode) != 0o755):
                raise StageRootDenied("A0_STAGE_RECOVERY_FOREIGN_DIRECTORY")
        elif node.is_file():
            row = allowed.get(rel)
            if (row is None or meta.st_uid != 0 or meta.st_gid != 0
                    or meta.st_nlink != 1
                    or stat.S_IMODE(meta.st_mode) != 0o444
                    or meta.st_size != row["size"]
                    or digest(node.read_bytes()) != row["sha256"]):
                raise StageRootDenied("A0_STAGE_RECOVERY_FOREIGN_FILE")
        else:
            raise StageRootDenied("A0_STAGE_RECOVERY_SPECIAL_OBJECT")
    for name in allowed:
        obj = root / name
        if obj.is_file():
            obj.unlink()
    for name in sorted(dirs, key=lambda item: (item.count("/"), item),
                       reverse=True):
        directory = root / name
        if directory.is_dir():
            directory.rmdir()
    root.rmdir()
    return not root.exists()


def stage_root_copy(release_root: Path, scope: Mapping[str, Any], tar_bytes: bytes,
                    *, after_step: Callable[[str], None] | None = None) -> Path:
    """Restricted file-copy core. Caller must hold lock and verify Owner/CI."""
    target = release_root / scope["candidate_sha"]
    scratch = release_root / (".pmv4-a0-stage-" + scope["candidate_sha"])
    if (target.exists() or target.is_symlink()
            or scratch.exists() or scratch.is_symlink()
            or release_root.is_symlink()):
        raise StageRootDenied("A0_STAGE_RELEASE_SOURCE_TARGET_NOT_EMPTY")
    try:
        scratch.mkdir(mode=0o700)
        paths = tuple(row["path"] for row in scope["files"])
        dirs = set()
        for name in paths:
            parent = Path(name).parent
            while str(parent) != ".":
                dirs.add(parent.as_posix())
                parent = parent.parent
        for directory in sorted(dirs, key=lambda name: (name.count("/"), name)):
            p = scratch / directory
            p.mkdir(mode=0o755)
            os.chown(p, 0, 0)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as source:
            for row in scope["files"]:
                path = scratch / row["path"]
                data = source.extractfile(row["path"]).read()
                if digest(data) != row["sha256"]:
                    raise StageRootDenied("A0_STAGE_BLOB_REVALIDATION_FAILED")
                _write_root(path, data, mode=0o444)
                if after_step:
                    after_step(row["path"])
        for directory in dirs:
            os.chmod(scratch / directory, 0o755)
        os.chmod(scratch, 0o755)
        verify_staged_source(scratch, scope)
        if target.exists() or target.is_symlink():
            raise StageRootDenied("A0_STAGE_TARGET_RACE")
        _rename_no_replace(scratch, target)
        return target
    except Exception as exc:
        try:
            if not recover_exact_source(release_root, scope):
                raise StageRootDenied("A0_STAGE_RECOVERY_NOT_EMPTY")
        except Exception as rollback_error:
            raise StageRootDenied("A0_STAGE_FAILED_ROOT_RECOVERY_REQUIRES_REVIEW") from rollback_error
        raise StageRootDenied("A0_STAGE_FAILED_EMPTY_ROLLBACK_VERIFIED") from exc


def verify_staged_source(root: Path, scope: Mapping[str, Any]) -> None:
    allowed = {row["path"]: row for row in scope["files"]}
    expected_dirs: set[str] = set()
    for path in allowed:
        p = Path(path).parent
        while str(p) != ".":
            expected_dirs.add(p.as_posix())
            p = p.parent
    found_files = set()
    found_dirs = set()
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid != 0:
        raise StageRootDenied("A0_STAGE_ROOT_DIRECTORY_UNTRUSTED")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise StageRootDenied("A0_STAGE_UNEXPECTED_SYMLINK")
        relative = path.relative_to(root).as_posix()
        meta = path.lstat()
        if path.is_dir():
            if (relative not in expected_dirs or meta.st_uid != 0
                    or stat.S_IMODE(meta.st_mode) != 0o755):
                raise StageRootDenied("A0_STAGE_FOREIGN_DIRECTORY")
            found_dirs.add(relative)
        elif path.is_file():
            expected = allowed.get(relative)
            if (not expected or meta.st_uid != 0 or meta.st_gid != 0
                    or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o444
                    or digest(path.read_bytes()) != expected["sha256"]):
                raise StageRootDenied("A0_STAGE_FOREIGN_OR_TAMPERED_FILE")
            found_files.add(relative)
        else:
            raise StageRootDenied("A0_STAGE_SPECIAL_OBJECT")
    if found_files != set(allowed) or found_dirs != expected_dirs:
        raise StageRootDenied("A0_STAGE_SOURCE_INCOMPLETE")


def fresh_owner(helper: Any, policy: Mapping[str, Any]) -> str:
    entry = "https://login.microsoftonline.com/" + helper.TENANT + "/oauth2/v2.0/"
    challenge = helper._form(entry + "devicecode",
                             {"client_id": helper.CLIENT_ID, "scope": helper.SCOPE})
    if not all(isinstance(challenge.get(k), str)
               for k in ("device_code", "user_code", "verification_uri")):
        raise StageRootDenied("A0_STAGE_OWNER_OAUTH_UNAVAILABLE")
    duration = min(int(challenge.get("expires_in", 0)), 600)
    if duration < 60:
        raise StageRootDenied("A0_STAGE_OWNER_OAUTH_TOO_SHORT")
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("ONLY_SOURCE_SHA=" + policy["candidate_sha"], flush=True)
    print("SOURCE_SCOPE_SHA256=" + policy["sparse_scope_sha256"], flush=True)
    print("NO_RUNTIME_OR_MCP_REPLACEMENT=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    deadline = time.monotonic() + duration
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    while time.monotonic() < deadline:
        time.sleep(interval)
        token = helper._form(entry + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": helper.CLIENT_ID, "device_code": challenge["device_code"],
        })
        if isinstance(token.get("access_token"), str):
            owner = helper.jwt_owner(token["access_token"])
            if input("Confirm exact action with APPROVE-EXACT-PMV4-A0-SPARSE-SOURCE-ONLY: ").strip() != "APPROVE-EXACT-PMV4-A0-SPARSE-SOURCE-ONLY":
                raise StageRootDenied("A0_EXPLICIT_EXACT_ACTION_CONSENT_DENIED")
            return owner
        if token.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif token.get("error") != "authorization_pending":
            raise StageRootDenied("A0_STAGE_OWNER_OAUTH_DENIED")
    raise StageRootDenied("A0_STAGE_OWNER_OAUTH_EXPIRED")


def signed_stage_owner_proof(policy: Mapping[str, Any], owner_oid: str,
                             verifier: Any) -> dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if owner_oid not in verifier.EXACT_OWNER_OAUTH_SUBJECTS:
        raise StageRootDenied("A0_STAGE_OWNER_SUBJECT_DENIED")
    fd = os.open(SIGNER, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 1000
                or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o400
                or meta.st_size != 32):
            raise StageRootDenied("A0_STAGE_OWNER_SIGNER_UNTRUSTED")
        raw = os.read(fd, 33)
    finally:
        os.close(fd)
    if len(raw) != 32:
        raise StageRootDenied("A0_STAGE_OWNER_SIGNER_CHANGED")
    signer = Ed25519PrivateKey.from_private_bytes(raw)
    root_public = verifier.read_pinned_root_owner_public_key(TRUST)
    if verifier.public_key_sha256(signer.public_key()) != verifier.public_key_sha256(root_public):
        raise StageRootDenied("A0_STAGE_OWNER_SIGNER_NOT_ROOT_PINNED")
    at = datetime.now(timezone.utc)
    proof = verifier.issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid.uuid4().hex,
        release_id="release-" + policy["candidate_sha"][:16],
        candidate_sha=policy["candidate_sha"], rollback_sha=policy["lkg_sha"],
        scope_sha256=policy["sparse_scope_sha256"],
        manifest_sha256=digest(canonical(policy)),
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=verifier.TID, verified_owner_oid=owner_oid,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[owner_oid],
        verified_organization_id="aot", confirmed_decision="approve",
        at=at, private_key=signer,
    )
    verifier.verify_exact_owner_release(
        proof, public_key=root_public, at=at,
        expected_candidate_sha=policy["candidate_sha"],
        expected_rollback_sha=policy["lkg_sha"],
        expected_release_id="release-" + policy["candidate_sha"][:16],
        expected_scope_sha256=policy["sparse_scope_sha256"],
        expected_manifest_sha256=digest(canonical(policy)),
        expected_freeze_sha256=policy["freeze_sha256"],
    )
    return proof


def protected_ci_as_operator(ci: Any, candidate_sha: str) -> bool:
    """Use the existing unprivileged GitHub identity, never root credentials."""
    def run_as_al(argv: list[str], **kwargs: Any) -> Any:
        return subprocess.run(
            ["/usr/sbin/runuser", "-u", "al", "--", *argv], **kwargs,
        )
    return ci.protected_main_ci_verified(candidate_sha, runner=run_as_al) is True


def execute() -> None:
    if (os.geteuid() != 0 or sys.flags.isolated != 1
            or Path(__file__).resolve(strict=True) != ROOT_SCRIPT):
        raise StageRootDenied("A0_STAGE_ROOT_INSTALLED_ISOLATED_CODE_REQUIRED")
    policy = trusted_policy()
    audit = AUDIT.lstat()
    if (AUDIT.is_symlink() or audit.st_uid != 0
            or stat.S_IMODE(audit.st_mode) != 0o700
            or any(AUDIT.glob(ACTION + ".*"))):
        raise StageRootDenied("A0_STAGE_OWNER_AUDIT_ALREADY_CLAIMED_OR_UNSAFE")
    source = _load_trusted(SOURCE_TOOL, "a0_sparse_root_trusted_source")
    verifier = _load_trusted(VERIFIER, "a0_sparse_root_trusted_signer")
    ci = _load_trusted(ROOT_CI, "a0_sparse_root_trusted_ci")
    helper = _load_trusted(AUTH, "a0_sparse_root_trusted_owner_oauth")
    helper.trusted_signer()
    before = protected_preflight(policy)
    scope, data = exact_source_archive(policy, source)
    if not protected_ci_as_operator(ci, policy["candidate_sha"]):
        raise StageRootDenied("A0_STAGE_PROTECTED_MAIN_CI_NOT_VERIFIED")
    approved_owner = fresh_owner(helper, policy)
    proof = signed_stage_owner_proof(policy, approved_owner, verifier)
    with existing_host_lock():
        if trusted_policy() != policy or protected_preflight(policy) != before:
            raise StageRootDenied("A0_STAGE_PRODUCTION_CHANGED_DURING_OWNER_AUTH")
        if not protected_ci_as_operator(ci, policy["candidate_sha"]):
            raise StageRootDenied("A0_STAGE_CI_CHANGED_DURING_OWNER_AUTH")
        rootinfo = RELEASES.lstat()
        if (RELEASES.is_symlink() or rootinfo.st_uid != 0
                or not stat.S_ISDIR(rootinfo.st_mode)
                or rootinfo.st_mode & 0o022):
            raise StageRootDenied("A0_STAGE_RELEASE_DIRECTORY_UNTRUSTED")
        attempt = AUDIT / (ACTION + ".attempt.json")
        _write_root(attempt, canonical({
            "schema_version": "1.0", "action": ACTION,
            "candidate_sha": policy["candidate_sha"],
            "archive_sha256": policy["archive_sha256"],
            "sparse_scope_sha256": policy["sparse_scope_sha256"],
            "signed_owner_proof": proof,
            "status": "one_shot_claimed_before_root_write",
        }) + b"\n")
        outcome = {"status": "failed", "schema_version": "1.0",
                   "action": ACTION, "candidate_sha": policy["candidate_sha"]}
        try:
            installed = stage_root_copy(RELEASES, scope, data)
            verify_staged_source(installed, scope)
            if protected_preflight(policy) != before:
                raise StageRootDenied("A0_STAGE_PRODUCTION_HEALTH_CHANGED")
            outcome["status"] = "verified"
            outcome["sparse_source_path"] = str(installed)
            outcome["sparse_scope_sha256"] = scope["scope_sha256"]
        except Exception as exc:
            try:
                outcome["rollback_to_absence"] = recover_exact_source(RELEASES, scope)
            except Exception as rollback_exc:
                outcome["rollback_to_absence"] = False
                raise StageRootDenied("A0_STAGE_FAILED_RECOVERY_REQUIRES_REVIEW") from rollback_exc
            raise StageRootDenied("A0_STAGE_FAILED_EMPTY_ROLLBACK_VERIFIED") from exc
        finally:
            outcome["verified_at"] = datetime.now(timezone.utc).isoformat()
            _write_root(AUDIT / (ACTION + ".result.json"), canonical(outcome) + b"\n")
    print("PMV4_A0_SPARSE_IMMUTABLE_ROOT_SOURCE=VERIFIED")
    print("CURRENT_PRODUCTION_POINTER_CHANGED=false")
    print("MCP_OR_TICKET_RUNTIME_REPLACED=false")


def main() -> int:
    parser = argparse.ArgumentParser()
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--inspect", action="store_true")
    choices.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.inspect:
            print(json.dumps({"status": "source_only_not_installed",
                              "production_mutation": False,
                              "owner_approval_issued": False}, sort_keys=True))
        else:
            execute()
    except (StageRootDenied, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("PMV4_A0_SPARSE_ROOT_STAGE=DENIED " + type(exc).__name__ +
              ":" + str(exc)[:150], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
