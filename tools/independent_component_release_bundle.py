#!/usr/bin/env python3
"""Prepare and verify a self-contained, source-pinned independent release-code bundle.

SOURCE-ONLY: this utility cannot install, activate, or replace production
software. A separately authorized root installer must independently verify the
bundle, current protected CI, Owner signature, release locks and frozen state.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

SHA = re.compile(r"^[0-9a-f]{40}$")
FILES = (
    "tools/independent_component_release.py",
    "tools/independent_component_host_adapter.py",
    "tools/independent_component_release_root.py",
    "tools/pmv4_host_release_guard.py",
    "implementation/kernel/signed_owner_release.py",
    "implementation/kernel/__init__.py",
)
RESTRICTED_ROOTS = (
    Path("/opt/jason"), Path("/var/lib/jason"), Path("/etc/jason"),
    Path("/etc/jason-owner-release"), Path("/run"), Path("/srv/jason"),
)


class ComponentBundleDenied(PermissionError):
    pass


def _git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False, capture_output=True, timeout=30,
    )
    if p.returncode != 0:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_GIT_OBJECT_UNAVAILABLE")
    return p.stdout


def _sha(ref: str) -> str:
    if not isinstance(ref, str) or not SHA.fullmatch(ref):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_EXACT_SHA_REQUIRED")
    return ref


def _destination(path: Path, *, existing: bool) -> Path:
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_DESTINATION_UNSAFE")
    # Never even inspect a protected production path. It can be inaccessible
    # to the unprivileged builder, and must be rejected based on its pathname.
    if p == Path("/") or any(p == x or x in p.parents for x in RESTRICTED_ROOTS):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_PRODUCTION_DESTINATION_DENIED")
    try:
        canonical = p.resolve(strict=False)
        if p.is_symlink() or canonical != p:
            raise ComponentBundleDenied("COMPONENT_BUNDLE_DESTINATION_SYMLINK")
    except OSError as exc:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_DESTINATION_UNAVAILABLE") from exc
    if existing and (not p.is_dir() or p.is_symlink()):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_UNAVAILABLE")
    if not existing and (p.exists() or p.is_symlink()):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_REPLACE_DENIED")
    return p


def _git_file(repo: Path, sha: str, path: str) -> bytes:
    result = _git(repo, "ls-tree", sha, "--", path)
    line = result.decode("utf-8", errors="strict").strip()
    if not line.startswith("100644 blob ") or not line.endswith("\t" + path):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_NOT_PLAIN_SOURCE_BLOB")
    content = _git(repo, "show", sha + ":" + path)
    if (not content and not path.endswith("/__init__.py")) or len(content) > 256 * 1024:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_SOURCE_SIZE_INVALID")
    if path.endswith(".py"):
        compile(content, path, "exec")
    return content


def _manifest(sha: str, files: Mapping[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_kind": "source_only_independent_component_release_code",
        "repository": "al-teamaot-com/jason",
        "source_sha": sha,
        "files_sha256": dict(sorted(files.items())),
        "separate_production_approval_required": True,
        "production_installation_performed": False,
        "production_authority": False,
    }


def _bytes(doc: Mapping[str, Any]) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def prepare(repo: Path, sha: str, destination: Path) -> dict[str, Any]:
    """Create private, immutable-by-content staging from exact reviewed Git blobs."""
    sha = _sha(sha)
    target = _destination(destination, existing=False)
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink():
        raise ComponentBundleDenied("COMPONENT_BUNDLE_SOURCE_REPOSITORY_INVALID")
    if _git(repo, "cat-file", "-t", sha).strip() != b"commit":
        raise ComponentBundleDenied("COMPONENT_BUNDLE_NOT_A_COMMIT")
    # Read all Git objects before creating any output. Prevent partial source
    # staging when a required file is absent, is a symlink, or does not compile.
    data = {path: _git_file(repo, sha, path) for path in FILES}
    manifest = _manifest(sha, {k: sha256(v).hexdigest() for k, v in data.items()})
    target.mkdir(mode=0o700, parents=False)
    try:
        for rel, blob in data.items():
            dest = target / rel
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, "wb") as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
        doc = target / "source-bundle.json"
        fd = os.open(doc, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, "wb") as f:
            f.write(_bytes(manifest))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # Never remove artifacts on failure; leave staging for bounded audit.
        raise
    verify(repo, sha, target)
    return {"status": "source_bundle_verified", "source_sha": sha,
            "bundle_manifest_sha256": sha256(_bytes(manifest)).hexdigest(),
            "file_count": len(FILES), "production_installed": False}


def verify(repo: Path, sha: str, destination: Path) -> dict[str, Any]:
    sha = _sha(sha)
    target = _destination(destination, existing=True)
    try:
        doc = target / "source-bundle.json"
        if not doc.is_file() or doc.is_symlink() or doc.stat().st_size > 8192:
            raise ComponentBundleDenied("COMPONENT_BUNDLE_MANIFEST_UNTRUSTED")
        manifest = json.loads(doc.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_MANIFEST_INVALID") from exc
    if manifest != _manifest(sha, {
        rel: sha256(_git_file(Path(repo), sha, rel)).hexdigest()
        for rel in FILES
    }):
        raise ComponentBundleDenied("COMPONENT_BUNDLE_MANIFEST_DRIFT")
    expected = set(FILES) | {"source-bundle.json"}
    actual: set[str] = set()
    for path in target.rglob("*"):
        if path.is_symlink():
            raise ComponentBundleDenied("COMPONENT_BUNDLE_SYMLINK_DENIED")
        if path.is_file():
            actual.add(path.relative_to(target).as_posix())
            if path.stat().st_mode & 0o222:
                raise ComponentBundleDenied("COMPONENT_BUNDLE_FILE_WRITABLE")
        elif not path.is_dir():
            raise ComponentBundleDenied("COMPONENT_BUNDLE_NONREGULAR_DENIED")
    if actual != expected:
        raise ComponentBundleDenied("COMPONENT_BUNDLE_FILE_SET_DRIFT")
    for rel in FILES:
        blob = (target / rel).read_bytes()
        if blob != _git_file(Path(repo), sha, rel):
            raise ComponentBundleDenied("COMPONENT_BUNDLE_SOURCE_BYTES_DRIFT")
    return {"status": "source_bundle_verified", "source_sha": sha,
            "file_count": len(FILES), "production_installed": False}


def main() -> int:
    p = argparse.ArgumentParser(description="Source-only independent-component bundle")
    p.add_argument("command", choices=("prepare", "verify"))
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--destination", type=Path, required=True)
    args = p.parse_args()
    try:
        result = (
            prepare(args.repo, args.source_sha, args.destination)
            if args.command == "prepare" else
            verify(args.repo, args.source_sha, args.destination)
        )
    except (ComponentBundleDenied, OSError, ValueError, SyntaxError) as exc:
        p.exit(2, "DENIED: " + str(exc) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
