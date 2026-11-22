#!/usr/bin/env python3
"""One exact 15-minute Entra Owner signature for idle catalog-unit reconciliation.

Unprivileged UID-1000 step only. Root action requires an independent public-key
verification of the exact signed manifest. Never grants catalog promotion.
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

SCOPED=Path(__file__).resolve().with_name("catalog_recovery_units_reconcile_root.py")
spec=importlib.util.spec_from_file_location("catalog_unit_owner_scope",SCOPED)
assert spec and spec.loader
root=importlib.util.module_from_spec(spec)
spec.loader.exec_module(root)

SIGNER=root.SIGNER
SIGNER_SHA=root.SIGNER_SHA
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUBLIC=root.ROOT_OWNER
CONFIRM="APPROVE-EXACT-IDLE-CATALOG-RECOVERY-UNIT-RECONCILE"

def trusted(path, sha, name):
    s=path.lstat()
    root.need(not path.is_symlink() and stat.S_ISREG(s.st_mode)
              and s.st_uid==0 and not (s.st_mode&0o022)
              and root.digest(path.read_bytes())==sha,
              "OWNER_RECONCILE_PINNED_SIGNER_DRIFT")
    mod=importlib.util.spec_from_file_location(name,path)
    root.need(mod is not None and mod.loader is not None,
              "OWNER_RECONCILE_SIGNER_UNAVAILABLE")
    obj=importlib.util.module_from_spec(mod)
    mod.loader.exec_module(obj)
    return obj

def preflight(packet):
    root.need(os.geteuid()==1000,"OWNER_RECONCILE_UID1000_REQUIRED")
    manifest,_=root.stage(packet,require_proof=False)
    root.need(not (packet/"owner-proof.json").exists(),
              "OWNER_RECONCILE_ALREADY_SIGNED")
    root.need(root.digest(root.FREEZE.read_bytes())==root.FREEZE_SHA
              and root.digest(root.DESIRED.read_bytes())==root.DESIRED_SHA,
              "OWNER_RECONCILE_FROZEN_POLICY_CHANGED")
    root.need(Path("/opt/jason/current").resolve(strict=True).name==root.LKG,
              "OWNER_RECONCILE_ROOT_LKG_CHANGED")
    control=json.loads(root.CONTROL.read_bytes())
    drift=json.loads(root.DRIFT.read_bytes())
    root.need(control.get("circuit_breaker",{}).get("state")=="open"
              and drift.get("status")=="drift_detected"
              and set(x.get("unit") for x in drift.get("problems",[]))==set(root.UNITS),
              "OWNER_RECONCILE_INCIDENT_NOT_EXACT")
    signer=trusted(SIGNER,SIGNER_SHA,"catalog_unit_signer")
    auth=trusted(OAUTH,OAUTH_SHA,"catalog_unit_oauth")
    p=PRIVATE.lstat()
    root.need(not PRIVATE.is_symlink() and stat.S_ISREG(p.st_mode)
              and p.st_uid==1000 and stat.S_IMODE(p.st_mode)==0o400
              and p.st_size==32, "OWNER_RECONCILE_PRIVATE_KEY_UNTRUSTED")
    key=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    pub=signer.read_pinned_root_owner_public_key(
        PUBLIC,require_root_owned=True)
    root.need(signer.public_key_sha256(key.public_key())==
              signer.public_key_sha256(pub),
              "OWNER_RECONCILE_KEY_PIN_MISMATCH")
    return manifest,signer,auth,key

def authenticate(auth, manifest):
    url="https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/"
    device=auth._form(url+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    root.need(all(isinstance(device.get(k),str) for k in
             ("device_code","user_code","verification_uri")),
             "OWNER_RECONCILE_ENTRA_DEVICE_UNAVAILABLE")
    ttl=min(600,int(device.get("expires_in",0)))
    root.need(ttl>=60,"OWNER_RECONCILE_ENTRA_CHALLENGE_TOO_SHORT")
    print("EXACT_ACTION="+root.ACTION,flush=True)
    print("SOURCE_SHA="+manifest["source_sha"],flush=True)
    print("SCOPE_SHA256="+manifest["scope_sha256"],flush=True)
    print("REMOVE_ONLY=4 undeclared idle catalog recovery systemd units",flush=True)
    print("CATALOG_ROOT_CONTROL_RETAINED=TRUE",flush=True)
    print("CATALOG_PROMOTIONS_SUSPENDED_UNTIL_PROPER_RELEASE=TRUE",flush=True)
    print("PRODUCTION_FREEZE_AND_ALL_CONTAINERS_UNCHANGED=TRUE",flush=True)
    print("BROWSER_VERIFICATION_URL="+device["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+device["user_code"],flush=True)
    deadline=time.monotonic()+ttl
    interval=max(5,min(20,int(device.get("interval",5))))
    while time.monotonic()<deadline:
        response=auth._form(url+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":auth.CLIENT_ID,
            "device_code":device["device_code"]})
        if isinstance(response.get("access_token"),str):
            oid=auth.jwt_owner(response["access_token"])
            response=None
            choice=input("Type "+CONFIRM+" to authorize this exact action: ")
            root.need(choice.strip()==CONFIRM,
                      "OWNER_RECONCILE_EXACT_CONSENT_MISSING")
            return oid
        if response.get("error")=="slow_down":
            interval=min(20,interval+5)
        else:
            root.need(response.get("error")=="authorization_pending",
                      "OWNER_RECONCILE_ENTRA_AUTH_FAILED")
        time.sleep(interval)
    raise root.Denied("OWNER_RECONCILE_ENTRA_CHALLENGE_EXPIRED")

def approve(packet):
    manifest,signer,auth,private=preflight(packet)
    oid=authenticate(auth,manifest)
    principal=signer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    root.need(principal is not None,"OWNER_RECONCILE_SUBJECT_NOT_PINNED")
    signed=signer.issue_exact_owner_release(
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
        signed,public_key=private.public_key(),
        expected_candidate_sha=manifest["source_sha"],
        expected_rollback_sha=root.LKG,
        expected_release_id="release-"+manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=root.digest(root.canonical(manifest)),
        expected_freeze_sha256=root.FREEZE_SHA,
        at=datetime.now(timezone.utc))
    wrapper={"schema_version":"1.0","action":root.ACTION,
             "manifest_sha256":root.digest(root.canonical(manifest)),
             "signed_owner_proof":signed}
    path=packet/"owner-proof.json"
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(wrapper,sort_keys=True).encode()+b"\n")
        out.flush();os.fsync(out.fileno())
    print("ENTRA_OWNER_EXACT_PROOF=VERIFIED")
    print("ROOT_AND_SYSTEMD_MUTATIONS=NOT_PERFORMED")

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--packet",type=Path,required=True)
    flags=parser.add_mutually_exclusive_group(required=True)
    flags.add_argument("--check-only",action="store_true")
    flags.add_argument("--approve",action="store_true")
    args=parser.parse_args()
    if args.check_only:
        manifest,*_=preflight(args.packet)
        print("OWNER_SIGNER_SOURCE_AND_INCIDENT_PREFLIGHT=PASS")
        print("ROOT_AND_SYSTEMD_MUTATIONS=NOT_PERFORMED")
    else:approve(args.packet)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CATALOG_UNIT_RECONCILE_OWNER_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:130] if isinstance(exc,root.Denied)
               else ":DETAILS_REDACTED"))
        raise SystemExit(2)
