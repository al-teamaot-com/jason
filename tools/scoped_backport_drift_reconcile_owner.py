#!/usr/bin/env python3
"""One authenticated Entra Owner consent for four-unit catalog drift policy repair.

No root/service/data/container mutation occurs here. The proof is bound to one
immutable plan; the separately staged root executor independently re-verifies it.
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
from typing import Any, Mapping

ACTION="scoped-backport-four-unit-drift-policy-reconcile-v1"
CONFIRM="APPROVE-ONE-EXACT-SCOPED-BACKPORT-FOUR-UNIT-RECONCILE"
OWNER_SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")

class StageCOwnerDenied(PermissionError):
    pass

def need(ok:bool,code:str)->None:
    if not ok: raise StageCOwnerDenied(code)

def canon(value:Mapping[str,Any])->bytes:
    return json.dumps(dict(value),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def sha(raw:bytes)->str:
    return sha256(raw).hexdigest()

def read_json(path:Path,maxsize:int=3_000_000)->dict[str,Any]:
    try:
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_nlink==1 and 0<meta.st_size<=maxsize,
             "SCOPED_BACKPORT_DRIFT_OWNER_PLAN_UNTRUSTED")
        value=json.loads(path.read_bytes())
        need(isinstance(value,dict),"SCOPED_BACKPORT_DRIFT_OWNER_PLAN_NOT_OBJECT")
        return value
    except (OSError,ValueError,TypeError) as exc:
        raise StageCOwnerDenied("SCOPED_BACKPORT_DRIFT_OWNER_PLAN_UNAVAILABLE") from exc

def trusted(path:Path,digest:str,name:str):
    meta=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==0 and not meta.st_mode&0o022
         and sha(path.read_bytes())==digest,
         "SCOPED_BACKPORT_DRIFT_OWNER_EXISTING_TRUSTED_LIBRARY_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "SCOPED_BACKPORT_DRIFT_OWNER_TRUSTED_LIBRARY_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def exact_plan(path:Path)->dict[str,Any]:
    need(os.geteuid()==1000,"SCOPED_BACKPORT_DRIFT_OWNER_UID1000_REQUIRED")
    plan=read_json(path)
    need(plan.get("schema_version")=="1.0"
         and plan.get("action")==ACTION
         and plan.get("owner_consents")==1
         and plan.get("standing_authority") is False
         and plan.get("later_stages_authorized") is False
         and plan.get("production_mutations")==["root_scoped_backport_four_unit_allowlist","watchdog_oneshot","restore_exact_baseline_on_failure","one_use_audit_receipts"]
         and plan.get("scoped_backport_unit_names")==list((
             "jason-scoped-backport-recovery.service",
             "jason-scoped-backport-recovery.timer",
             "jason-scoped-backport-requests.path",
             "jason-scoped-backport-requests.service",
         ))
         and plan.get("restart_containers")==[]
         and plan.get("candidate_sha")==plan.get("source_sha"),
         "SCOPED_BACKPORT_DRIFT_OWNER_SCOPE_NOT_EXACT")
    scope=plan.get("scope_sha256")
    unsigned=dict(plan);unsigned.pop("scope_sha256",None)
    need(isinstance(scope,str) and sha(canon(unsigned))==scope,
         "SCOPED_BACKPORT_DRIFT_OWNER_SCOPE_HASH_INVALID")
    candidate=plan.get("candidate_sha")
    need(isinstance(candidate,str) and len(candidate)==40
         and path.parent.name=="scoped-backport-drift-"+candidate
         and path.name=="root-release-plan.json",
         "SCOPED_BACKPORT_DRIFT_OWNER_ARTIFACT_PATH_INVALID")
    proof=path.parent/"root-oneowner-proof.json"
    need(not proof.exists() and not proof.is_symlink(),
         "SCOPED_BACKPORT_DRIFT_OWNER_ALREADY_AUTHORIZED")
    main=subprocess.check_output(
        ["/usr/bin/gh","api","repos/al-teamaot-com/jason/branches/main",
         "--jq",".commit.sha"],text=True,timeout=20).strip()
    need(main==candidate,"SCOPED_BACKPORT_DRIFT_OWNER_PROTECTED_MAIN_CHANGED")
    need(sha(FREEZE.read_bytes())==plan.get("freeze_sha256")
         and sha(HOLD.read_bytes())==plan.get("hold_sha256")
         and Path("/opt/jason/current").resolve(strict=True).name
             ==plan.get("production_lkg_sha"),
         "SCOPED_BACKPORT_DRIFT_OWNER_PRODUCTION_CONTROLS_CHANGED")
    return plan

def release_id(plan:Mapping[str,Any])->str:
    """The *pinned* native Owner signer requires release-{SHA[:16]}.

    Stage C artifact paths and release transaction IDs are still pmv4-c-*;
    that separate namespace must never be used for the cryptographic claim.
    """
    sha_value=plan.get("candidate_sha")
    need(isinstance(sha_value,str) and len(sha_value)==40
         and all(c in "0123456789abcdef" for c in sha_value),
         "SCOPED_BACKPORT_DRIFT_OWNER_RELEASE_ID_SOURCE_INVALID")
    return "release-"+sha_value[:16]


def signer_contract_preflight(signer:Any,plan:Mapping[str,Any])->None:
    """Ephemeral in-memory sign+verify, before Entra login or production work.

    Exercise BOTH allowed Owner OIDs using the real pinned signer schema.
    No production signing key, token, Owner grant, receipt or provider call.
    """
    key=signer.Ed25519PrivateKey.generate()
    instant=datetime.now(timezone.utc)
    for oid,principal in sorted(signer.EXACT_OWNER_OAUTH_SUBJECTS.items()):
        signed=signer.issue_exact_owner_release(
            approval_id="owner-mcp-"+uuid.uuid4().hex,
            release_id=release_id(plan),
            candidate_sha=plan["candidate_sha"],
            rollback_sha=plan["rollback_sha"],
            scope_sha256=plan["scope_sha256"],
            manifest_sha256=sha(canon(plan)),
            freeze_sha256=plan["freeze_sha256"],
            verified_tenant_id=signer.TID,
            verified_owner_oid=oid,
            verified_principal=principal,
            verified_organization_id="aot",
            confirmed_decision="approve",at=instant,private_key=key)
        verified=signer.verify_exact_owner_release(
            signed,public_key=key.public_key(),at=instant,
            expected_candidate_sha=plan["candidate_sha"],
            expected_rollback_sha=plan["rollback_sha"],
            expected_release_id=release_id(plan),
            expected_scope_sha256=plan["scope_sha256"],
            expected_manifest_sha256=sha(canon(plan)),
            expected_freeze_sha256=plan["freeze_sha256"])
        need(verified["owner_oid"]==oid
             and verified["release_id"]==release_id(plan),
             "SCOPED_BACKPORT_DRIFT_OWNER_SIGNER_SCHEMA_NOT_COMPATIBLE")


def authenticate(auth:Any,plan:Mapping[str,Any])->str:
    endpoint=("https://login.microsoftonline.com/"+auth.TENANT+
              "/oauth2/v2.0/")
    challenge=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    need(all(isinstance(challenge.get(x),str)
             for x in ("device_code","user_code","verification_uri")),
         "SCOPED_BACKPORT_DRIFT_OWNER_ENTRA_DEVICE_FLOW_UNAVAILABLE")
    lifetime=min(600,int(challenge.get("expires_in",0)))
    need(lifetime>=60,"SCOPED_BACKPORT_DRIFT_OWNER_DEVICE_CODE_TOO_SHORT")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("EXACT_SOURCE_SHA="+plan["candidate_sha"],flush=True)
    print("EXACT_SCOPE_SHA256="+plan["scope_sha256"],flush=True)
    print("ONE_OWNER_APPROVAL_TOTAL=1",flush=True)
    print("SERVICE_RESTARTS=none; WATCHDOG_ONESHOT=one",flush=True)
    print("TICKET_CORE_AND_MCP_UNCHANGED=true",flush=True)
    print("PMV4_LATER_PHASES_AUTHORIZED=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    end=time.monotonic()+lifetime
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<end:
        time.sleep(interval)
        response=auth._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":challenge["device_code"]})
        if isinstance(response.get("access_token"),str):
            oid=auth.jwt_owner(response["access_token"])
            entered=input(
                "Approve exact four-unit drift policy repair by typing "+CONFIRM+": ")
            need(entered.strip()==CONFIRM,
                 "SCOPED_BACKPORT_DRIFT_OWNER_EXACT_CONSENT_NOT_GIVEN")
            return oid
        error=response.get("error")
        if error=="slow_down": interval=min(20,interval+5)
        elif error!="authorization_pending":
            raise StageCOwnerDenied("SCOPED_BACKPORT_DRIFT_OWNER_ENTRA_LOGIN_DENIED")
    raise StageCOwnerDenied("SCOPED_BACKPORT_DRIFT_OWNER_ENTRA_LOGIN_EXPIRED")

def authorize(path:Path)->None:
    need(sys.stdin.isatty() and sys.stdout.isatty(),
         "SCOPED_BACKPORT_DRIFT_OWNER_REAL_LOCAL_TTY_REQUIRED")
    plan=exact_plan(path)
    signer=trusted(OWNER_SIGNER,OWNER_SIGNER_SHA,"c_owner_signer")
    # A signed proof with a schema-invalid release ID must be caught BEFORE
    # asking an Owner to authenticate, not after their affirmative consent.
    signer_contract_preflight(signer,plan)
    auth=trusted(OAUTH,OAUTH_SHA,"c_owner_oauth")
    public=signer.read_pinned_root_owner_public_key(PUBLIC)
    oid=authenticate(auth,plan)
    need(oid in signer.EXACT_OWNER_OAUTH_SUBJECTS,
         "SCOPED_BACKPORT_DRIFT_OWNER_NOT_IN_TRUSTED_ENTRA_BINDING")
    need(exact_plan(path)==plan,
         "SCOPED_BACKPORT_DRIFT_OWNER_SCOPE_CHANGED_DURING_LOGIN")
    approval="owner-mcp-"+uuid.uuid4().hex
    at=datetime.now(timezone.utc)
    signed=signer.issue_exact_owner_release(
        approval_id=approval,
        release_id=release_id(plan),
        candidate_sha=plan["candidate_sha"],
        rollback_sha=plan["rollback_sha"],
        scope_sha256=plan["scope_sha256"],
        manifest_sha256=sha(canon(plan)),
        freeze_sha256=plan["freeze_sha256"],
        verified_tenant_id=signer.TID,
        verified_owner_oid=oid,
        verified_principal=signer.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot",
        confirmed_decision="approve",at=at,
        private_key=signer.read_service_owner_signing_key(PRIVATE))
    verified=signer.verify_exact_owner_release(
        signed,public_key=public,at=at,
        expected_candidate_sha=plan["candidate_sha"],
        expected_rollback_sha=plan["rollback_sha"],
        expected_release_id=release_id(plan),
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=sha(canon(plan)),
        expected_freeze_sha256=plan["freeze_sha256"])
    need(verified["approval_id"]==approval and verified["owner_oid"]==oid,
         "SCOPED_BACKPORT_DRIFT_OWNER_SIGNED_SCOPE_MISMATCH")
    record={
        "schema_version":"1.0","action":ACTION,
        "source_sha":plan["candidate_sha"],
        "scope_sha256":plan["scope_sha256"],
        "plan_sha256":sha(canon(plan)),
        "approval_id":approval,"signed_release":signed,
    }
    proof=path.parent/"root-oneowner-proof.json"
    fd=os.open(proof,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(canon(record));out.flush();os.fsync(out.fileno())
    need(read_json(proof)==record,"SCOPED_BACKPORT_DRIFT_OWNER_PROOF_PERSISTENCE_FAILED")
    print("SCOPED_BACKPORT_DRIFT_OWNER_SINGLE_AUTHENTICATED_CONSENT=VERIFIED",flush=True)
    print("SCOPED_BACKPORT_DRIFT_OWNER_APPROVAL_ID="+approval,flush=True)
    print("PRODUCTION_MUTATIONS=false",flush=True)

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--authorize",action="store_true")
    args=p.parse_args()
    try:
        if args.check_only:
            plan=exact_plan(args.plan)
            signer=trusted(OWNER_SIGNER,OWNER_SIGNER_SHA,"c_owner_signer")
            signer_contract_preflight(signer,plan)
            print("PMV4_C_PINNED_SIGNER_EXACT_PROOF_PREFLIGHT=PASS")
            print("SYNTHETIC_SIGNER_CHECK_ONLY=true; OWNER_PROOF_ISSUED=false")
            print("PMV4_C_ONE_OWNER_EXACT_SCOPE_PREFLIGHT=PASS")
            print("EXACT_SCOPE_SHA256="+plan["scope_sha256"])
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        else:
            authorize(args.plan)
        return 0
    except BaseException as exc:
        code=str(exc)
        if len(code)>180: code="SCOPED_BACKPORT_DRIFT_OWNER_INTERNAL_DENIED"
        print("SCOPED_BACKPORT_DRIFT_OWNER=DENIED "+type(exc).__name__+":"+code,
              file=sys.stderr,flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
