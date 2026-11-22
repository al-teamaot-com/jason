#!/usr/bin/env python3
"""Entra Owner signature for exact independent financial-container policy delta."""
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

SCOPED=Path(__file__).resolve().with_name("financial_container_policy_reconcile_root.py")
spec=importlib.util.spec_from_file_location("financial_container_policy_scope",SCOPED)
assert spec and spec.loader
root=importlib.util.module_from_spec(spec)
spec.loader.exec_module(root)

SIGNER=root.SIGNER
SIGNER_SHA=root.SIGNER_SHA
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
CONFIRM="APPROVE-EXACT-FINANCIAL-CONTAINER-POLICY"

def trusted(path,sha,name):
    info=path.lstat()
    root.need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
              and info.st_uid==0 and not (info.st_mode&0o022)
              and root.digest(path.read_bytes())==sha,
              "FINANCIAL_POLICY_OWNER_PINNED_SIGNER_DRIFT")
    mod=importlib.util.spec_from_file_location(name,path)
    root.need(mod is not None and mod.loader is not None,
              "FINANCIAL_POLICY_OWNER_SIGNER_MISSING")
    obj=importlib.util.module_from_spec(mod)
    mod.loader.exec_module(obj)
    return obj

def preflight(packet):
    root.need(os.geteuid()==1000,"FINANCIAL_POLICY_OWNER_UID1000_REQUIRED")
    manifest,_=root.stage(packet,with_proof=False)
    root.need(not (packet/root.OWNER_FILE).exists(),
              "FINANCIAL_POLICY_OWNER_PROOF_ALREADY_CREATED")
    root.need(root.digest(root.FREEZE.read_bytes())==root.FREEZE_SHA
              and Path("/opt/jason/current").resolve(strict=True).name==root.LKG,
              "FINANCIAL_POLICY_OWNER_FREEZE_OR_LKG_CHANGED")
    signer=trusted(SIGNER,SIGNER_SHA,"financial_policy_signer")
    auth=trusted(OAUTH,OAUTH_SHA,"financial_policy_auth")
    info=PRIVATE.lstat()
    root.need(not PRIVATE.is_symlink() and stat.S_ISREG(info.st_mode)
              and info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o400
              and info.st_size==32,
              "FINANCIAL_POLICY_OWNER_PRIVATE_KEY_UNTRUSTED")
    private=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    pub=signer.read_pinned_root_owner_public_key(
        root.PUBLIC,require_root_owned=True)
    root.need(signer.public_key_sha256(pub)==
              signer.public_key_sha256(private.public_key()),
              "FINANCIAL_POLICY_OWNER_KEY_NOT_ROOT_PINNED")
    return manifest,signer,auth,private

def authenticate(auth,manifest):
    endpoint="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    device=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    root.need(all(isinstance(device.get(k),str) for k in
              ("device_code","user_code","verification_uri")),
              "FINANCIAL_POLICY_OWNER_DEVICE_CODE_UNAVAILABLE")
    ttl=min(600,int(device.get("expires_in",0)))
    root.need(ttl>=60,"FINANCIAL_POLICY_OWNER_CHALLENGE_TOO_SHORT")
    print("ACTION="+root.ACTION,flush=True)
    print("EXACT_SOURCE="+manifest["source_sha"],flush=True)
    print("EXACT_SCOPE_SHA256="+manifest["scope_sha256"],flush=True)
    print("ADD_ONLY="+root.NAME+" to root-owned allowed running containers",flush=True)
    print("NO_RUNTIME_OR_MCP_RESTARTS=True",flush=True)
    print("NO_FINANCIAL_SERVICE_ACTIVATION=True",flush=True)
    print("NO_FREEZE_OR_PROVIDER_MUTATION=True",flush=True)
    print("BROWSER_VERIFICATION_URL="+device["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+device["user_code"],flush=True)
    stop=time.monotonic()+ttl
    interval=max(5,min(20,int(device.get("interval",5))))
    while time.monotonic()<stop:
        response=auth._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":device["device_code"]})
        if isinstance(response.get("access_token"),str):
            oid=auth.jwt_owner(response["access_token"])
            response=None
            typed=input("Type "+CONFIRM+" to authorize exactly this root policy: ")
            root.need(typed.strip()==CONFIRM,
                      "FINANCIAL_POLICY_OWNER_EXACT_CONSENT_MISSING")
            return oid
        if response.get("error")=="slow_down":
            interval=min(20,interval+5)
        else:
            root.need(response.get("error")=="authorization_pending",
                      "FINANCIAL_POLICY_OWNER_ENTRA_DENIED")
        time.sleep(interval)
    raise root.Denied("FINANCIAL_POLICY_OWNER_CHALLENGE_EXPIRED")

def approve(packet):
    manifest,signer,auth,private=preflight(packet)
    oid=authenticate(auth,manifest)
    principal=signer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    root.need(principal is not None,"FINANCIAL_POLICY_OWNER_NOT_PINNED")
    proof=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id="release-"+manifest["source_sha"][:16],
        candidate_sha=manifest["source_sha"],rollback_sha=root.LKG,
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=root.digest(root.canonical(manifest)),
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,verified_owner_oid=oid,
        verified_principal=principal,verified_organization_id="aot",
        confirmed_decision="approve",at=datetime.now(timezone.utc),
        private_key=private)
    signer.verify_exact_owner_release(
        proof,public_key=private.public_key(),
        expected_candidate_sha=manifest["source_sha"],
        expected_rollback_sha=root.LKG,
        expected_release_id="release-"+manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=root.digest(root.canonical(manifest)),
        expected_freeze_sha256=root.FREEZE_SHA,
        at=datetime.now(timezone.utc))
    wrapper={
        "schema_version":"1.0","action":root.ACTION,
        "manifest_sha256":root.digest(root.canonical(manifest)),
        "signed_owner_proof":proof,
    }
    dest=packet/root.OWNER_FILE
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(wrapper,sort_keys=True).encode()+b"\n")
        out.flush();os.fsync(out.fileno())
    print("FINANCIAL_POLICY_SIGNED_OWNER_PROOF=VERIFIED")
    print("ROOT_POLICY_MUTATIONS=NOT_PERFORMED")

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--packet",type=Path,required=True)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--approve",action="store_true")
    a=p.parse_args()
    if a.check_only:
        preflight(a.packet)
        print("FINANCIAL_POLICY_OWNER_AND_SOURCE_PREFLIGHT=PASS")
        print("ROOT_POLICY_MUTATIONS=NOT_PERFORMED")
    else:approve(a.packet)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FINANCIAL_POLICY_OWNER_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:140] if isinstance(exc,root.Denied)
               else ":DETAILS_REDACTED"))
        raise SystemExit(2)
