#!/usr/bin/env python3
"""Build a NEW, immutable A1 owner release from exact merged protected main.

The previous A1 release, receipt and approval are immutable history.
Generated root/Owner/launcher files derive only from Git-trusted source
templates. No root install, Docker up, provider network or Owner signing.
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
from typing import Callable

from tools.pmv4_shadow_release import ShadowReleaseDenied, read_json
from tools.pmv4_shadow_ci import protected_main_ci_verified
from tools.pmv4_shadow_candidate_packet import ARTIFACT_PARENT

ORIGINAL_SOURCE = "8c2064193d74cc41b52369681febbc0a74fa96f7"
ORIGINAL_APPROVAL = "owner-mcp-319c697027a146beac98818e5305a971"
REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
NEW_ACTION = "pmv4-a1-one-owner-exact-disconnected-shadow-bootstrap-v2"
FILES = (
    "tools/pmv4_a1_atomic_shadow_root.py",
    "tools/pmv4_a1_atomic_one_owner.py",
    "tools/pmv4_a1_one_owner_local.sh",
)
SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class CandidateBuildDenied(PermissionError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise CandidateBuildDenied(reason)


def digest(blob: bytes) -> str:
    return sha256(blob).hexdigest()


def exact_replace(value: str, old: str, new: str) -> str:
    need(value.count(old) == 1, "A1_V2_TEMPLATE_CONTEXT_NOT_EXACT")
    return value.replace(old, new)


def render_root(source: str, sha: str, image: str) -> str:
    need(bool(SHA.fullmatch(sha) and IMAGE.fullmatch(image)),
         "A1_V2_SHA_OR_IMAGE_NOT_EXACT")
    stage = "/run/jason-pmv4-a1-v2-" + sha[:12]
    result = source
    for old, new in (
        ('CANDIDATE="' + ORIGINAL_SOURCE + '"', 'CANDIDATE="' + sha + '"'),
        ('IMAGE="sha256:779bf783c83cdefad82e34ac99335e2a2c017d8aa5588edb0ed2844a885aa9ed"',
         'IMAGE="' + image + '"'),
        ('ACTION="pmv4-a1-one-owner-exact-shadow-bootstrap-and-activate-v1"',
         'ACTION="' + NEW_ACTION + '"'),
        ('AUDIT=ROOT/"control"/"a1-exact-atomic-bootstrap.jsonl"',
         'AUDIT=ROOT/"control"/("a1-exact-atomic-bootstrap-v2-"+CANDIDATE[:12]+".jsonl")'),
        ('TRUSTED_SCRIPT=Path("/run/jason-pmv4-a1-oneowner-8c20/installer.py")',
         'TRUSTED_SCRIPT=Path("' + stage + '/installer.py")'),
    ):
        result = exact_replace(result, old, new)

    # Exactly one fully rolled-back, historical original approval is allowed.
    # The native controller still independently rejects pending receipts.
    result = exact_replace(
        result,
        '    need(not receipts,"A1_REVIEW_EXISTING_RELEASE_RECEIPTS")',
        '''    need(len(receipts)==1
         and receipts[0].name=="owner-''' + ORIGINAL_APPROVAL + '''.json"
         and receipts[0].is_file() and not receipts[0].is_symlink(),
         "A1_V2_ORIGINAL_ROLLED_BACK_RECEIPT_REQUIRED")
    historical=shadow.read_json(receipts[0])
    need(historical.get("state")=="rolled_back"
         and historical.get("approval_id")=="''' + ORIGINAL_APPROVAL + '''"
         and historical.get("candidate_sha")=="''' + ORIGINAL_SOURCE + '''"
         and historical.get("rollback_sha")==ROLLBACK,
         "A1_V2_ORIGINAL_OWNER_RECEIPT_NOT_RECONCILED")'''
    )
    # Verified-bytes in-memory import avoids executing mutable worktree files:
    # prior to the Owner request source_git_attestation binds each blob to
    # protected main. Root never accepts an arbitrary module path or hash.
    anchor = "def protected_source_and_health()->guard_lib.IndependentHostGuard:\n"
    loader = '''def verified_reviewed_module(relative:str, name:str):
    import types
    need(relative in ("tools/pmv4_host_release_guard.py",
                      "tools/pmv4_shadow_docker_adapter.py"),
         "A1_V2_RUNTIME_MODULE_NOT_ALLOWLISTED")
    plan,manifest,scope=plan_and_source()
    body=(ARCHIVE/"release"/"bundle"/relative).read_bytes()
    need(0<len(body)<1_000_000
         and sha(body)==plan["source_files"][relative],
         "A1_V2_REVIEWED_RUNTIME_MODULE_HASH_CHANGED")
    module=types.ModuleType("tools.pmv4_a1_v2_"+name)
    module.__package__="tools"
    exec(compile(body,"protected-main:"+CANDIDATE+":"+relative,"exec"),
         module.__dict__)
    return module


'''
    result = exact_replace(result, anchor, loader+anchor)
    result = exact_replace(
        result, "    host=guard_lib.IndependentHostGuard()\n",
        '    host=verified_reviewed_module("tools/pmv4_host_release_guard.py","guard").IndependentHostGuard()\n')
    result = exact_replace(
        result, "    adapter=docker_shadow.DockerShadowAdapter(\n        root=ROOT,core_continuity_probe=host.preexisting_core_health,",
        '    adapter=verified_reviewed_module("tools/pmv4_shadow_docker_adapter.py","adapter").DockerShadowAdapter(\n        root=ROOT,core_continuity_probe=host.preexisting_core_health,')
    # Source-git identity must precede executing any source-derived root module.
    result = exact_replace(
        result,
        "    plan,manifest,scope=plan_and_source()\n    empty_baseline()\n    host=protected_source_and_health()",
        "    plan,manifest,scope=plan_and_source()\n    source_git_attestation(plan)\n    empty_baseline()\n    host=protected_source_and_health()")
    return result


def render_owner(source: str, source_sha: str) -> str:
    archive=ARTIFACT_PARENT / ("pmv4-a1-"+source_sha)
    result = exact_replace(
        source,
        "from tools import pmv4_a1_atomic_shadow_root as root",
        '''ROOT_GENERATED=Path(__file__).with_name("pmv4_a1_atomic_shadow_root.py")
_spec=importlib.util.spec_from_file_location("tools.pmv4_a1_v2_verified_root",ROOT_GENERATED)
if _spec is None or _spec.loader is None:
    raise RuntimeError("A1_V2_REVIEWED_ROOT_IMPORT_UNAVAILABLE")
root=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(root)''')
    result = exact_replace(
        result,
        'WORKTREE=Path("/srv/jason/archive/engineering-worktrees/pmv4-a1-shadow-package-20261116")',
        'WORKTREE=Path("'+str(archive)+'")')
    return result


def render_local(source:str, source_sha:str, root_hash:str,
                 owner_hash:str)->str:
    archive=str(ARTIFACT_PARENT / ("pmv4-a1-"+source_sha))
    stage="/run/jason-pmv4-a1-v2-"+source_sha[:12]
    tree="/srv/jason/archive/engineering-worktrees/pmv4-a1-v2-main-"+source_sha[:12]
    result=source
    for old,new in (
        ('TREE="/srv/jason/archive/engineering-worktrees/pmv4-a1-shadow-package-20261116"',
         'TREE="'+archive+'"\nSOURCE_TREE="'+tree+'"'),
        ('ARTIFACT="/srv/jason/archive/engineering-artifacts/pmv4-a1-'+ORIGINAL_SOURCE+'"',
         'ARTIFACT="'+archive+'"'),
        ('STAGE="/run/jason-pmv4-a1-oneowner-8c20"',
         'STAGE="'+stage+'"'),
        ('ROOT_SHA="ea259a6a281d3a04d16e7fe4a8fe7b90a00b78e02fe0c9dbecdadd5ccc1c9e1b"',
         'ROOT_SHA="'+root_hash+'"'),
        ('OWNER_SHA="9eb50beaf292a8114f8f74e1ece055058d8d58bf4253a4faaa3c09ecda7239a8"',
         'OWNER_SHA="'+owner_hash+'"'),
        ('SOURCE="'+ORIGINAL_SOURCE+'"', 'SOURCE="'+source_sha+'"'),
        ('cd "$TREE"\nPYTHONPATH=implementation:. ',
         '[[ "$(git -C "$SOURCE_TREE" rev-parse HEAD)" == "$SOURCE" ]] || { echo "A1_V2_SOURCE_CHECKOUT_CHANGED" >&2; exit 2; }\n[[ -z "$(git -C "$SOURCE_TREE" status --porcelain)" ]] || { echo "A1_V2_SOURCE_CHECKOUT_DIRTY" >&2; exit 2; }\ncd "$SOURCE_TREE"\nPYTHONPATH=implementation:. '),
    ):
        result=exact_replace(result,old,new)
    return result


def read_git(repo:Path,source_sha:str,relative:str)->str:
    need(relative in FILES, "A1_V2_NOT_ALLOWLISTED_SOURCE_FILE")
    run=subprocess.run(
        ["/usr/bin/git","-C",str(repo),"show",source_sha+":"+relative],
        capture_output=True,check=False,timeout=30)
    need(run.returncode==0 and 0<len(run.stdout)<1_000_000,
         "A1_V2_REVIEWED_GIT_SOURCE_UNAVAILABLE")
    return run.stdout.decode("utf-8")


def write_exclusive(path:Path,content:str)->None:
    need(not path.exists() and not path.is_symlink(),
         "A1_V2_GENERATED_FILE_ALREADY_EXISTS")
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as file:
        file.write(content.encode("utf-8"))
        file.flush()
        os.fsync(file.fileno())


def prepare(source_sha:str,image_digest:str,*,repo:Path=REPO,
            verify_main:Callable[[str],bool]=protected_main_ci_verified)->dict:
    need(bool(SHA.fullmatch(source_sha) and IMAGE.fullmatch(image_digest)),
         "A1_V2_INVALID_SOURCE_OR_IMAGE")
    need(verify_main(source_sha) is True,
         "A1_V2_PROTECTED_MAIN_CHECKS_NOT_PASS")
    archive=ARTIFACT_PARENT/("pmv4-a1-"+source_sha)
    need(archive.is_dir() and not archive.is_symlink(),
         "A1_V2_SOURCE_PACKET_NOT_PREPARED")
    evidence=read_json(archive/"evidence.json")
    manifest=read_json(archive/"release"/"release-manifest.json")
    need(evidence.get("status")=="preproduction_candidate_not_authorized"
         and evidence.get("source_sha")==source_sha
         and evidence.get("image_digest")==image_digest
         and manifest.get("candidate_sha")==source_sha
         and manifest.get("image_digest")==image_digest,
         "A1_V2_PINNED_SOURCE_PACKET_DIFFERENT")
    need(not (archive/"root-oneowner-proof.json").exists(),
         "A1_V2_OWNER_PROOF_MUST_NOT_PREEXIST")
    folder=archive/"tools"
    need(not folder.exists() and not folder.is_symlink(),
         "A1_V2_ALREADY_GENERATED_OR_UNTRUSTED")
    root=render_root(read_git(repo,source_sha,FILES[0]),source_sha,image_digest)
    owner=render_owner(read_git(repo,source_sha,FILES[1]),source_sha)
    rh=digest(root.encode())
    oh=digest(owner.encode())
    local=render_local(read_git(repo,source_sha,FILES[2]),source_sha,rh,oh)
    for body in (root,owner):
        compile(body,"reviewed-A1-v2-generated","exec")
    folder.mkdir(mode=0o700)
    try:
        write_exclusive(folder/"pmv4_a1_atomic_shadow_root.py",root)
        write_exclusive(folder/"pmv4_a1_atomic_one_owner.py",owner)
        write_exclusive(folder/"pmv4_a1_one_owner_local.sh",local)
        receipt={
            "status":"new_source_exact_immutable_a1_v2_candidate",
            "source_sha":source_sha,"image_digest":image_digest,
            "action":NEW_ACTION,"previous_owner_approval_reused":False,
            "previous_failed_source_sha":ORIGINAL_SOURCE,
            "previous_approval_id":ORIGINAL_APPROVAL,
            "root_executor_sha256":rh,
            "owner_issuer_sha256":oh,
            "local_launcher_sha256":digest(local.encode()),
            "source_approval_issued":False,
            "production_mutations":False,"gateway_started":False,
        }
        write_exclusive(archive/"new-release-build-evidence.json",
                        json.dumps(receipt,sort_keys=True,
                                   separators=(",",":")))
        return receipt
    except BaseException:
        # Newly created artifacts only; no previous immutable packet touched.
        for f in folder.iterdir():
            f.unlink()
        folder.rmdir()
        raise


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--image-digest",required=True)
    args=parser.parse_args()
    report=prepare(args.source_sha,args.image_digest)
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
