#!/usr/bin/env python3
"""Prepare immutable unprivileged root/Owner v5 Stage E canary packet.

No production writes, deployment, consent, root code installation,
sudo execution, breaker override or service restart.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable

from tools import pmv4_e_canary_oneowner_root as root

SOURCES=(
    "tools/pmv4_e_canary_oneowner_root.py",
    "tools/pmv4_e_canary_oneowner_owner.py",
    "tools/pmv4_e_canary_oneowner_local.sh",
    "tools/pmv4_e_canary_drift_policy.py",
    "tools/pmv4_e_root_receipt_readback.py",
    *root.TRUST_NEW,
)


class StageDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:
        raise StageDenied("PMV4_E_ONEOWNER_PACKET_"+reason)


def git_blob(repo:Path,sha:str,relative:str)->bytes:
    need(relative in SOURCES
         and len(sha)==40 and all(c in "0123456789abcdef" for c in sha),
         "NOT_REVIEWED_SOURCE")
    got=subprocess.run(
        ["/usr/bin/git","-C",str(repo),"show",sha+":"+relative],
        capture_output=True,timeout=25)
    need(got.returncode==0 and 0<len(got.stdout)<200_000,
         "PROTECTED_GIT_BLOB_UNAVAILABLE")
    return got.stdout


def source_main(repo:Path,sha:str)->bool:
    try:
        current=subprocess.check_output(
            ["/usr/bin/git","-C",str(repo),"rev-parse","origin/main"],
            text=True,timeout=10).strip()
        return sha==current
    except (subprocess.CalledProcessError,OSError,ValueError):
        return False


def ci_readback(sha:str)->bool:
    try:
        root.verify_ci(sha)
        return True
    except (root.Denied,subprocess.TimeoutExpired,
            OSError,ValueError):
        return False


def canary_source_readback()->bool:
    try:
        m,scope,data=root.candidate_packet()
        return m["candidate_sha"]==root.CANDIDATE
    except (root.Denied,OSError,ValueError):
        return False


def create_file(path:Path,data:bytes)->None:
    need(not path.exists() and not path.is_symlink()
         and 0<len(data)<200_000,
         "SOURCE_FILE_PREEXISTS_OR_INVALID")
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    need(path.read_bytes()==data and path.lstat().st_uid==os.geteuid(),
         "PACKET_READBACK_NOT_EXACT")


def prepare(
    sha:str,*,repo:Path=root.REPO,
    target:Path|None=None,
    verify_source:Callable[[Path,str],bool]=source_main,
    verify_ci:Callable[[str],bool]=ci_readback,
    verify_canary:Callable[[],bool]=canary_source_readback,
)->dict[str,Any]:
    need(os.geteuid()!=0,
         "ROOT_NOT_REQUIRED_FOR_SOURCE_PACKET")
    need(len(sha)==40 and all(c in "0123456789abcdef" for c in sha),
         "INVALID_REVIEWED_MAIN_SHA")
    need(verify_source(repo,sha) is True,"PROTECTED_MAIN_NOT_EXACT")
    need(verify_ci(sha) is True,"PROTECTED_REQUIRED_CI_NOT_GREEN")
    need(verify_ci(root.CANDIDATE) is True,
         "REVIEWED_CANARY_REQUIRED_CI_NOT_GREEN")
    need(verify_canary() is True,
         "IMMUTABLE_PROVIDERFREE_SOURCE_NOT_ATTESTED")
    target=target or root.stage_dir(sha)
    resolved=target.resolve(strict=False)
    need(resolved.parent==root.ARTIFACT_PARENT
         or str(resolved).startswith("/tmp/"),
         "PACKET_DESTINATION_OUTSIDE_UNPRIVILEGED_AREA")
    need(not target.exists() and not target.is_symlink(),
         "SOURCE_PACKET_ALREADY_PREPARED")
    data={file:git_blob(repo,sha,file) for file in SOURCES}
    need(len(data)==len(set(SOURCES)),
         "SOURCE_PACKET_DUPLICATE_PATH")
    target.mkdir(mode=0o700)
    try:
        for filename,content in data.items():
            dest=target/filename
            dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            create_file(dest,content)
        actual={str(p.relative_to(target)) for p in target.rglob("*")
                if p.is_file()}
        need(actual==set(SOURCES),"SOURCE_PACKET_FILE_SET_DRIFT")
        for filename,content in data.items():
            need((target/filename).read_bytes()==content,
                 "SOURCE_AFTER_STAGE_CHANGED")
        return {
            "status":"immutable_unprivileged_exact_source_prepared",
            "candidate_sha":root.CANDIDATE,
            "root_build_sha":sha,
            "owner_approval_issued":False,
            "production_mutations":False,
            "scope_sha256":root.SCOPE_SHA,
            "manifest_sha256":root.MANIFEST_SHA,
            "root_source_hashes":{
                path:sha256(data[path]).hexdigest() for path in SOURCES},
            "approved_action":root.ACTION,
            "local_command":str(
                target/"tools/pmv4_e_canary_oneowner_local.sh"),
        }
    except BaseException:
        for p in reversed(sorted(target.rglob("*"),key=lambda p:len(p.parts))):
            if p.is_file():p.unlink()
            elif p.is_dir():p.rmdir()
        target.rmdir()
        raise


def main():
    import argparse
    cli=argparse.ArgumentParser()
    cli.add_argument("--source-sha",required=True)
    x=cli.parse_args()
    result=prepare(x.source_sha)
    print("PMV4_E_EXACT_ONEOWNER_SOURCE_PACKET=PREPARED")
    print("ROOT_BUILD_SHA="+result["root_build_sha"])
    print("CANDIDATE_SHA="+result["candidate_sha"])
    print("EXACT_SCOPE_SHA256="+result["scope_sha256"])
    print("EXACT_MANIFEST_SHA256="+result["manifest_sha256"])
    print("OWNER_APPROVAL_ISSUED=false; PRODUCTION_MUTATIONS=false")
    print("LOCAL_COMMAND=bash "+result["local_command"]+" --execute")


if __name__=="__main__":
    try:main()
    except (StageDenied,OSError,ValueError,
            subprocess.TimeoutExpired) as exc:
        print("PMV4_E_PACKET_DENIED:"+type(exc).__name__
              +( ":"+str(exc)[:140] if isinstance(exc,StageDenied)
               else ""))
        raise SystemExit(2)
