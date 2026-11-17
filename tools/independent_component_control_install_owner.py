#!/usr/bin/env python3
"""Single exact Owner-signed installation consent. No production mutation."""
from __future__ import annotations

from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import time
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT_SOURCE = Path(__file__).resolve().with_name("independent_component_control_install_root.py")
ROOT_SPEC = importlib.util.spec_from_file_location("scoped_component_root_source", ROOT_SOURCE)
assert ROOT_SPEC is not None and ROOT_SPEC.loader is not None
scope = importlib.util.module_from_spec(ROOT_SPEC)
ROOT_SPEC.loader.exec_module(scope)

ISSUER = Path("/usr/local/lib/jason/owner_signed_release.py")
ISSUER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
CONFIRM = "APPROVE-INDEPENDENT-COMPONENT-CONTROLLER-INSTALL"

def pinned(path, digest, module_name):
    meta=path.lstat()
    scope.need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
               and meta.st_uid==0 and not (meta.st_mode & 0o022)
               and scope.digest(path.read_bytes())==digest,
               "OWNER_SIGNER_LIBRARY_CHANGED")
    spec=importlib.util.spec_from_file_location(module_name,path)
    x=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(x)
    return x

def preflight(directory):
    scope.need(os.geteuid()==1000,"OWNER_UID1000_REQUIRED")
    m, _=scope.load_stage(directory,with_proof=False)
    scope.need(not (directory/"owner-proof.json").exists(),
               "OWNER_APPROVAL_ALREADY_REQUESTED")
    scope.need(scope.digest(scope.FREEZE.read_bytes())==scope.FREEZE_HASH,
               "OWNER_FROZEN_BASELINE_CHANGED")
    # Avoid signing over a new active incident or an already-installed controller.
    scope.capture_protected()
    issuer=pinned(ISSUER,ISSUER_SHA,"owner_component_installer")
    auth=pinned(OAUTH,OAUTH_SHA,"oauth_component_installer")
    info=PRIVATE.lstat()
    scope.need(not PRIVATE.is_symlink() and stat.S_ISREG(info.st_mode)
               and info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o400
               and info.st_size==32, "OWNER_SIGNING_KEY_UNTRUSTED")
    key=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    public=issuer.read_pinned_root_owner_public_key(
        scope.OWNER_KEY,require_root_owned=True)
    scope.need(issuer.public_key_sha256(public)==
               issuer.public_key_sha256(key.public_key()),
               "OWNER_SIGNING_KEY_NOT_ROOT_PINNED")
    return m,issuer,auth,key

def authenticate(auth, m):
    endpoint=("https://login.microsoftonline.com/"+auth.TENANT+"/oauth2/v2.0/")
    device=auth._form(endpoint+"devicecode",{
        "client_id":auth.CLIENT_ID,"scope":auth.SCOPE})
    scope.need(all(isinstance(device.get(k),str) for k in
            ("device_code","verification_uri","user_code")),
            "OWNER_DEVICE_CODE_UNAVAILABLE")
    ttl=min(600,int(device.get("expires_in",0)))
    scope.need(ttl>=60,"OWNER_DEVICE_CODE_EXPIRED")
    print("ACTION="+scope.ACTION,flush=True)
    print("EXACT_SOURCE="+m["source_sha"],flush=True)
    print("EXACT_SCOPE_SHA256="+m["scope_sha256"],flush=True)
    print("NO_MCP_SWAP_OR_FINANCIAL_ACTIVATION=True",flush=True)
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
            decision=input("Type "+CONFIRM+" to authorize this exact action: ")
            scope.need(decision.strip()==CONFIRM,"OWNER_EXACT_APPROVAL_MISSING")
            return oid
        if token.get("error")=="slow_down":interval=min(20,interval+5)
        else:scope.need(token.get("error")=="authorization_pending",
                        "OWNER_AUTHENTICATION_DENIED")
        time.sleep(interval)
    raise scope.Denied("OWNER_APPROVAL_TIMEOUT")

def approve(directory):
    m,issuer,auth,key=preflight(directory)
    oid=authenticate(auth,m)
    principal=issuer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    scope.need(principal is not None,"OWNER_PRINCIPAL_NOT_PINNED")
    proof=issuer.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid.uuid4().hex,
        release_id="release-"+m["source_sha"][:16],
        candidate_sha=m["source_sha"],rollback_sha=scope.LKG,
        scope_sha256=m["scope_sha256"],
        manifest_sha256=scope.digest(scope.canonical(m)),
        freeze_sha256=scope.FREEZE_HASH,
        verified_tenant_id=issuer.TID, verified_owner_oid=oid,
        verified_principal=principal, verified_organization_id="aot",
        confirmed_decision="approve", at=datetime.now(timezone.utc),
        private_key=key)
    issuer.verify_exact_owner_release(
        proof,public_key=key.public_key(),
        expected_candidate_sha=m["source_sha"],expected_rollback_sha=scope.LKG,
        expected_release_id="release-"+m["source_sha"][:16],
        expected_scope_sha256=m["scope_sha256"],
        expected_manifest_sha256=scope.digest(scope.canonical(m)),
        expected_freeze_sha256=scope.FREEZE_HASH,at=datetime.now(timezone.utc))
    envelope={"schema_version":"1.0","action":scope.ACTION,
              "manifest_sha256":scope.digest(scope.canonical(m)),
              "signed_owner_proof":proof}
    fd=os.open(directory/"owner-proof.json",
               os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),
               0o400)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(envelope,sort_keys=True).encode()+b"\n")
        out.flush()
        os.fsync(out.fileno())
    print("OWNER_APPROVAL=EXACT_SIGNED_AND_VERIFIED")
    print("PRODUCTION_MUTATION=NONE")

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--packet",type=Path,required=True)
    a=ap.add_mutually_exclusive_group(required=True)
    a.add_argument("--check-only",action="store_true")
    a.add_argument("--approve",action="store_true")
    args=ap.parse_args()
    if args.check_only:
        m,*_=preflight(args.packet)
        print("OWNER_AUTH_ISSUER_PREFLIGHT=PASS")
        print("SOURCE_SHA="+m["source_sha"])
    else:approve(args.packet)

if __name__=="__main__":
    try: main()
    except (scope.Denied,OSError,ValueError) as exc:
        print("OWNER_COMPONENT_INSTALL=DENIED:"+str(exc)[:150])
        raise SystemExit(2)
