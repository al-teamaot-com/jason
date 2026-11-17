#!/usr/bin/env python3
"""One authenticated Entra Owner decision for full exact PMv4 A1 action.

The same existing Owner signer and Entra verifier used by A0 emit TWO
cryptographically bound scopes (root staging + standalone shadow promotion)
only after ONE confirmed Owner device-code ceremony and ONE approval ID.
No Teams, new signer, standing approval, root mutation, container start,
provider access, or production release is performed by this script.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid
from typing import Any,Mapping

from tools import pmv4_a1_atomic_shadow_root as root

OWNER_SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
CONFIRM="APPROVE-ONE-EXACT-PMV4-A1-DISCONNECTED-SHADOW-BOOTSTRAP"
WORKTREE=Path("/srv/jason/archive/engineering-worktrees/pmv4-a1-shadow-package-20261116")
REPO=Path("/home/al/.local/lib/jason/engineering-source-repo")


class A1OwnerDenied(PermissionError):
    pass


def need(value:bool,code:str)->None:
    if not value:raise A1OwnerDenied(code)


def trusted(path:Path,sha256_hex:str,name:str):
    meta=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==0 and not meta.st_mode&0o022
         and root.sha(path.read_bytes())==sha256_hex,
         "A1_OWNER_EXISTING_TRUSTED_LIBRARY_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "A1_OWNER_TRUSTED_LIBRARY_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_plan()->dict[str,Any]:
    need(os.geteuid()==1000 and Path(__file__).resolve().parents[1]==WORKTREE,
         "A1_OWNER_LOCAL_WORKTREE_REQUIRED")
    require=[WORKTREE/"tools/pmv4_a1_atomic_shadow_root.py",
             WORKTREE/"tools/pmv4_a1_atomic_one_owner.py"]
    need(all(x.is_file() and not x.is_symlink() for x in require),
         "A1_OWNER_REVIEW_SOURCE_UNAVAILABLE")
    evidence=root.read_json(root.ARCHIVE/"evidence.json")
    manifest=root.read_json(root.ARCHIVE/"release"/"release-manifest.json")
    scope=root.read_json(root.ARCHIVE/"reviewed-scope.json")
    root.shadow.manifest_check(manifest)
    need(evidence.get("status")=="preproduction_candidate_not_authorized"
         and evidence.get("source_sha")==root.CANDIDATE
         and evidence.get("image_digest")==root.IMAGE
         and evidence.get("bundle_sha256")==manifest["bundle_sha256"]
         and evidence.get("manifest_sha256")==root.sha(root.canon(manifest))
         and evidence.get("scope_sha256")==root.sha(root.canon(scope))
         and set(evidence.get("source_files",{}))==set(root.FILES)
         and manifest["rollback_sha"]==root.ROLLBACK
         and manifest["candidate_sha"]==root.CANDIDATE,
         "A1_OWNER_IMMUTABLE_SOURCE_PACK_NOT_READY")
    need(root.shadow.bundle_digest(root.ARCHIVE/"release"/"bundle")==manifest["bundle_sha256"],
         "A1_OWNER_SOURCE_PACKAGE_CHANGED")
    need(root.sha(root.GLOBAL_FREEZE.read_bytes())==root.FREEZE_SHA
         and root.sha(root.GLOBAL_HOLD.read_bytes())==root.HOLD_SHA
         and root.sha(root.SHADOW_FREEZE.read_bytes())==
             "c1e6aa23c48df9f87aa98c549086ad65a6fd38716e5a1a5cafd727fbd69fe928"
         and Path("/opt/jason/current").resolve(strict=True).name==root.LKG,
         "A1_OWNER_PRODUCTION_OR_SHADOW_FROZEN_STATE_CHANGED")
    main=subprocess.check_output(
        ["/usr/bin/gh","api",
         "repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
        text=True,timeout=20).strip()
    need(main==root.CANDIDATE,
         "A1_OWNER_PROTECTED_MAIN_SOURCE_CHANGED")
    for rel,digest in evidence["source_files"].items():
        blob=subprocess.check_output(
            ["/usr/bin/git","-C",str(REPO),"show",root.CANDIDATE+":"+rel],
            timeout=20)
        need(root.sha(blob)==digest,
             "A1_OWNER_SOURCE_BLOB_CHANGED")
    return {
        "schema_version":"1.0","action":root.ACTION,
        "candidate_sha":root.CANDIDATE,"rollback_sha":root.ROLLBACK,
        "root_executor_sha256":root.sha(require[0].read_bytes()),
        "image_digest":root.IMAGE,
        "bundle_sha256":manifest["bundle_sha256"],
        "shadow_scope_sha256":manifest["scope_sha256"],
        "shadow_manifest_sha256":root.sha(root.canon(manifest)),
        "shadow_freeze_sha256":root.sha(root.SHADOW_FREEZE.read_bytes()),
        "global_freeze_sha256":root.FREEZE_SHA,
        "global_hold_sha256":root.HOLD_SHA,
        "production_lkg_sha":root.LKG,
        "original_runtime_images":root.IMAGE_IDS,
        "gateway_secret_generation":"root_secure_random_48",
        "source_files":evidence["source_files"],
        "owner_consents":1,
        "standing_authority":False,
        "root_stage_before_owner_authorization":False,
    }


def exact_plan()->dict[str,Any]:
    doc=expected_plan()
    doc["scope_sha256"]=root.sha(root.canon(doc))
    return doc


def prepare_plan()->dict[str,Any]:
    doc=exact_plan()
    if root.PLAN.exists() or root.PLAN.is_symlink():
        need(root.read_json(root.PLAN)==doc,
             "A1_OWNER_PLAN_ALREADY_EXISTS_DIFFERENT")
    else:
        root.PLAN.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(root.PLAN,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   getattr(os,"O_NOFOLLOW",0),0o400)
        with os.fdopen(fd,"wb") as out:
            out.write(root.canon(doc))
            out.flush();os.fsync(out.fileno())
    need(root.read_json(root.PLAN)==doc,
         "A1_OWNER_PLAN_UNVERIFIED")
    return doc


def issue_pair(*,owner_oid:str,owner_principal:str,
               signer:Any,at:datetime,approval_id:str,
               plan:Mapping[str,Any],manifest:Mapping[str,Any])->dict[str,Any]:
    """Pure signing function for offline signature regression tests."""
    common={
        "approval_id":approval_id,
        "release_id":"release-"+root.CANDIDATE[:16],
        "candidate_sha":root.CANDIDATE,
        "rollback_sha":root.ROLLBACK,
        "freeze_sha256":plan["shadow_freeze_sha256"],
        "verified_tenant_id":signer.TID,
        "verified_owner_oid":owner_oid,
        "verified_principal":owner_principal,
        "verified_organization_id":"aot",
        "confirmed_decision":"approve","at":at,
        "private_key":signer.read_service_owner_signing_key(PRIVATE),
    }
    root_signed=signer.issue_exact_owner_release(
        scope_sha256=plan["scope_sha256"],
        manifest_sha256=root.sha(root.canon(plan)),**common)
    shadow_signed=signer.issue_exact_owner_release(
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=root.sha(root.canon(manifest)),**common)
    return {
        "schema_version":"1.0","action":root.ACTION,
        "source_sha":root.CANDIDATE,
        "scope_sha256":plan["scope_sha256"],
        "manifest_sha256":root.sha(root.canon(plan)),
        "approval_id":approval_id,
        "signed_root_release":root_signed,
        "signed_shadow_release":shadow_signed,
    }


def authenticate_owner(auth:Any)->str:
    endpoint="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    challenge=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE,
    })
    need(all(isinstance(challenge.get(x),str)
             for x in ("device_code","user_code","verification_uri")),
         "A1_OWNER_ENTRA_DEVICE_FLOW_UNAVAILABLE")
    lifetime=min(600,int(challenge.get("expires_in",0)))
    need(lifetime>=60,"A1_OWNER_ENTRA_DEVICE_CODE_TOO_SHORT")
    print("EXACT_ACTION="+root.ACTION,flush=True)
    print("EXACT_SOURCE_SHA="+root.CANDIDATE,flush=True)
    print("EXACT_SCOPE_SHA256="+root.read_json(root.PLAN)["scope_sha256"],flush=True)
    print("ONE_OWNER_APPROVAL_TOTAL=1",flush=True)
    print("ONLY_ISOLATED_NETWORK_DISCONNECTED_SHADOW=true",flush=True)
    print("PRODUCTION_TICKET_CORE_CHANGES=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    until=time.monotonic()+lifetime
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<until:
        time.sleep(interval)
        result=auth._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":challenge["device_code"],
        })
        if isinstance(result.get("access_token"),str):
            oid=auth.jwt_owner(result["access_token"])
            entered=input("Approve exact A1 scope by typing "+CONFIRM+": ")
            need(entered.strip()==CONFIRM,
                 "A1_OWNER_EXACT_CONSENT_NOT_GIVEN")
            return oid
        if result.get("error")=="slow_down":
            interval=min(20,interval+5)
        elif result.get("error")!="authorization_pending":
            raise A1OwnerDenied("A1_OWNER_ENTRA_LOGIN_DENIED")
    raise A1OwnerDenied("A1_OWNER_ENTRA_LOGIN_EXPIRED")


def authorize()->None:
    need(sys.stdin.isatty() and sys.stdout.isatty(),
         "A1_OWNER_REAL_LOCAL_TTY_REQUIRED")
    need(not root.OWNER_PROOF.exists() and not root.OWNER_PROOF.is_symlink(),
         "A1_OWNER_ALREADY_AUTHORIZED")
    plan=prepare_plan()
    trusted(OWNER_SIGNER,OWNER_SIGNER_SHA,"a1_existing_owner_signer")
    auth=trusted(OAUTH,OAUTH_SHA,"a1_existing_owner_oauth")
    signer=trusted(OWNER_SIGNER,OWNER_SIGNER_SHA,"a1_existing_owner_release")
    public=signer.read_pinned_root_owner_public_key(root.ROOT_PIN)
    oid=authenticate_owner(auth)
    need(oid in signer.EXACT_OWNER_OAUTH_SUBJECTS,
         "A1_OWNER_NOT_IN_TRUSTED_ENTRA_BINDING")
    need(prepare_plan()==plan,
         "A1_OWNER_REVIEW_CHANGED_DURING_LOGIN")
    at=datetime.now(timezone.utc)
    approval="owner-mcp-"+uuid.uuid4().hex
    manifest=root.read_json(root.ARCHIVE/"release"/"release-manifest.json")
    record=issue_pair(
        owner_oid=oid,
        owner_principal=signer.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        signer=signer,at=at,approval_id=approval,plan=plan,manifest=manifest)
    for signed,scope,record_hash in (
        (record["signed_root_release"],plan["scope_sha256"],
         root.sha(root.canon(plan))),
        (record["signed_shadow_release"],manifest["scope_sha256"],
         root.sha(root.canon(manifest))),
    ):
        verified=signer.verify_exact_owner_release(
            signed,public_key=public,at=at,
            expected_candidate_sha=root.CANDIDATE,
            expected_rollback_sha=root.ROLLBACK,
            expected_release_id="release-"+root.CANDIDATE[:16],
            expected_scope_sha256=scope,
            expected_manifest_sha256=record_hash,
            expected_freeze_sha256=plan["shadow_freeze_sha256"])
        need(verified["approval_id"]==approval and verified["owner_oid"]==oid,
             "A1_OWNER_EXACT_SIGNED_SCOPE_MISMATCH")
    fd=os.open(root.OWNER_PROOF,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(root.canon(record))
        out.flush();os.fsync(out.fileno())
    need(root.read_json(root.OWNER_PROOF)==record,
         "A1_OWNER_SIGNED_EVIDENCE_PERSISTENCE_FAILED")
    print("A1_OWNER_SINGLE_AUTHENTICATED_CONSENT=VERIFIED",flush=True)
    print("A1_OWNER_APPROVAL_ID="+approval,flush=True)
    print("PRODUCTION_MUTATIONS=false",flush=True)


def main()->int:
    p=argparse.ArgumentParser()
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-plan",action="store_true")
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--authorize",action="store_true")
    args=p.parse_args()
    try:
        if args.prepare_plan:
            print("A1_SOURCE_ONLY_PLAN_SHA256="+
                  root.sha(root.canon(prepare_plan())))
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        elif args.check_only:
            need(prepare_plan()==root.read_json(root.PLAN),
                 "A1_OWNER_PLAN_CHANGED")
            need(not root.OWNER_PROOF.exists() and
                 not root.OWNER_PROOF.is_symlink(),
                 "A1_OWNER_ALREADY_AUTHORIZED")
            print("A1_ONE_OWNER_FULL_EXACT_SCOPE_PREFLIGHT=PASS")
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        else:
            authorize()
        return 0
    except Exception as exc:
        code=str(exc)
        if len(code)>140 or "/" in code:code="A1_OWNER_INTERNAL_DENIED"
        print("A1_OWNER=DENIED "+type(exc).__name__+":"+code,
              flush=True,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
