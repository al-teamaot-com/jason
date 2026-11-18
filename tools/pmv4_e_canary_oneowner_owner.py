#!/usr/bin/env python3
"""One authenticated Entra Owner consent for the EXACT Stage E canary test.

Creates an immutable one-use proof only, never changes production,
runs Docker, invokes a provider or grants PMv3 retirement authority.
"""
from __future__ import annotations

from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ISSUER=Path("/usr/local/lib/jason/owner_signed_release.py")
ISSUER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUB=Path("/etc/jason-owner-release/verified-owner-public-key.json")
CONFIRM="APPROVE-ONE-EXACT-PMV4-E-PROVIDERFREE-CANARY-AND-CLEANUP"


def root_module():
    path=Path(__file__).with_name("pmv4_e_canary_oneowner_root.py")
    spec=importlib.util.spec_from_file_location(
        "reviewed_pmv4_e_canary_root_source",path)
    if spec is None or spec.loader is None:
        raise PermissionError("PMV4_E_EXACT_ROOT_SOURCE_NOT_FOUND")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned_module(path:Path,sha:str,name:str,root):
    data=path.read_bytes()
    meta=path.lstat()
    root.need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
              and meta.st_uid==0 and not (meta.st_mode&0o022)
              and root.digest(data)==sha,
              "OWNER_AUTH_ISSUER_SOURCE_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    root.need(spec is not None and spec.loader is not None,
              "PINNED_AUTH_MODULE_MISSING")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def exact_preflight(build_sha:str):
    root=root_module()
    root.need(os.geteuid()==1000,"OWNER_UID1000_REQUIRED")
    root.need(Path(__file__).read_bytes()==root.source_bytes(
        build_sha,"tools/pmv4_e_canary_oneowner_owner.py"),
        "OWNER_EXECUTING_NONREVIEWED_CODE")
    root.preflight(build_sha,strict_root=False)
    p=root.stage_dir(build_sha)/"owner-proof.json"
    root.need(not p.exists() and not p.is_symlink(),
              "OWNER_PROOF_ALREADY_ISSUED")
    manifest,scope,data=root.candidate_packet()
    root.need(root.digest(root.FREEZE.read_bytes())==root.FREEZE_SHA,
              "OWNER_SOURCE_FREEZE_CHANGED")
    signer=pinned_module(ISSUER,ISSUER_SHA,
                         "pmv4_e_owner_release_signer",root)
    auth=pinned_module(OAUTH,OAUTH_SHA,
                       "pmv4_e_owner_entra_auth",root)
    x=PRIVATE.lstat()
    root.need(stat.S_ISREG(x.st_mode) and not PRIVATE.is_symlink()
              and x.st_uid==1000
              and stat.S_IMODE(x.st_mode)==0o400
              and x.st_size==32,
              "OWNER_SIGNER_PRIVATE_KEY_UNTRUSTED")
    private=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    public=signer.read_pinned_root_owner_public_key(
        PUB,require_root_owned=True)
    root.need(signer.public_key_sha256(public)==
              signer.public_key_sha256(private.public_key()),
              "OWNER_KEY_NOT_MATCHING_ROOT_PUBLIC_KEY")
    return root,manifest,signer,auth,private


