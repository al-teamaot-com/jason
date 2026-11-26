#!/usr/bin/env python3
"""Deterministic sparse Stage A0 root-source package, with NO production apply.

The native root Stage A0 worker already verifies source files against immutable
Git blobs. This artifact lets a separately approved root bootstrap transaction
stage exactly those required blobs, never a full runtime/MCP release tree.
It never installs on /opt/jason/releases or changes any running service.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
from typing import Any, Callable, Mapping

SHA = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_VERSION = "1.0"
ROOT_SOURCE = "/opt/jason/releases"
DIRECTORY_MODE = 0o755
FILE_MODE = 0o444
BLOCKED_PREFIXES = (
    "infrastructure/jason-runtime/",
    "infrastructure/jason-mcp/",
    "implementation/runtime_service/",
    "implementation/mcp_service/",
    "config/production-",
)
REQUIRED = (
    "config/pmv4-shadow/docker-compose.yml",
    "implementation/kernel/__init__.py",
    "implementation/kernel/signed_owner_release.py",
    "tools/install_release_host_reconciler.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_ci.py",
    "tools/pmv4_shadow_docker_adapter.py",
    "tools/pmv4_shadow_host_runtime.py",
    "tools/pmv4_shadow_release.py",
    "tools/pmv4_stage_a_admission.py",
    "tools/pmv4_stage_a_native_install.py",
    "tools/pmv4_stage_a_packet.py",
    "tools/release_host_reconcile_worker.py",
)
# This is deliberately NOT a production installer.
PRODUCTION_APPLY_SUPPORTED = False


class SparseSourceDenied(PermissionError):
    pass


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _checked_path(value: str) -> str:
    if (not isinstance(value, str) or not value
            or value.startswith("/") or value.startswith(".")
            or "//" in value or "\\" in value
            or PurePosixPath(value).as_posix() != value
            or any(component in ("", ".", "..") for component in value.split("/"))
            or value.startswith(BLOCKED_PREFIXES)
            or not value.startswith(("tools/", "implementation/kernel/", "config/pmv4-shadow/"))):
        raise SparseSourceDenied("A0_SPARSE_SOURCE_PATH_DENIED")
    return value


def required_paths() -> tuple[str, ...]:
    checked = tuple(_checked_path(x) for x in REQUIRED)
    if len(checked) != len(set(checked)) or len(checked) > 24:
        raise SparseSourceDenied("A0_SPARSE_SOURCE_ALLOWLIST_INVALID")
    return checked


def source_manifest(source_sha: str, git_blob: Callable[[str, str], bytes],
                    *, freeze_sha256: str, current_lkg: str) -> dict[str, Any]:
    if (not isinstance(source_sha, str) or not SHA.fullmatch(source_sha)
            or not isinstance(current_lkg, str) or not SHA.fullmatch(current_lkg)
            or not isinstance(freeze_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", freeze_sha256) is None
            or source_sha == current_lkg):
        raise SparseSourceDenied("A0_SPARSE_EXACT_RELEASE_BINDING_REQUIRED")
    files = []
    for relative in required_paths():
        data = git_blob(source_sha, relative)
        if not isinstance(data, bytes) or len(data) > 1_000_000:
            raise SparseSourceDenied("A0_SPARSE_SOURCE_BLOB_INVALID")
        files.append({
            "path": relative, "sha256": sha256(data).hexdigest(),
            "size": len(data), "mode": "0444", "uid": 0, "gid": 0,
        })
    obj = {
        "schema_version": SCHEMA_VERSION,
        "service": "pmv4-stage-a0-immutable-root-source",
        "candidate_sha": source_sha,
        "rollback_sha": current_lkg,
        "owner_release_required": True,
        "root_install_authorized": False,
        "freeze_sha256": freeze_sha256,
        "target": ROOT_SOURCE + "/" + source_sha,
        "release_mode": "create-only-sparse-root-source",
        "production_services_restart": False,
        "production_core_changes": False,
        "provider_writes": False,
        "files": files,
    }
    obj["scope_sha256"] = sha256(canonical(obj)).hexdigest()
    return obj


def _tarinfo(name: str, *, file: bool, size: int = 0) -> tarfile.TarInfo:
    value = tarfile.TarInfo(name)
    value.uid = 0
    value.gid = 0
    value.uname = "root"
    value.gname = "root"
    value.mode = FILE_MODE if file else DIRECTORY_MODE
    value.mtime = 0
    value.type = tarfile.REGTYPE if file else tarfile.DIRTYPE
    value.size = size
    return value


def _directory_names(paths: tuple[str, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for item in paths:
        parent = PurePosixPath(item).parent
        while str(parent) != ".":
            names.add(str(parent))
            parent = parent.parent
    return tuple(sorted(names, key=lambda name: (name.count("/"), name)))


def package_bytes(manifest: Mapping[str, Any],
                  git_blob: Callable[[str, str], bytes]) -> bytes:
    validate_manifest(manifest)
    data = io.BytesIO()
    rows = tuple(x["path"] for x in manifest["files"])
    with tarfile.open(fileobj=data, mode="w:", format=tarfile.USTAR_FORMAT) as archive:
        for directory in _directory_names(rows):
            archive.addfile(_tarinfo(directory + "/", file=False))
        for row in manifest["files"]:
            raw = git_blob(manifest["candidate_sha"], row["path"])
            if (len(raw) != row["size"] or sha256(raw).hexdigest() != row["sha256"]):
                raise SparseSourceDenied("A0_SPARSE_SOURCE_CHANGED_DURING_PACKAGE")
            archive.addfile(_tarinfo(row["path"], file=True, size=len(raw)),
                            io.BytesIO(raw))
    blob = data.getvalue()
    verify_package(blob, manifest)
    return blob


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if not isinstance(manifest, Mapping):
        raise SparseSourceDenied("A0_SPARSE_MANIFEST_NOT_OBJECT")
    fields = {
        "schema_version", "service", "candidate_sha", "rollback_sha",
        "owner_release_required", "root_install_authorized", "freeze_sha256",
        "target", "release_mode", "production_services_restart",
        "production_core_changes", "provider_writes", "files", "scope_sha256",
    }
    if (set(manifest) != fields
            or manifest["schema_version"] != SCHEMA_VERSION
            or manifest["service"] != "pmv4-stage-a0-immutable-root-source"
            or manifest["release_mode"] != "create-only-sparse-root-source"
            or manifest["owner_release_required"] is not True
            or manifest["root_install_authorized"] is not False
            or any(manifest[k] is not False for k in (
                "production_services_restart", "production_core_changes", "provider_writes"))
            or not isinstance(manifest["candidate_sha"], str)
            or not SHA.fullmatch(manifest["candidate_sha"])
            or not isinstance(manifest["rollback_sha"], str)
            or not SHA.fullmatch(manifest["rollback_sha"])
            or manifest["candidate_sha"] == manifest["rollback_sha"]
            or manifest["target"] != ROOT_SOURCE + "/" + manifest["candidate_sha"]
            or not isinstance(manifest["freeze_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", manifest["freeze_sha256"]) is None
            or not isinstance(manifest["files"], list)
            or tuple(r.get("path") for r in manifest["files"]) != required_paths()):
        raise SparseSourceDenied("A0_SPARSE_MANIFEST_SCOPE_INVALID")
    if len(manifest["files"]) > 24:
        raise SparseSourceDenied("A0_SPARSE_MANIFEST_OVERSIZE")
    for row in manifest["files"]:
        if (not isinstance(row, dict)
                or set(row) != {"path", "sha256", "size", "mode", "uid", "gid"}
                or row["mode"] != "0444"
                or row["uid"] != 0 or row["gid"] != 0
                or type(row["size"]) is not int or not 0 <= row["size"] <= 1_000_000
                or not isinstance(row["sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
            raise SparseSourceDenied("A0_SPARSE_MANIFEST_FILE_INVALID")
    reviewed = dict(manifest)
    signature = reviewed.pop("scope_sha256")
    if (not isinstance(signature, str)
            or sha256(canonical(reviewed)).hexdigest() != signature):
        raise SparseSourceDenied("A0_SPARSE_MANIFEST_DIGEST_INVALID")


def verify_package(blob: bytes, manifest: Mapping[str, Any]) -> None:
    validate_manifest(manifest)
    if not isinstance(blob, bytes) or len(blob) > 16 * 1024 * 1024:
        raise SparseSourceDenied("A0_SPARSE_PACKAGE_OVERSIZE")
    expected_files = {row["path"]: row for row in manifest["files"]}
    expected_dirs = set(_directory_names(tuple(expected_files)))
    observed_files: set[str] = set()
    observed_dirs: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
            for member in archive:
                if (member.uid != 0 or member.gid != 0 or member.mtime != 0
                        or member.issym() or member.islnk() or member.isdev()
                        or member.type not in (tarfile.REGTYPE, tarfile.DIRTYPE)):
                    raise SparseSourceDenied("A0_SPARSE_PACKAGE_UNSAFE_METADATA")
                relative = member.name.rstrip("/")
                if member.isdir():
                    if relative not in expected_dirs or member.mode != DIRECTORY_MODE or relative in observed_dirs:
                        raise SparseSourceDenied("A0_SPARSE_PACKAGE_UNDECLARED_DIRECTORY")
                    observed_dirs.add(relative)
                elif member.isfile():
                    _checked_path(relative)
                    if relative not in expected_files or relative in observed_files or member.mode != FILE_MODE:
                        raise SparseSourceDenied("A0_SPARSE_PACKAGE_UNDECLARED_FILE")
                    row = expected_files[relative]
                    stream = archive.extractfile(member)
                    if (stream is None or member.size != row["size"]
                            or sha256(stream.read()).hexdigest() != row["sha256"]):
                        raise SparseSourceDenied("A0_SPARSE_PACKAGE_FILE_TAMPERED")
                    observed_files.add(relative)
            if observed_files != set(expected_files) or observed_dirs != expected_dirs:
                raise SparseSourceDenied("A0_SPARSE_PACKAGE_INCOMPLETE")
    except SparseSourceDenied:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise SparseSourceDenied("A0_SPARSE_PACKAGE_INVALID") from exc


def _private_lab_root(root: Path) -> Path:
    """Never map this test installer to a real /opt or an arbitrary path."""
    import os
    import stat
    if (not root.is_absolute() or Path("/tmp") not in root.parents
            or root.is_symlink() or not root.is_dir()
            or root.resolve(strict=True) != root
            or root.stat().st_uid != os.geteuid()
            or stat.S_IMODE(root.stat().st_mode) != 0o700):
        raise SparseSourceDenied("A0_SPARSE_DISPOSABLE_TEST_ROOT_REQUIRED")
    return root


def _lab_target(root: Path, manifest: Mapping[str, Any]) -> Path:
    path = _private_lab_root(root) / manifest["target"].lstrip("/")
    ancestor = path.parent
    while ancestor != root:
        if ancestor.is_symlink() or root not in ancestor.parents:
            raise SparseSourceDenied("A0_SPARSE_TEST_PARENT_REDIRECTION")
        ancestor = ancestor.parent
    return path


def stage_disposable(root: Path, manifest: Mapping[str, Any],
                     archive: bytes, *, root_metadata: bool = False,
                     stop_after: int | None = None) -> dict[str, Any]:
    """Complete exact sparse source in a private /tmp lab, never production."""
    import os
    import stat
    verify_package(archive, manifest)
    if root_metadata and os.geteuid() != 0:
        raise SparseSourceDenied("A0_SPARSE_ROOT_CI_ONLY")
    root = _private_lab_root(root)
    target = _lab_target(root, manifest)
    if target.exists() or target.is_symlink():
        raise SparseSourceDenied("A0_SPARSE_TEST_TARGET_ALREADY_EXISTS")
    # No extraction through tarfile.extractall: only prevalidated regular files.
    paths = manifest["files"]
    target.mkdir(parents=True, mode=DIRECTORY_MODE)
    target.chmod(DIRECTORY_MODE)
    for name in _directory_names(tuple(x["path"] for x in paths)):
        directory = target / name
        directory.mkdir(mode=DIRECTORY_MODE)
        directory.chmod(DIRECTORY_MODE)
        if root_metadata:
            os.chown(directory, 0, 0)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for row in paths:
            source = tar.extractfile(row["path"])
            if source is None:
                raise SparseSourceDenied("A0_SPARSE_TEST_SOURCE_UNAVAILABLE")
            dest = target / row["path"]
            dest.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
            if dest.parent.is_symlink() or dest.exists() or dest.is_symlink():
                raise SparseSourceDenied("A0_SPARSE_TEST_COLLISION")
            data = source.read()
            if sha256(data).hexdigest() != row["sha256"]:
                raise SparseSourceDenied("A0_SPARSE_TEST_BLOB_CHANGED")
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                with os.fdopen(fd, "wb", closefd=False) as handle:
                    handle.write(data)
                    handle.flush()
                    if root_metadata:
                        os.fchown(fd, 0, 0)
                    os.fchmod(fd, FILE_MODE)
                    os.fsync(fd)
            finally:
                os.close(fd)
            if stop_after is not None:
                stop_after -= 1
                if stop_after == 0:
                    raise InterruptedError("A0_SPARSE_TEST_INTERRUPTED")
    verify_disposable(root, manifest, root_metadata=root_metadata)
    return {"status": "exact_sparse_source_verified", "files": len(paths),
            "source_sha": manifest["candidate_sha"], "production_mutation": False}


def verify_disposable(root: Path, manifest: Mapping[str, Any],
                      *, partial: bool = False,
                      root_metadata: bool = False) -> None:
    import os
    import stat
    validate_manifest(manifest)
    target = _lab_target(root, manifest)
    if not target.exists() or target.is_symlink():
        raise SparseSourceDenied("A0_SPARSE_TEST_RELEASE_ROOT_MISSING")
    if target.parent.is_symlink() or target.parent.parent.is_symlink():
        raise SparseSourceDenied("A0_SPARSE_TEST_PARENT_REDIRECTION")
    wanted_files = {str(row["path"]) for row in manifest["files"]}
    wanted_dirs = set(_directory_names(tuple(wanted_files)))
    found_files: set[str] = set()
    found_dirs: set[str] = set()
    for obj in target.rglob("*"):
        if obj.is_symlink():
            raise SparseSourceDenied("A0_SPARSE_TEST_FOREIGN_LINK")
        relative = obj.relative_to(target).as_posix()
        meta = obj.lstat()
        if obj.is_dir():
            if relative not in wanted_dirs or stat.S_IMODE(meta.st_mode) != DIRECTORY_MODE:
                raise SparseSourceDenied("A0_SPARSE_TEST_FOREIGN_DIRECTORY")
            found_dirs.add(relative)
        elif obj.is_file():
            rows = [x for x in manifest["files"] if x["path"] == relative]
            if (len(rows) != 1 or stat.S_IMODE(meta.st_mode) != FILE_MODE
                    or meta.st_nlink != 1 or sha256(obj.read_bytes()).hexdigest() != rows[0]["sha256"]):
                raise SparseSourceDenied("A0_SPARSE_TEST_FOREIGN_FILE")
            if root_metadata and (meta.st_uid, meta.st_gid) != (0, 0):
                raise SparseSourceDenied("A0_SPARSE_TEST_OWNER_DRIFT")
            found_files.add(relative)
        else:
            raise SparseSourceDenied("A0_SPARSE_TEST_SPECIAL_OBJECT")
    if (not found_dirs.issubset(wanted_dirs) or not found_files.issubset(wanted_files)
            or (not partial and (found_dirs != wanted_dirs or found_files != wanted_files))):
        raise SparseSourceDenied("A0_SPARSE_TEST_INCOMPLETE_OR_EXTRA")


def rollback_disposable(root: Path, manifest: Mapping[str, Any],
                        *, partial: bool = False,
                        root_metadata: bool = False) -> dict[str, Any]:
    validate_manifest(manifest)
    verify_disposable(root, manifest, partial=partial,
                      root_metadata=root_metadata)
    target = _lab_target(root, manifest)
    for row in manifest["files"]:
        path = target / row["path"]
        if path.is_file():
            path.unlink()
    for name in reversed(_directory_names(tuple(x["path"] for x in manifest["files"]))):
        directory = target / name
        if directory.is_dir():
            directory.rmdir()
    target.rmdir()
    base = root / "opt/jason/releases"
    # Remove ONLY the exact previously-created empty scaffold.
    for p in (base, base.parent, base.parent.parent, base.parent.parent.parent):
        if p != root:
            p.rmdir()
    return {"status": "verified_sparse_absence_rollback",
            "rollback_semantics": "only-created-source-objects",
            "production_mutation": False}


def git_object(repo: Path) -> Callable[[str, str], bytes]:
    def get(revision: str, path: str) -> bytes:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={repo}", "-C", str(repo),
             "show", revision + ":" + _checked_path(path)],
            timeout=15,
        )
    return get


def prepare(repo: Path, source_sha: str, *, lkg_sha: str,
            freeze_sha256: str) -> tuple[dict[str, Any], bytes]:
    # The root-loaded validator imports no operator-controlled Python package.
    # Native packet alignment is validated when the *unprivileged* preparer
    # runs and separately by GitHub CI before any publish.
    from tools import pmv4_stage_a_packet as packet
    if required_paths() != tuple(sorted(set(packet.BUNDLE_FILES) |
                                         set(packet.ROOT_STAGE_A_REQUIRED_SOURCES))):
        raise SparseSourceDenied("A0_SPARSE_ALLOWLIST_DRIFT_FROM_NATIVE")
    packet.verify_exact_repository_head(repo, source_sha)
    remote = subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "origin", "refs/heads/main"],
        text=True, timeout=25,
    ).splitlines()
    if remote != [source_sha + "\trefs/heads/main"]:
        raise SparseSourceDenied("A0_SPARSE_NOT_CURRENT_PROTECTED_MAIN")
    read = git_object(repo)
    manifest = source_manifest(source_sha, read, freeze_sha256=freeze_sha256,
                               current_lkg=lkg_sha)
    return manifest, package_bytes(manifest, read)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-sha", required=True)
    p.add_argument("--rollback-lkg", required=True)
    p.add_argument("--freeze-sha256", required=True)
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--target", type=Path, required=True,
                   help="Only a NEW file under /srv/jason/archive, never a root release path")
    args = p.parse_args()
    try:
        target = args.target
        if (target.is_symlink() or target.exists() or not target.is_absolute()
                or target.parent != Path("/srv/jason/archive")
                or not target.name.startswith("pmv4-stage-a0-sparse-")
                or target.suffix != ".tar"):
            raise SparseSourceDenied("A0_SPARSE_UNSAFE_ARTIFACT_TARGET")
        manifest, data = prepare(args.repo, args.source_sha,
                                 lkg_sha=args.rollback_lkg,
                                 freeze_sha256=args.freeze_sha256)
        import os
        descriptor = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        result = {
            "source_sha": args.source_sha,
            "scope_sha256": manifest["scope_sha256"],
            "archive_sha256": sha256(data).hexdigest(),
            "artifact": str(target), "source_count": len(manifest["files"]),
            "production_mutation": False, "root_publish_authorized": False,
            "requires_separate_signed_owner_release": True,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SparseSourceDenied, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("PMV4_A0_SPARSE_SOURCE=DENIED " + str(exc)[:160])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
