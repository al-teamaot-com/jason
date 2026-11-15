#!/usr/bin/env python3
"""Fresh Entra authenticated one-use Owner signature for the exact A0 root trust pair.

No root changes, signer exports, standing releases or Teams dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid

CANDIDATE="8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION="pmv4-a0-ci-policy-root-trust-twofile-migration-v1"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
REVIEW_SHA="5c9ddd10825c7a2e13a134dd5458d16d2eadfd9bea3bd991cb6427e658071138"
PACKAGE_SHA="be49db761f381b8d570773c50d9bcdd5e3248135684094461dc2596aacdab402"
ROOT_SHA="0660aa5ab58c9b8e4ed69bb8628f031b20162862338c52c0386b5fbb9820f903"
EXPECTED_SCOPE="af39b52bfcc5e2b5d3e0cf39932be0325a74e574af447588ebc92b866a970453"
ARCHIVE=Path("/srv/jason/archive")
MANIFEST=ARCHIVE/("pmv4-a0-root-trust-twofile-migration-"+CANDIDATE+"-SIGNED-REVIEW.json")
PACKAGE=ARCHIVE/("pmv4-a0-root-trust-twofile-migration-"+CANDIDATE+".tar")
PROOF=ARCHIVE/("pmv4-a0-root-trust-twofile-OWNER-PROOF-"+CANDIDATE+".json")
WORKTREE=Path("/srv/jason/archive/engineering-worktrees/pmv4-a0-rebind-20261115")
ROOT_CODE=WORKTREE/"tools/pmv4_a0_exact_twofile_root_trust_migrator.py"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
VERIFIER=Path("/usr/local/lib/jason/owner_signed_release.py")
VERIFIER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
PIN=Path("/etc/jason-owner-release/verified-owner-public-key.json")
SIGNER=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONFIRM="APPROVE-EXACT-TWO-ROOT-TRUST-FILES-8C20"

class TrustOwnerDenied(PermissionError):
    pass

def need(ok,code):
    if not ok: raise TrustOwnerDenied(code)

def hashbytes(raw):return sha256(raw).hexdigest()

def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def module(path,name):
    st=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(st.st_mode)
         and st.st_uid==0 and not (st.st_mode & 0o022),
         "EXACT_ROOT_OWNER_LIBRARY_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "OWNER_LIBRARY_NOT_AVAILABLE")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def review():
    need(os.geteuid()==1000,"UID1000_LOCAL_OWNER_REQUIRED")
    need(hashbytes(MANIFEST.read_bytes())==REVIEW_SHA
         and hashbytes(PACKAGE.read_bytes())==PACKAGE_SHA
         and hashbytes(ROOT_CODE.read_bytes())==ROOT_SHA,
         "ROOT_TRUST_PREVIEW_SOURCE_SHA_DRIFT")
    need(hashbytes(VERIFIER.read_bytes())==VERIFIER_SHA,
         "OWNER_VERIFIER_HASH_DRIFT")
    p=json.loads(MANIFEST.read_bytes())
    need(p["candidate_sha"]==CANDIDATE and p["action"]==ACTION
         and p["root_executor_sha256"]==ROOT_SHA
         and p["package_sha256"]==PACKAGE_SHA
         and p["scope_sha256"]==EXPECTED_SCOPE
         and p["scope_sha256"]==hashbytes(canon({k:v for k,v in p.items()
                                                  if k!="scope_sha256"})),
         "OWNER_ROOT_TRUST_REVIEW_DRIFT")
    need(hashbytes(FREEZE.read_bytes())==FREEZE_SHA
         and hashbytes(HOLD.read_bytes())==HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "OWNER_PRODUCTION_FREEZE_OR_LKG_DRIFT")
    main=subprocess.check_output(
        ["git","-C","/home/al/.local/lib/jason/engineering-source-repo",
         "rev-parse","origin/main"],text=True,timeout=10).strip()
    need(main==CANDIDATE,"OWNER_PROTECTED_MAIN_CHANGED")
    return p

def owner_login(oauth):
    endpoint="https://login.microsoftonline.com/"+oauth.TENANT+"/oauth2/v2.0/"
    challenge=oauth._form(endpoint+"devicecode",{
       "client_id":oauth.CLIENT_ID,"scope":oauth.SCOPE})
    need(all(isinstance(challenge.get(k),str)
             for k in ("device_code","user_code","verification_uri")),
         "EXACT_OWNER_ENTRA_UNAVAILABLE")
    deadline=time.monotonic()+min(600,int(challenge.get("expires_in",0)))
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+CANDIDATE,flush=True)
    print("SCOPE_SHA256="+EXPECTED_SCOPE,flush=True)
    print("ONLY_TWO_ROOT_FILES=true; NO_RUNTIME_RESTART=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<deadline:
        time.sleep(interval)
        token=oauth._form(endpoint+"token",{
           "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
           "client_id":oauth.CLIENT_ID,"device_code":challenge["device_code"]})
        if isinstance(token.get("access_token"),str):
            oid=oauth.jwt_owner(token["access_token"])
            need(input("Approve the EXACT TWO root file replacements with "+CONFIRM+": ").strip()==CONFIRM,
                 "EXACT_ROOT_TRUST_OWNER_CONFIRMATION_REQUIRED")
            return oid
        if token.get("error")=="slow_down":interval=min(20,interval+5)
        elif token.get("error")!="authorization_pending":
            raise TrustOwnerDenied("ROOT_TRUST_OWNER_LOGIN_DENIED")
    raise TrustOwnerDenied("ROOT_TRUST_OWNER_LOGIN_EXPIRED")

def verify_proof(p):
    record=json.loads(PROOF.read_bytes())
    need(set(record)=={"schema_version","action","source_sha","scope_sha256",
                       "manifest_sha256","signed_owner_proof"}
         and record["source_sha"]==CANDIDATE
         and record["action"]==ACTION
         and record["scope_sha256"]==p["scope_sha256"]
         and record["manifest_sha256"]==hashbytes(canon(p)),
         "EXACT_ROOT_TRUST_PROOF_DRIFT")
    v=module(VERIFIER,"trusted_root_trust_owner_verifier")
    proof=v.verify_exact_owner_release(
      record["signed_owner_proof"],
      public_key=v.read_pinned_root_owner_public_key(PIN),
      at=datetime.now(timezone.utc),
      expected_candidate_sha=CANDIDATE,
      expected_rollback_sha=LKG,
      expected_release_id="release-"+CANDIDATE[:16],
      expected_scope_sha256=p["scope_sha256"],
      expected_manifest_sha256=hashbytes(canon(p)),
      expected_freeze_sha256=FREEZE_SHA)
    return proof["approval_id"]

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only",action="store_true")
    group.add_argument("--authorize",action="store_true")
    group.add_argument("--verify-proof",action="store_true")
    args=parser.parse_args()
    try:
        p=review()
        if args.check_only:
            need(not PROOF.exists() and not PROOF.is_symlink(),
                 "ALREADY_AUTHORIZED_OR_UNTRUSTED_PROOF")
            print("ROOT_TRUST_ONE_OWNER_REVIEW=PASS")
            print("OWNER_APPROVAL_CONSUMED=false; PRODUCTION_CHANGES=false")
            return 0
        if args.verify_proof:
            print("OWNER_APPROVAL_ID="+verify_proof(p));return 0
        need(sys.stdin.isatty() and sys.stdout.isatty() and
             not PROOF.exists() and not PROOF.is_symlink(),
             "FRESH_OWNER_LOCAL_TTY_AND_ONE_SHOT_REQUIRED")
        oauth=module(OAUTH,"a0_exact_root_trust_oauth")
        v=module(VERIFIER,"a0_exact_root_trust_signer")
        oid=owner_login(oauth)
        need(oid in v.EXACT_OWNER_OAUTH_SUBJECTS,"UNAUTHORIZED_OWNER_ID")
        need(review()==p,"ROOT_TRUST_SOURCE_CHANGED_DURING_OWNER_LOGIN")
        now=datetime.now(timezone.utc)
        signed=v.issue_exact_owner_release(
           approval_id="owner-mcp-"+uuid.uuid4().hex,
           release_id="release-"+CANDIDATE[:16],
           candidate_sha=CANDIDATE,rollback_sha=LKG,
           scope_sha256=p["scope_sha256"],manifest_sha256=hashbytes(canon(p)),
           freeze_sha256=FREEZE_SHA,
           verified_tenant_id=v.TID,verified_owner_oid=oid,
           verified_principal=v.EXACT_OWNER_OAUTH_SUBJECTS[oid],
           verified_organization_id="aot",
           confirmed_decision="approve",at=now,
           private_key=v.read_service_owner_signing_key(SIGNER))
        v.verify_exact_owner_release(
           signed,public_key=v.read_pinned_root_owner_public_key(PIN),
           at=now,expected_candidate_sha=CANDIDATE,
           expected_rollback_sha=LKG,
           expected_release_id="release-"+CANDIDATE[:16],
           expected_scope_sha256=p["scope_sha256"],
           expected_manifest_sha256=hashbytes(canon(p)),
           expected_freeze_sha256=FREEZE_SHA)
        raw=canon({"schema_version":"1.0","action":ACTION,
                   "source_sha":CANDIDATE,"scope_sha256":p["scope_sha256"],
                   "manifest_sha256":hashbytes(canon(p)),
                   "signed_owner_proof":signed})+b"\n"
        fd=os.open(PROOF,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
                   getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            need(os.write(fd,raw)==len(raw),"OWNER_SIGNED_PROOF_SHORT_WRITE")
            os.fsync(fd)
        finally:os.close(fd)
        print("ONE_EXACT_OWNER_ROOT_TRUST_PROOF=RECORDED")
        print("ROOT_MUTATIONS=false");return 0
    except (TrustOwnerDenied,OSError,ValueError,KeyError,
            subprocess.SubprocessError) as exc:
        print("A0_OWNER_TRUST_ISSUER=DENIED "+type(exc).__name__+":"+str(exc)[:140],
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
