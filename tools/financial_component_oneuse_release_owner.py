#!/usr/bin/env python3
"""Sign a single exact 05:00 financial organizer promotion as authenticated Owner.

Runs only as UID 1000 with installed pinned signer. Does not write SharePoint
or run root, Docker, scheduler, MCP, PMv4, Release Manager or production files.
"""
from __future__ import annotations
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import time
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT_FILE=Path(__file__).resolve().with_name("financial_component_oneuse_release_root.py")
ROOT_SPEC=importlib.util.spec_from_file_location("financial_exact_scope",ROOT_FILE)
assert ROOT_SPEC is not None and ROOT_SPEC.loader is not None
root=importlib.util.module_from_spec(ROOT_SPEC)
ROOT_SPEC.loader.exec_module(root)
ISSUER=Path("/usr/local/lib/jason/owner_signed_release.py")
ISSUER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
CONFIRM="APPROVE-EXACT-05AM-FINANCIAL-STATEMENT-RELEASE"

def pinned_module(path,sha,name):
    meta=path.lstat()
    root.need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
              and meta.st_uid==0 and not (meta.st_mode&0o022)
              and root.digest(path.read_bytes())==sha,
              "FINANCIAL_OWNER_SIGNER_LIBRARY_DRIFT")
    spec=importlib.util.spec_from_file_location(name,path)
    root.need(spec is not None and spec.loader is not None,
              "FINANCIAL_OWNER_SIGNER_LIBRARY_MISSING")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def preflight():
    root.need(os.geteuid()==1000,"UID1000_OWNER_REQUIRED")
    root.need(not root.OWNER_PROOF.exists() and not root.OWNER_PROOF.is_symlink(),
              "FINANCIAL_OWNER_PROOF_ALREADY_ISSUED")
    manifest,files=root.exact_stage()
    root.need(root.digest(root.FREEZE.read_bytes())==root.FREEZE_SHA,
              "FINANCIAL_PRODUCTION_FREEZE_DRIFT")
    root.need(Path("/opt/jason/current").resolve(strict=True).name==root.LKG,
              "FINANCIAL_PRODUCTION_LKG_DRIFT")
    state=json.loads(root.PROTECTED_CONTROL.read_bytes())
    root.need(state.get("circuit_breaker",{}).get("state")=="closed",
              "FINANCIAL_PRODUCTION_BREAKER_OPEN")
    root.verify_image()
    root.acceptance_status()
    # There is no simulated CI PASS: query actual protected GitHub checks now.
    root.verified_ci()
    signer=pinned_module(ISSUER,ISSUER_SHA,"financial_owner_signer")
    auth=pinned_module(OAUTH,OAUTH_SHA,"financial_entra_auth")
    p=PRIVATE.lstat()
    root.need(not PRIVATE.is_symlink() and stat.S_ISREG(p.st_mode)
              and p.st_uid==1000 and stat.S_IMODE(p.st_mode)==0o400
              and p.st_size==32,"FINANCIAL_SIGNER_PRIVATE_KEY_UNTRUSTED")
    private=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    public=signer.read_pinned_root_owner_public_key(
        root.OWNER_PUB,require_root_owned=True)
    root.need(signer.public_key_sha256(public)==
              signer.public_key_sha256(private.public_key()),
              "FINANCIAL_OWNER_KEY_NOT_ROOT_PINNED")
    return manifest,signer,auth,private

def authenticate(auth,manifest):
    endpoint="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    device=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    root.need(all(isinstance(device.get(k),str) for k in (
        "device_code","user_code","verification_uri")),
        "ENTRA_FINANCIAL_OWNER_CHALLENGE_FAILED")
    ttl=min(600,int(device.get("expires_in",0)))
    root.need(ttl>=60,"ENTRA_FINANCIAL_OWNER_CHALLENGE_TOO_SHORT")
    print("EXACT_ACTION="+root.ACTION,flush=True)
    print("SOURCE_SHA="+root.SOURCE,flush=True)
    print("IMAGE_DIGEST="+root.IMAGE,flush=True)
    print("SCOPE_SHA256="+root.SCOPE_SHA,flush=True)
    print("SCHEDULE=05:00 America/New_York",flush=True)
    print("SHAREPOINT_SCOPE=AOT Accounting Documents only",flush=True)
    print("NO_QUICKBOOKS_WRITES_OR_PROTECTED_SERVICE_RESTARTS=True",flush=True)
    print("DEVICE_URL="+device["verification_uri"],flush=True)
    print("DEVICE_CODE="+device["user_code"],flush=True)
    deadline=time.monotonic()+ttl
    interval=max(5,min(20,int(device.get("interval",5))))
    while time.monotonic()<deadline:
        token=auth._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":device["device_code"]})
        if isinstance(token.get("access_token"),str):
            oid=auth.jwt_owner(token["access_token"])
            token=None
            typed=input("Type "+CONFIRM+" to approve this exact release: ")
            root.need(typed.strip()==CONFIRM,
                      "EXACT_FINANCIAL_OWNER_CONFIRMATION_MISSING")
            return oid
        if token.get("error")=="slow_down":
            interval=min(20,interval+5)
        else:
            root.need(token.get("error")=="authorization_pending",
                      "ENTRA_FINANCIAL_OWNER_REJECTED")
        time.sleep(interval)
    raise root.Denied("ENTRA_FINANCIAL_OWNER_CHALLENGE_EXPIRED")

def approve():
    manifest,signer,auth,private=preflight()
    oid=authenticate(auth,manifest)
    principal=signer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    root.need(principal is not None,"FINANCIAL_OWNER_PRINCIPAL_NOT_PINNED")
    signed=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id="release-"+root.SOURCE[:16],
        candidate_sha=root.SOURCE,
        rollback_sha=root.ZERO,
        scope_sha256=root.SCOPE_SHA,
        manifest_sha256=root.MANIFEST_SHA,
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,
        verified_owner_oid=oid,
        verified_principal=principal,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=private)
    signer.verify_exact_owner_release(
        signed,public_key=private.public_key(),
        expected_candidate_sha=root.SOURCE,
        expected_rollback_sha=root.ZERO,
        expected_release_id="release-"+root.SOURCE[:16],
        expected_scope_sha256=root.SCOPE_SHA,
        expected_manifest_sha256=root.MANIFEST_SHA,
        expected_freeze_sha256=root.FREEZE_SHA,
        at=datetime.now(timezone.utc))
    proof={
        "schema_version":"1.0","action":root.ACTION,
        "manifest_sha256":root.MANIFEST_SHA,
        "signed_owner_proof":signed,
    }
    fd=os.open(root.OWNER_PROOF,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(proof,sort_keys=True).encode()+b"\n")
        out.flush()
        os.fsync(out.fileno())
    print("EXACT_ENTRA_OWNER_RELEASE_SIGNATURE=VERIFIED")
    print("PRODUCTION_MUTATION=NOT_YET_PERFORMED")

def main():
    import argparse
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--approve",action="store_true")
    a=p.parse_args()
    if a.check_only:
        manifest,*_=preflight()
        print("FINANCIAL_SOURCE_IDENTITY_CI_PREFLIGHT=PASS")
        print("OWNER_SIGNATURE=NOT_REQUESTED")
    else:approve()

if __name__=="__main__":
    try: main()
    except (root.Denied,OSError,ValueError) as exc:
        print("FINANCIAL_OWNER_RELEASE_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:140] if isinstance(exc,root.Denied) else ""))
        raise SystemExit(2)
