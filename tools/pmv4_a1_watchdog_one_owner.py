#!/usr/bin/env python3
"""Exactly one Entra Owner consent for the bounded PMv4 A1 watchdog root delta.

Source-only until run on a real interactive Owner TTY after root preflight.
Uses the existing pinned Owner Ed25519 signer and verification policy.
No Teams, new signing key, standing authorization, or production write.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid
from typing import Any

from tools import pmv4_a1_watchdog_policy_root as root

OWNER_SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
WORKTREE=Path("/srv/jason/archive/engineering-worktrees/pmv4-a1-watchdog-allowlist-20261116")
REPO=Path("/home/al/.local/lib/jason/engineering-source-repo")
CONFIRM="APPROVE-EXACT-ONE-PMV4-A1-WATCHDOG-CONTAINER-860DC8"


class OwnerWatchdogDenied(PermissionError):
    pass


def need(value:bool,reason:str)->None:
    if not value:
        raise OwnerWatchdogDenied(reason)


def module_from_root_file(path:Path,digest:str,name:str):
    metadata=path.lstat()
    need(stat.S_ISREG(metadata.st_mode) and metadata.st_uid==0
         and metadata.st_gid==0 and not path.is_symlink()
         and not metadata.st_mode&0o022
         and root.digest(path.read_bytes())==digest,
         "A1_OWNER_EXISTING_SIGNER_TRUST_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "A1_OWNER_SIGNER_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gh(*args:str)->str:
    result=subprocess.run(["/usr/bin/gh",*args],capture_output=True,text=True,
                          check=False,timeout=30)
    need(result.returncode==0,"A1_OWNER_GITHUB_RECEIPT_NOT_READY")
    return result.stdout


def git_blob(revision:str)->bytes:
    repository=REPO if revision==root.BASE else WORKTREE
    need(revision in (root.BASE,root.SOURCE),"A1_OWNER_GIT_REVISION_NOT_PINNED")
    result=subprocess.run(
        ["/usr/bin/git","-C",str(repository),"show",
         revision+":config/production-desired-state.json"],
        capture_output=True,check=False,timeout=20)
    need(result.returncode==0,"A1_OWNER_GIT_SOURCE_UNAVAILABLE")
    return result.stdout


def source_checks()->str:
    need(gh("api","repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha").strip()==root.BASE,
         "A1_OWNER_PROTECTED_MAIN_SHA_CHANGED")
    review=json.loads(gh("pr","view",root.GIT_PR,
                         "--repo","al-teamaot-com/jason",
                         "--json","headRefOid,isDraft,state"))
    reviewed_head=review.get("headRefOid")
    need(isinstance(reviewed_head,str) and len(reviewed_head)==40
         and review=={"headRefOid":reviewed_head,"isDraft":True,"state":"OPEN"},
         "A1_OWNER_SOURCE_PR_CHANGED")
    ancestry=subprocess.run(["/usr/bin/git","-C",str(WORKTREE),
                             "merge-base","--is-ancestor",root.SOURCE,reviewed_head],
                            capture_output=True,check=False,timeout=20)
    need(ancestry.returncode==0,"A1_OWNER_REVIEWED_SOURCE_NOT_ANCESTOR")
    results=gh("pr","checks",root.GIT_PR,"--repo","al-teamaot-com/jason")
    states=[line.split("\t") for line in results.splitlines() if line.strip()]
    need(len(states)>=10 and all(len(x)>=2 and x[1]=="pass" for x in states),
         "A1_OWNER_SOURCE_CI_NOT_ALL_PASS")
    before=json.loads(git_blob(root.BASE))
    reviewed=subprocess.run(["/usr/bin/git","-C",str(WORKTREE),"show",
                             reviewed_head+":config/production-desired-state.json"],
                            capture_output=True,check=False,timeout=20)
    need(reviewed.returncode==0,"A1_OWNER_REVIEWED_SOURCE_UNAVAILABLE")
    after_blob=reviewed.stdout
    after=json.loads(after_blob)
    need(root.digest(after_blob)==root.SOURCE_POLICY_SHA
         and set(after)==set(before)
         and root.NAME not in before["allowed_running_containers"]
         and after["allowed_running_containers"]==
             before["allowed_running_containers"]+[root.NAME]
         and all(after[k]==before[k] for k in before
                 if k!="allowed_running_containers"),
         "A1_OWNER_SOURCE_POLICY_DIFF_NOT_EXACT")
    return reviewed_head


def exact_plan()->dict[str,Any]:
    need(os.geteuid()==1000 and Path(__file__).resolve().parents[1]==WORKTREE,
         "A1_OWNER_LOCAL_SOURCE_NOT_TRUSTED")
    root_file=WORKTREE/"tools/pmv4_a1_watchdog_policy_root.py"
    need(root_file.is_file() and not root_file.is_symlink()
         and root.digest(root_file.read_bytes())==root.fixed_plan()["root_executor_sha256"],
         "A1_OWNER_INSTALLER_SOURCE_CHANGED")
    reviewed_head=source_checks()
    need(root.digest(root.FREEZE.read_bytes())==root.FREEZE_SHA
         and root.digest(root.HOLD.read_bytes())==root.HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name==root.LKG,
         "A1_OWNER_PRODUCTION_CONTROLS_CHANGED")
    plan=root.fixed_plan()
    plan["reviewed_pr_head_sha"]=reviewed_head
    plan["scope_sha256"]=root.digest(root.canon(plan))
    return plan


def prepare_plan()->dict[str,Any]:
    plan=exact_plan()
    if not root.PACK.exists():
        root.PACK.mkdir(mode=0o700)
    # This archive parent has inherited SGID. Remove SGID from the newly
    # created, user-owned evidence folder before binding signed proof files.
    if root.PACK.lstat().st_uid==os.geteuid():
        os.chmod(root.PACK,0o700)
    directory=root.PACK.lstat()
    need(directory.st_uid==os.geteuid()
         and stat.S_IMODE(directory.st_mode)==0o700
         and not root.PACK.is_symlink(),
         "A1_OWNER_ARTIFACT_DIRECTORY_UNTRUSTED")
    if root.PLAN.exists() or root.PLAN.is_symlink():
        need(root.object_file(root.PLAN)==plan,
             "A1_OWNER_REVIEWED_PLAN_MISMATCH")
    else:
        create_exclusive(root.PLAN,root.canon(plan))
    need(root.object_file(root.PLAN)==plan,
         "A1_OWNER_PLAN_WRITE_VERIFICATION_FAILED")
    return plan


def create_exclusive(path:Path,data:bytes)->None:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    need(root.digest(path.read_bytes())==root.digest(data),
         "A1_OWNER_EVIDENCE_PERSISTENCE_FAILED")


def sign_one_scope(*,signer:Any,owner_oid:str,owner_principal:str,
                   plan:dict[str,Any],at:datetime,approval_id:str):
    signed=signer.issue_exact_owner_release(
        approval_id=approval_id,
        release_id="release-"+root.SOURCE[:16],
        candidate_sha=root.SOURCE,
        rollback_sha=root.BASE,
        scope_sha256=plan["scope_sha256"],
        manifest_sha256=root.digest(root.canon(plan)),
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,
        verified_owner_oid=owner_oid,
        verified_principal=owner_principal,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=at,
        private_key=signer.read_service_owner_signing_key(PRIVATE),
    )
    return {
        "schema_version":"1.0",
        "action":root.ACTION,
        "source_sha":root.SOURCE,
        "scope_sha256":plan["scope_sha256"],
        "approval_id":approval_id,
        "signed_release":signed,
    }


def interactive_entra(auth:Any)->str:
    root_url="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    challenge=auth._form(root_url+"devicecode",
                         {"client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    need(all(isinstance(challenge.get(k),str)
             for k in ("device_code","user_code","verification_uri")),
         "A1_OWNER_ENTRA_DEVICE_CHALLENGE_FAILED")
    lifetime=min(600,int(challenge.get("expires_in",0)))
    need(lifetime>=60,"A1_OWNER_DEVICE_CHALLENGE_TOO_SHORT")
    print("EXACT_ACTION="+root.ACTION,flush=True)
    print("EXACT_REVIEWED_SOURCE_SHA="+root.SOURCE,flush=True)
    print("EXACT_ROOT_ORIGINAL_SHA256="+root.OLD_SHA,flush=True)
    print("EXACT_ROOT_PROPOSED_SHA256="+root.NEW_SHA,flush=True)
    print("EXACT_SCOPE_SHA256="+root.object_file(root.PLAN)["scope_sha256"],flush=True)
    print("ONLY_ONE_OPTIONAL_CONTAINER="+root.NAME,flush=True)
    print("OWNER_AUTH_CONSENTS=1; STANDING_AUTHORITY=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    until=time.monotonic()+lifetime
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<until:
        time.sleep(interval)
        response=auth._form(root_url+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,"device_code":challenge["device_code"],
        })
        if isinstance(response.get("access_token"),str):
            oid=auth.jwt_owner(response["access_token"])
            confirm=input("Approve ONLY the exact one-container policy: "+CONFIRM+": ")
            need(confirm.strip()==CONFIRM,
                 "A1_OWNER_EXACT_ACTION_NOT_APPROVED")
            return oid
        if response.get("error")=="slow_down":
            interval=min(20,interval+5)
        elif response.get("error")!="authorization_pending":
            raise OwnerWatchdogDenied("A1_OWNER_ENTRA_CHALLENGE_DENIED")
    raise OwnerWatchdogDenied("A1_OWNER_ENTRA_CHALLENGE_EXPIRED")


def authorize()->None:
    need(sys.stdin.isatty() and sys.stdout.isatty(),
         "A1_OWNER_REAL_INTERACTIVE_TTY_REQUIRED")
    need(not root.PROOF.exists() and not root.PROOF.is_symlink(),
         "A1_OWNER_PROOF_ALREADY_ISSUED")
    plan=prepare_plan()
    signer=module_from_root_file(OWNER_SIGNER,OWNER_SHA,
                                 "pmv4_a1_existing_owner_signed_release")
    auth=module_from_root_file(OAUTH,OAUTH_SHA,
                               "pmv4_a1_existing_entra_auth")
    public=signer.read_pinned_root_owner_public_key(root.ROOT_KEY)
    oid=interactive_entra(auth)
    need(oid in signer.EXACT_OWNER_OAUTH_SUBJECTS,
         "A1_OWNER_OAUTH_SUBJECT_NOT_TRUSTED")
    need(prepare_plan()==plan,"A1_OWNER_EXACT_SCOPE_CHANGED_DURING_AUTH")
    at=datetime.now(timezone.utc)
    receipt=sign_one_scope(
        signer=signer, owner_oid=oid,
        owner_principal=signer.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        plan=plan,at=at,
        approval_id="owner-mcp-"+uuid.uuid4().hex,
    )
    validated=signer.verify_exact_owner_release(
        receipt["signed_release"],public_key=public,at=at,
        expected_candidate_sha=root.SOURCE,
        expected_rollback_sha=root.BASE,
        expected_release_id="release-"+root.SOURCE[:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=root.digest(root.canon(plan)),
        expected_freeze_sha256=root.FREEZE_SHA,
    )
    need(validated["approval_id"]==receipt["approval_id"]
         and validated["owner_oid"]==oid,
         "A1_OWNER_SIGNATURE_AND_ID_UNVERIFIED")
    create_exclusive(root.PROOF,root.canon(receipt))
    need(root.object_file(root.PROOF)==receipt,
         "A1_OWNER_SIGNED_PROOF_NOT_PERSISTED")
    print("A1_ONE_ENRA_OWNER_EXACT_RELEASE=RECORDED")
    print("OWNER_APPROVAL_ID="+receipt["approval_id"])
    print("ROOT_MUTATIONS=false; PRODUCTION_WATCHDOG_NOT_CHANGED")


def main()->int:
    parser=argparse.ArgumentParser()
    command=parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--prepare-plan",action="store_true")
    command.add_argument("--check-only",action="store_true")
    command.add_argument("--authorize",action="store_true")
    args=parser.parse_args()
    try:
        if args.prepare_plan:
            plan=prepare_plan()
            print("A1_POLICY_ONE_OWNER_PLAN_SHA256="+root.digest(root.canon(plan)))
            print("ONE_OWNER_SOURCE_ONLY=true; ROOT_MUTATIONS=false")
        elif args.check_only:
            plan=prepare_plan()
            need(not root.PROOF.exists() and not root.PROOF.is_symlink(),
                 "A1_OWNER_PROOF_ALREADY_ISSUED")
            print("A1_POLICY_ONE_OWNER_SIGNED_SCOPE_PREFLIGHT=PASS")
            print("OWNER_APPROVAL_USED=false; ROOT_MUTATIONS=false")
        else:authorize()
        return 0
    except Exception as exc:
        code=str(exc)
        if not code or len(code)>140 or "/" in code:
            code="A1_OWNER_INTERNAL_DENIAL"
        print("A1_OWNER=DENIED "+type(exc).__name__+":"+code,
              file=sys.stderr,flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