def authenticate(root,auth,build_sha:str)->str:
    base=("https://login.microsoftonline.com/"+auth.TENANT+
          "/oauth2/v2.0/")
    response=auth._form(base+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    root.need(all(isinstance(response.get(k),str) for k in
             ("device_code","user_code","verification_uri")),
             "ENTRA_EXACT_OWNER_DEVICE_CHALLENGE_INVALID")
    lifetime=min(600,int(response.get("expires_in",0)))
    root.need(lifetime>=60,"ENTRA_OWNER_CHALLENGE_TOO_SHORT")
    print("PMV4_E_EXACT_ACTION="+root.ACTION,flush=True)
    print("REVIEWED_CANARY_SOURCE_SHA="+root.CANDIDATE,flush=True)
    print("REVIEWED_RELEASE_INSTALLER_SHA="+build_sha,flush=True)
    print("EXACT_SCOPE_SHA256="+root.SCOPE_SHA,flush=True)
    print("REUSED_PREPRODUCTION_OCI="+root.IMAGE,flush=True)
    print("OWNER_APPROVALS_TOTAL=1",flush=True)
    print("PROVIDER_CALLS=0; RETIREMENT_AUTHORIZED=false",flush=True)
    print("ONLY_CANARY_RELEASE_AND_CLEANUP=true",flush=True)
    print("PROTECTED_DESIRED_STATE_RESTORED_AFTER_CANARY=true",flush=True)
    print("NO_RUNTIME_MCP_TICKET_CORE_RESTART=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+response["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+response["user_code"],flush=True)
    deadline=time.monotonic()+lifetime
    interval=max(5,min(20,int(response.get("interval",5))))
    while time.monotonic()<deadline:
        token=auth._form(base+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":response["device_code"]})
        if isinstance(token.get("access_token"),str):
            oid=auth.jwt_owner(token["access_token"])
            token=None
            typed=input("Type "+CONFIRM+" to approve ONLY this canary test: ")
            root.need(typed.strip()==CONFIRM,
                      "ONE_EXACT_OWNER_CONFIRMATION_MISSING")
            return oid
        if token.get("error")=="slow_down":
            interval=min(20,interval+5)
        else:
            root.need(token.get("error")=="authorization_pending",
                      "ENTRA_OWNER_AUTHENTICATION_REJECTED")
        time.sleep(interval)
    raise root.Denied("ENTRA_OWNER_APPROVAL_EXPIRED")


def approve(build_sha:str)->None:
    root,manifest,signer,auth,private=exact_preflight(build_sha)
    oid=authenticate(root,auth,build_sha)
    principal=signer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    root.need(principal is not None,"OWNER_IDENTITY_NOT_PINNED")
    signed=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id="release-"+root.CANDIDATE[:16],
        candidate_sha=root.CANDIDATE,
        rollback_sha="0"*40,
        scope_sha256=root.SCOPE_SHA,
        manifest_sha256=root.MANIFEST_SHA,
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,
        verified_owner_oid=oid,
        verified_principal=principal,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=private,
    )
    signer.verify_exact_owner_release(
        signed,public_key=private.public_key(),
        expected_candidate_sha=root.CANDIDATE,
        expected_rollback_sha="0"*40,
        expected_release_id="release-"+root.CANDIDATE[:16],
        expected_scope_sha256=root.SCOPE_SHA,
        expected_manifest_sha256=root.MANIFEST_SHA,
        expected_freeze_sha256=root.FREEZE_SHA,
        at=datetime.now(timezone.utc),
    )
    wrapper={
        "schema_version":"1.0","action":root.ACTION,
        "build_sha":build_sha,
        "manifest_sha256":root.MANIFEST_SHA,
        "scope_sha256":root.SCOPE_SHA,
        "signed_owner_proof":signed,
    }
    p=root.stage_dir(build_sha)/"owner-proof.json"
    root.root_file(p,root.canonical(wrapper)+b"\n",0o400,uid=1000)
    print("PMV4_E_ONE_OWNER_AUTHENTICATED_EXACT_SIGNATURE=VERIFIED")
    print("PRODUCTION_MUTATIONS=false; SIGNATURE_ONLY=true")


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    options=parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--check-only",action="store_true")
    options.add_argument("--approve",action="store_true")
    parser.add_argument("--build-sha",required=True)
    args=parser.parse_args(argv)
    if args.check_only:
        root,manifest,*_=exact_preflight(args.build_sha)
        print("PMV4_E_OWNER_UNPRIVILEGED_PREFLIGHT=PASS")
        print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
    else:
        approve(args.build_sha)


if __name__=="__main__":
    try:main()
    except (PermissionError,OSError,ValueError) as exc:
        print("PMV4_E_OWNER_DENIED:"+type(exc).__name__
              +(":"+str(exc)[:140] if isinstance(exc,PermissionError) else ""))
        raise SystemExit(2)
