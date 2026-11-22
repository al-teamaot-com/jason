#!/usr/bin/env python3
"""Build immutable SOURCE-ONLY canary release; never deploy or issue Owner proof."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from tools import pmv4_e_canary_contract as contract
from tools import independent_component_release as core
from tools.pmv4_shadow_ci import protected_main_ci_verified

REPOSITORY=Path("/home/al/.local/lib/jason/engineering-source-repo")
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
REVIEWED_FILES=(
    "infrastructure/pmv4-e-canary/compose.yaml",
    "infrastructure/pmv4-e-canary/config.json",
    "tools/pmv4_e_canary_contract.py",
)
SOURCE_SHA=re.compile(r"^[a-f0-9]{40}$")
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"


class CanaryPacketDenied(PermissionError):
    pass


def require(ok:bool,reason:str)->None:
    if not ok:raise CanaryPacketDenied("PMV4_E_CANARY_"+reason)


def source_at(repo:Path,sha:str,rel:str)->bytes:
    require(rel in REVIEWED_FILES and SOURCE_SHA.fullmatch(sha) is not None,
            "SOURCE_FILE_UNREVIEWED")
    result=subprocess.run(
        ["/usr/bin/git","-C",str(repo),"show",sha+":"+rel],
        capture_output=True,timeout=20,check=False)
    require(result.returncode==0 and 0<len(result.stdout)<1_000_000,
            "SOURCE_NOT_AT_PROTECTED_MAIN")
    return result.stdout


def source_is_protected_main(repo:Path,sha:str)->bool:
    try:
        remote=subprocess.check_output(
            ["/usr/bin/git","-C",str(repo),"rev-parse","origin/main"],
            text=True,timeout=10).strip()
        return remote==sha
    except (OSError,ValueError,subprocess.CalledProcessError):
        return False


def inspect_reviewed_image()->dict[str,Any]:
    image=subprocess.run(
        ["/usr/bin/docker","image","inspect",contract.IMAGE],
        capture_output=True,text=True,timeout=15,check=False)
    require(image.returncode==0,"PINNED_IMAGE_UNAVAILABLE")
    try:
        item=json.loads(image.stdout)
        require(isinstance(item,list) and len(item)==1,
                "IMAGE_ATTESTATION_COUNT_INVALID")
        contract.validate_exact_image(item[0])
        return {
            "image_sha256":contract.IMAGE,
            "image_source_sha":contract.IMAGE_SOURCE,
            "component_label":"pmv4-shadow",
            "provider_mutations_disabled":True,
            "production_core_excluded":True,
        }
    except (ValueError,TypeError,IndexError) as exc:
        raise CanaryPacketDenied("PMV4_E_CANARY_IMAGE_ATTESTATION_INVALID") from exc


def exclusive(path:Path,data:bytes)->None:
    require(not path.exists() and not path.is_symlink()
            and 0<len(data)<1_000_000,
            "DESTINATION_NOT_EMPTY_OR_INVALID")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as handle:
        handle.write(data);handle.flush();os.fsync(handle.fileno())
    path.chmod(0o400)
    require(sha256(path.read_bytes()).digest()==sha256(data).digest(),
            "READBACK_DIFFERENT")


def prepare(
    *,sha:str,repo:Path=REPOSITORY,dest:Path|None=None,
    protected_main:Callable[[Path,str],bool]=source_is_protected_main,
    verified_ci:Callable[[str],bool]=protected_main_ci_verified,
    verified_image:Callable[[],dict[str,Any]]=inspect_reviewed_image,
)->dict[str,Any]:
    require(isinstance(sha,str) and SOURCE_SHA.fullmatch(sha) is not None,
            "SOURCE_SHA_INVALID")
    require(protected_main(repo,sha),"PROTECTED_MAIN_REQUIRED")
    require(verified_ci(sha) is True,
            "PROTECTED_REQUIRED_CI_NOT_GREEN")
    dest=dest or ARTIFACTS/("pmv4-e-canary-"+sha)
    safe=dest.resolve(strict=False)
    require(safe.parent==ARTIFACTS
            or str(safe).startswith("/tmp/"),
            "DESTINATION_ROOT_FORBIDDEN")
    require(not dest.exists() and not dest.is_symlink(),
            "EXACT_SOURCE_ALREADY_STAGED")
    source={rel:source_at(repo,sha,rel) for rel in REVIEWED_FILES}
    # Must not use the unreviewed worktree or a different source commit.
    image=verified_image()
    require(image.get("image_sha256")==contract.IMAGE
            and image.get("image_source_sha")==contract.IMAGE_SOURCE
            and image.get("provider_mutations_disabled") is True
            and image.get("production_core_excluded") is True,
            "IMAGE_SOURCE_BOUNDARY_NOT_EXACT")
    manifest=contract.manifest(
        compose=source[REVIEWED_FILES[0]],
        config=source[REVIEWED_FILES[1]],
        freeze_sha256=FREEZE_SHA,candidate_sha=sha)
    core.validate_manifest(manifest)
    core.validate_compose(source[REVIEWED_FILES[0]],manifest)
    scope={key:manifest[key] for key in core.SCOPE_FIELDS}
    core.validate_scope(manifest,scope)
    report={
        "status":"preproduction_not_authorized",
        "action":"pmv4-e-providerfree-canary-existing-generic-controller-v1",
        "candidate_sha":sha,"rollback_sha":core.ZERO,
        "image_digest":contract.IMAGE,
        "image_source_revision":contract.IMAGE_SOURCE,
        "manifest_sha256":sha256(core.canonical(manifest)).hexdigest(),
        "scope_sha256":manifest["scope_sha256"],
        "source_sha256":{rel:sha256(data).hexdigest()
                         for rel,data in source.items()},
        "root_installed":False,
        "owner_proof_issued":False,
        "production_mutations":False,
        "provider_calls":0,
        "financial_controller_modified":False,
    }
    dest.mkdir(mode=0o700)
    try:
        for rel,data in (
            ("manifest.json",core.canonical(manifest)),
            ("scope.json",core.canonical(scope)),
            ("compose.yaml",source[REVIEWED_FILES[0]]),
            ("config.json",source[REVIEWED_FILES[1]]),
            ("source-evidence.json",core.canonical(report)),
        ):
            exclusive(dest/rel,data)
        require({p.name for p in dest.iterdir()}=={
            "manifest.json","scope.json","compose.yaml",
            "config.json","source-evidence.json"},
            "PACKET_FILE_SET_CHANGED")
        return report
    except BaseException:
        for child in dest.iterdir():child.unlink()
        dest.rmdir()
        raise
