#!/usr/bin/env python3
"""ONE existing Entra Owner v1 release proof for full immutable A0 scope.

The human authenticates ONCE, confirms all three exact A0 stages ONCE, and
signs ONE complete release using Jason's EXISTING service Owner Ed25519 key.
No Teams, private-key disclosure, new signer, standing authorization, or
privileged root action. The independently root-pinned executor verifies it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

WORKTREE=Path(
    "/srv/jason/archive/engineering-worktrees/pmv4-a0-rebind-20261115"
)
PROOF=Path("/srv/jason/archive/pmv4-a0-atomic-v1-OWNER-PROOF-8c20.json")
RELEASE=Path("/var/lib/jason/openclaw/release-manager")
FREEZE=RELEASE/"production-deployment-freeze"
HOLD=RELEASE/"auto-promotion-incident-hold"
VERIFIER=Path("/usr/local/lib/jason/owner_signed_release.py")
VERIFIER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
SIGNER=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
ROOT_PIN=Path("/etc/jason-owner-release/verified-owner-public-key.json")
CONFIRM="APPROVE-ONE-EXACT-PMV4-A0-THREE-STAGE-ATOMIC-RELEASE"
CANDIDATE="8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ACTION="pmv4-a0-exact-three-action-one-release-v1"


class A0OwnerIssuerDenied(PermissionError):
    pass


def need(condition:bool, reason:str)->None:
    if not condition: raise A0OwnerIssuerDenied(reason)


def digest(raw:bytes)->str:
    return sha256(raw).hexdigest()


def canonical(value:Mapping[str,Any])->bytes:
    return json.dumps(dict(value),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def load(path:Path,name:str):
    source=path.lstat()
    need(stat.S_ISREG(source.st_mode) and not path.is_symlink()
         and source.st_uid==0 and not source.st_mode&0o022,
         "A0_ONE_OWNER_LIBRARY_NOT_TRUSTED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "A0_ONE_OWNER_LIBRARY_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_review()->dict[str,Any]:
    need(os.geteuid()==1000 and Path(__file__).resolve().parents[1]==WORKTREE,
         "A0_ONE_OWNER_OPERATOR_LOCAL_SOURCE_REQUIRED")
    need(digest(VERIFIER.read_bytes())==VERIFIER_SHA,
         "A0_ONE_OWNER_EXISTING_SIGNER_VERIFIER_CHANGED")
    from tools.pmv4_a0_one_release_v1_proof import exact_v1_release_scopes
    from tools.pmv4_stage_a0_one_owner_review import exact_contract
    from tools.pmv4_a0_exact_v1_root_release import (
        full_release_scopes,reviewed_policy,
    )
    from tools import pmv4_a0_exact_v1_root_release as root
    old=root.POLICY
    try:
        root.POLICY=WORKTREE/"config/pmv4-stage-a0/atomic-v1-root-policy-review.json"
        policy=reviewed_policy(require_root=False)
    finally:
        root.POLICY=old
    original=exact_contract()
    whole=exact_v1_release_scopes()
    independent=full_release_scopes(policy)
    need(whole["scope_sha256"]==independent["scope_sha256"]
         and whole["manifest_sha256"]==independent["manifest_sha256"]
         and len(whole["manifest"]["exact_ordered_actions"])==3
         and whole["manifest"]["owner_consents"]==1
         and sha256(FREEZE.read_bytes()).hexdigest()==FREEZE_SHA
         and sha256(HOLD.read_bytes()).hexdigest()==HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name==LKG
         and subprocess.check_output(
             ["git","-C",str(Path("/home/al/.local/lib/jason/engineering-source-repo")),
              "rev-parse","origin/main"],text=True,timeout=10
         ).strip()==CANDIDATE,
         "A0_ONE_OWNER_EXACT_PRODUCTION_SOURCE_OR_SCOPE_CHANGED")
    return whole


def device_owner_oid(auth)->str:
    endpoint="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    challenge=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID, "scope":auth.SCOPE,
    })
    need(all(isinstance(challenge.get(key),str)
             for key in ("device_code","user_code","verification_uri")),
         "A0_ONE_OWNER_ENTRA_NOT_AVAILABLE")
    lifespan=min(600,int(challenge.get("expires_in",0)))
    need(lifespan>=60,"A0_ONE_OWNER_ENTRA_CHALLENGE_TOO_SHORT")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("ONE_SIGNED_PARENT_WHOLE_RELEASE=true",flush=True)
    print("STAGE_COUNT=3; EXTRA_OWNER_APPROVALS=0",flush=True)
    print("SOURCE_SHA="+CANDIDATE,flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    until=time.monotonic()+lifespan
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
            entered=input("Approve ONLY exact ALL THREE stages by typing "+
                          CONFIRM+": ")
            need(entered.strip()==CONFIRM,
                 "A0_ONE_OWNER_EXACT_CONFIRMATION_REQUIRED")
            return oid
        if result.get("error")=="slow_down":
            interval=min(20,interval+5)
        elif result.get("error")!="authorization_pending":
            raise A0OwnerIssuerDenied("A0_ONE_OWNER_ENTRA_DENIED")
    raise A0OwnerIssuerDenied("A0_ONE_OWNER_ENTRA_TIMED_OUT")


def verify_existing_proof(whole:Mapping[str,Any]):
    raw=PROOF.read_bytes()
    meta=PROOF.lstat()
    need(not PROOF.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==1000 and meta.st_nlink==1
         and stat.S_IMODE(meta.st_mode)==0o600 and len(raw)<=15000,
         "A0_ONE_OWNER_PROOF_FILE_UNTRUSTED")
    envelope=json.loads(raw)
    need(set(envelope)=={
        "schema_version","action","source_sha","scope_sha256",
        "manifest_sha256","signed_owner_proof"}
         and envelope["schema_version"]=="1.0"
         and envelope["action"]==ACTION
         and envelope["source_sha"]==CANDIDATE
         and envelope["scope_sha256"]==whole["scope_sha256"]
         and envelope["manifest_sha256"]==whole["manifest_sha256"],
         "A0_ONE_OWNER_PROOF_SCOPE_CHANGED")
    v=load(VERIFIER,"a0_existing_owner_proof")
    root=v.read_pinned_root_owner_public_key(ROOT_PIN)
    verified=v.verify_exact_owner_release(
        envelope["signed_owner_proof"],public_key=root,
        at=datetime.now(timezone.utc),
        expected_candidate_sha=CANDIDATE,expected_rollback_sha=LKG,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_scope_sha256=whole["scope_sha256"],
        expected_manifest_sha256=whole["manifest_sha256"],
        expected_freeze_sha256=FREEZE_SHA,
    )
    return verified["approval_id"]


def main()->int:
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--authorize",action="store_true")
    modes.add_argument("--verify-proof",action="store_true")
    args=parser.parse_args()
    try:
        whole=source_review()
        if args.check_only:
            need(not PROOF.exists() and not PROOF.is_symlink(),
                 "A0_ONE_OWNER_PREEXISTING_APPROVAL")
            print("A0_ONE_OWNER_SIGNED_FULL_RELEASE_PREFLIGHT=PASS")
            print("OWNER_APPROVAL_USED=false; PRODUCTION_ROOT_WRITES=false")
            return 0
        if args.verify_proof:
            print("OWNER_APPROVAL_ID="+verify_existing_proof(whole))
            return 0
        need(sys.stdin.isatty() and sys.stdout.isatty()
             and not PROOF.exists() and not PROOF.is_symlink(),
             "A0_ONE_OWNER_INTERACTIVE_ONCE_ONLY")
        oauth=load(OAUTH,"a0_existing_owner_oauth")
        verifier=load(VERIFIER,"a0_existing_owner_signer")
        oid=device_owner_oid(oauth)
        need(oid in verifier.EXACT_OWNER_OAUTH_SUBJECTS,
             "A0_ONE_OWNER_OID_NOT_APPROVED")
        need(source_review()==whole,
             "A0_ONE_OWNER_SOURCE_CHANGED_DURING_LOGIN")
        key=verifier.read_service_owner_signing_key(SIGNER)
        now=datetime.now(timezone.utc)
        signed=verifier.issue_exact_owner_release(
            approval_id="owner-mcp-"+uuid.uuid4().hex,
            release_id="release-"+CANDIDATE[:16],
            candidate_sha=CANDIDATE,rollback_sha=LKG,
            scope_sha256=whole["scope_sha256"],
            manifest_sha256=whole["manifest_sha256"],
            freeze_sha256=FREEZE_SHA,
            verified_tenant_id=verifier.TID,
            verified_owner_oid=oid,
            verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[oid],
            verified_organization_id="aot",
            confirmed_decision="approve",at=now,private_key=key,
        )
        verifier.verify_exact_owner_release(
            signed,public_key=verifier.read_pinned_root_owner_public_key(ROOT_PIN),
            at=now,expected_candidate_sha=CANDIDATE,
            expected_rollback_sha=LKG,
            expected_release_id="release-"+CANDIDATE[:16],
            expected_scope_sha256=whole["scope_sha256"],
            expected_manifest_sha256=whole["manifest_sha256"],
            expected_freeze_sha256=FREEZE_SHA,
        )
        raw=canonical({
            "schema_version":"1.0","action":ACTION,
            "source_sha":CANDIDATE,
            "scope_sha256":whole["scope_sha256"],
            "manifest_sha256":whole["manifest_sha256"],
            "signed_owner_proof":signed,
        })+b"\n"
        fd=os.open(PROOF,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            need(os.write(fd,raw)==len(raw),"A0_ONE_OWNER_SHORT_PROOF_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        print("ONE_ORIGINAL_V1_SIGNED_FULL_A0_RELEASE=RECORDED")
        print("ROOT_MUTATIONS_OCCURRED=false")
        return 0
    except (A0OwnerIssuerDenied,ValueError,OSError,KeyError,
            subprocess.SubprocessError) as exc:
        print("A0_ONE_OWNER=DENIED "+type(exc).__name__+
              ":"+str(exc)[:160],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
