#!/usr/bin/env python3
"""Nonprivileged immutable source-only staging for catalog promotion root files.

Never installs, activates, retags, deploys, unfreezes or changes root policy.
The separately approved root installer must independently reverify every
signed/source-bound digest and verify release-control compatibility.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

FILES = (
    "tools/catalog_scoped_promotion.py",
    "tools/catalog_scoped_promotion_host.py",
    "tools/catalog_scoped_promotion_root.py",
    "tools/catalog_scoped_release_admission.py",
    "tools/catalog_scoped_control_readback.py",
    "tools/catalog_scoped_promotion_recovery.py",
    "tools/catalog_scoped_protected_ci.py",
    "tools/release_manager_host_runner.py",
    "tools/release_host_reconcile_worker.py",
    "implementation/kernel/catalog_scoped_promotion_contract.py",
    "implementation/kernel/signed_owner_release.py",
    "docs/engineering/evidence/catalog-scope-admission-20261117.json",
    "docs/engineering/evidence/catalog-scope-original-manifest-20261117.json",
    "config/catalog-scoped-release-admission.json",
    "infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.service",
    "infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.timer",
)
SHA = re.compile(r"^[a-f0-9]{40}$")
BLOCKED_ROOTS = (
    Path("/opt/jason"),Path("/var/lib/jason"),Path("/etc/jason"),
    Path("/etc/jason-owner-release"),Path("/usr/local/lib/jason"),
    Path("/run"),
)


class CatalogBundleDenied(PermissionError):pass


def fail(reason:str)->None:
    raise CatalogBundleDenied("CATALOG_BUNDLE_"+reason)


def git(repo:Path,*argv:str)->bytes:
    done=subprocess.run(["git","-c",f"safe.directory={repo}","-C",str(repo),*argv],
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=30)
    if done.returncode:fail("SOURCE_COMMIT_OR_BLOB_UNAVAILABLE")
    return done.stdout


def safe_destination(path:Path,*,cwd:Path|None=None)->Path:
    # Check literal normalized path BEFORE any stat/symlink operation: the
    # source-only builder must not even inspect private production roots.
    lexical=Path(os.path.abspath(str(path.expanduser())))
    for root in BLOCKED_ROOTS:
        if lexical==root or root in lexical.parents:fail("PRODUCTION_PATH_DENIED")
    if path.is_symlink():fail("OUTPUT_SYMLINK_DENIED")
    resolved=path.resolve(strict=False)
    for root in BLOCKED_ROOTS:
        if resolved==root or root in resolved.parents:fail("PRODUCTION_PATH_DENIED")
    if resolved.exists():fail("OUTPUT_ALREADY_EXISTS")
    if not resolved.parent.is_dir() or resolved.parent.is_symlink():
        fail("STAGING_PARENT_MISSING_OR_SYMLINK")
    if resolved.parent.stat().st_uid!=os.getuid():
        fail("STAGING_PARENT_NOT_CURRENT_OPERATOR")
    return resolved


def bundle_exact_source(repo:Path,source_sha:str,staging:Path,*,
                        require_protected_main:bool=True)->dict[str,Any]:
    """Copy *only* Git-committed immutable blobs to an unprivileged directory."""
    if not isinstance(source_sha,str) or SHA.fullmatch(source_sha) is None:
        fail("EXACT_SOURCE_SHA_REQUIRED")
    if require_protected_main:
        try:
            remote=git(repo,"ls-remote","origin","refs/heads/main").decode().strip().split()
        except CatalogBundleDenied as exc:
            raise CatalogBundleDenied("CATALOG_BUNDLE_SOURCE_NOT_CURRENT_PROTECTED_MAIN") from exc
        if remote!=[source_sha,"refs/heads/main"]:
            fail("SOURCE_NOT_CURRENT_PROTECTED_MAIN")
    destination=safe_destination(staging)
    planned={rel:git(repo,"show",f"{source_sha}:{rel}") for rel in FILES}
    if any(not blob or len(blob)>500_000 for blob in planned.values()):
        fail("EMPTY_OR_OVERSIZED_SOURCE_BLOB")
    destination.mkdir(mode=0o700)
    manifest={"schema_version":"1.0","status":"source_only_not_installed",
              "source_sha":source_sha,"files":{},
              "release_approval_recorded":False,"production_mutations":False,
              "root_installation_authorized":False}
    for relative,blob in sorted(planned.items()):
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_symlink() or target.exists():fail("STAGING_FILE_CONFLICT")
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o644)
        try:
            with os.fdopen(fd,"wb",closefd=False) as stream:
                stream.write(blob);stream.flush();os.fsync(stream.fileno())
        finally:os.close(fd)
        manifest["files"][relative]={"sha256":sha256(blob).hexdigest(),"bytes":len(blob)}
    manifest["bundle_sha256"]=sha256(json.dumps(manifest,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    output=destination/"SOURCE_ONLY_MANIFEST.json"
    output.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    output.chmod(0o600)
    return manifest


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",type=Path,required=True)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    evidence=bundle_exact_source(args.repo.expanduser().resolve(),args.source_sha,
                                 args.output.expanduser())
    print(json.dumps({"status":evidence["status"],"source_sha":evidence["source_sha"],
                      "bundle_sha256":evidence["bundle_sha256"],
                      "file_count":len(evidence["files"]),
                      "root_installation_authorized":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
