#!/usr/bin/env python3
"""Preproduction-only PMv4 A1 immutable shadow release candidate builder.

Read the exact protected Git revision. Never sign, install, start Docker,
stage a root-owned target or consume existing approvals. The root release
authority must independently validate every file and current health.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping

from implementation.kernel.signed_owner_release import canonical
from tools.pmv4_shadow_release import (
    EMPTY_BASELINE, PROTECTED_CORE, REPO, ShadowReleaseDenied,
    bundle_digest, digest_file, manifest_check,
)
from tools.pmv4_shadow_ci import protected_main_ci_verified

SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXACT_SOURCE_FILES = (
    "config/openclaw-specialists/manifest.json",
    "config/pmv4-shadow/docker-compose.yml",
    "tools/pmv4_shadow_ci.py",
    "tools/pmv4_shadow_docker_adapter.py",
    "tools/pmv4_shadow_host_runtime.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_owner_issuer.py",
    "tools/pmv4_shadow_release.py",
)
ARTIFACT_PARENT = Path("/srv/jason/archive/engineering-artifacts")


def git_file(repo: Path, revision: str, name: str) -> bytes:
    if not SHA.fullmatch(revision) or name not in EXACT_SOURCE_FILES:
        raise ShadowReleaseDenied("A1_SOURCE_BLOB_NOT_ALLOWLISTED")
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "show", revision + ":" + name],
        shell=False, capture_output=True, timeout=20, check=False,
    )
    if result.returncode or not result.stdout or len(result.stdout) > 1_000_000:
        raise ShadowReleaseDenied("A1_SOURCE_BLOB_UNAVAILABLE")
    return result.stdout


def prepare(
    *,
    source_sha: str,
    image_digest: str,
    read_source: Callable[[str, str], bytes],
    target: Path,
    current_main_ok: Callable[[str], bool],
) -> dict:
    """Build a *source-only*, non-root candidate packet in an empty directory."""
    if not SHA.fullmatch(source_sha) or not IMAGE.fullmatch(image_digest):
        raise ShadowReleaseDenied("A1_SOURCE_OR_IMAGE_DIGEST_INVALID")
    if current_main_ok(source_sha) is not True:
        raise ShadowReleaseDenied("A1_PROTECTED_MAIN_CI_UNVERIFIED")
    target = Path(target)
    if (not target.is_absolute()
        or target.parent != ARTIFACT_PARENT
        or not target.name.startswith("pmv4-a1-")
        or target.name != "pmv4-a1-" + source_sha
        or target.exists() or target.is_symlink()):
        raise ShadowReleaseDenied("A1_UNTRUSTED_PREPRODUCTION_TARGET")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.parent.is_symlink() or target.parent.stat().st_mode & 0o022:
        raise ShadowReleaseDenied("A1_UNTRUSTED_PREPRODUCTION_PARENT")

    # All paths here are known repo-relative names, never supplied by an
    # untrusted release request. Source blobs must come from the exact Git SHA.
    target.mkdir(mode=0o700)
    try:
        root = target / "release"
        bundle = root / "bundle"
        bundle.mkdir(parents=True, mode=0o700)
        hashes = {}
        for name in EXACT_SOURCE_FILES:
            data = read_source(source_sha, name)
            if not isinstance(data, bytes) or not data or len(data) > 1_000_000:
                raise ShadowReleaseDenied("A1_SOURCE_BLOB_UNVERIFIED")
            dest = bundle / name
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            dest.write_bytes(data)
            dest.chmod(0o400)
            hashes[name] = sha256(data).hexdigest()
        bundle_sha = bundle_digest(bundle)
        scope = {
            "schema_version": "1.0", "service": "jason-pmv4-shadow",
            "candidate_sha": source_sha,
            "rollback_sha": EMPTY_BASELINE,
            "bundle_sha256": bundle_sha,
            "files": list(EXACT_SOURCE_FILES),
            "protected_core": [PROTECTED_CORE],
            "provider_writes": False,
        }
        manifest = {
            "schema_version": "1.0", "service": "jason-pmv4-shadow",
            "release_mode": "owner-signed-isolated-shadow",
            "repository": REPO, "candidate_sha": source_sha,
            "rollback_sha": EMPTY_BASELINE,
            "scope_sha256": sha256(canonical(scope)).hexdigest(),
            "bundle_sha256": bundle_sha,
            "compose_sha256": hashes["config/pmv4-shadow/docker-compose.yml"],
            "image_digest": image_digest,
            "read_only": True, "provider_writes": False,
            "teams_approval_required": False,
            "production_core_changes": [],
            "network_profile": "disconnected",
            "activation": "shadow-only",
        }
        manifest_check(manifest)
        manifest_path = root / "release-manifest.json"
        manifest_path.write_bytes(canonical(manifest))
        manifest_path.chmod(0o400)
        scope_path = target / "reviewed-scope.json"
        scope_path.write_bytes(canonical(scope))
        scope_path.chmod(0o400)
        packet = {
            "schema_version": "1.0",
            "status": "preproduction_candidate_not_authorized",
            "source_sha": source_sha,
            "image_digest": image_digest,
            "release_id": "release-" + source_sha[:16],
            "scope_sha256": manifest["scope_sha256"],
            "manifest_sha256": sha256(canonical(manifest)).hexdigest(),
            "bundle_sha256": bundle_sha,
            "source_files": hashes,
            "single_owner_exact_approval_required": True,
            "production_mutations": False,
            "shadow_activation_performed": False,
            "rollback_sha": EMPTY_BASELINE,
        }
        out = target / "evidence.json"
        out.write_bytes(canonical(packet))
        out.chmod(0o400)
        # Verify every emitted byte and hashes rather than trusting the plan.
        if bundle_digest(bundle) != bundle_sha:
            raise ShadowReleaseDenied("A1_BUNDLE_CHANGED_DURING_STAGING")
        if digest_file(manifest_path) != sha256(canonical(manifest)).hexdigest():
            raise ShadowReleaseDenied("A1_MANIFEST_CHANGED_DURING_STAGING")
        return packet
    except BaseException:
        # Only the newly created exact preproduction target is removable.
        import shutil
        shutil.rmtree(target)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--repo", default="/home/al/.local/lib/jason/engineering-source-repo")
    args = parser.parse_args()
    packet = prepare(
        source_sha=args.source_sha, image_digest=args.image_digest,
        read_source=lambda sha, name: git_file(Path(args.repo), sha, name),
        target=ARTIFACT_PARENT / ("pmv4-a1-" + args.source_sha),
        current_main_ok=protected_main_ci_verified,
    )
    print(json.dumps(packet, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
