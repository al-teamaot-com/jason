#!/usr/bin/env python3
"""Owner-only UID1000 Entra approval for fixed V2 four-DB health recovery.

Runs before and separately from the root action. Signs one 15-minute
exact-policy approval with the AL-OWNED 0400 key; never runs as root,
executes systemd, scans databases, or changes production.
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
import sys
import time
import uuid

ACTION="owner-full-integrity-v2-bounded-repair-20261113"
SOURCE="95832507e6e5f804f092cb5d3ebdea90ba1a49bf"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
SCOPE="8267a53e7c532125a8cf8df316c1f71da6eecdb7c8e34536c298119816e483fe"
BUNDLE_SHA="f39065a9c98da1fd8900c93f41965b84125129507b527d1e3287ef68e3e5c6d0"
BUNDLE_MANIFEST_SHA="c05bed1594d4eec79a47e02ec2a4c677f5772bc9ab92f173ad574708b7fcdf63"
ROOT_POLICY_SHA="611b244096fdf826680e4a1194abe6ad8ca3ab6132f4e7b6aa08ba70ec016c6f"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ARCHIVE=Path("/srv/jason/archive")
REVIEWED_POLICY=ARCHIVE/"owner-full-integrity-v2-reviewed-upgrade-policy-20261113.json"
ROOT_POLICY=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json")
ROOT_HELPER=Path("/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py")
LEDGER=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger")
OWNER_AUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_VERIFIER=Path("/usr/local/lib/jason/owner_signed_release.py")
SIGNER=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
ROOT_PIN=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
BUNDLE=ARCHIVE/("owner-full-integrity-v2-repair-source-"+SOURCE+".tar")
BUNDLE_MANIFEST=ARCHIVE/("owner-full-integrity-v2-repair-manifest-"+SOURCE+".json")
PROOF=ARCHIVE/"owner-full-integrity-v2-signed-owner-decision-20261113.json"
CONFIRM="AUTHORIZE-EXACT-V2-FOUR-SQLITE-HEALTH-RECOVERY-ONLY"

def digest(raw:bytes)->str:
    return sha256(raw).hexdigest()

def canonical(data:dict)->bytes:
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def load_trusted(p:Path,name:str):
    meta=p.lstat()
    if (p.is_symlink() or meta.st_uid!=0 or meta.st_mode & 0o022
            or not stat.S_ISREG(meta.st_mode)
            or p.parent.lstat().st_uid!=0):
        raise PermissionError("PINNED_OWNER_MODULE_UNTRUSTED")
    spec=importlib.util.spec_from_file_location(name,str(p))
    if spec is None or spec.loader is None:
        raise PermissionError("PINNED_OWNER_MODULE_UNAVAILABLE")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def preflight(*, require_root_upgrade:bool)->dict:
    if os.geteuid()!=1000:
        raise PermissionError("OWNER_UID1000_INTERACTIVE_CONSENT_REQUIRED")
    if not isinstance(ROOT_POLICY_SHA,str) or len(ROOT_POLICY_SHA)!=64:
        raise PermissionError("REVIEWED_POLICY_HASH_NOT_PINNED")
    if (digest(REVIEWED_POLICY.read_bytes())!=ROOT_POLICY_SHA
            or digest(BUNDLE.read_bytes())!=BUNDLE_SHA
            or digest(BUNDLE_MANIFEST.read_bytes())!=BUNDLE_MANIFEST_SHA):
        raise PermissionError("REVIEWED_POLICY_OR_HEALTH_PACKAGE_DRIFT")
    policy=json.loads(REVIEWED_POLICY.read_bytes())
    if (policy.get("schema_version")!="1.0"
            or policy.get("exact_action")!=ACTION
            or policy.get("source_sha")!=SOURCE
            or policy.get("production_lkg")!=LKG
            or policy.get("scope_sha256")!=SCOPE
            or policy.get("bundle_sha256")!=BUNDLE_SHA
            or policy.get("manifest_sha256")!=BUNDLE_MANIFEST_SHA
            or policy.get("freeze_sha256")!=FREEZE_SHA
            or policy.get("promotion_hold_sha256")!=HOLD_SHA
            or policy.get("one_shot") is not True
            or policy.get("no_provider_writes") is not True
            or policy.get("no_runtime_change") is not True):
        raise PermissionError("REVIEWED_EXACT_ACTION_POLICY_DRIFT")
    if (digest(FREEZE.read_bytes())!=FREEZE_SHA
            or digest(HOLD.read_bytes())!=HOLD_SHA
            or Path("/opt/jason/current").resolve(strict=True).name!=LKG):
        raise PermissionError("LKG_OR_FREEZE_CHANGED")
    if PROOF.exists() or PROOF.is_symlink():
        raise PermissionError("SIGNED_OWNER_APPROVAL_ALREADY_EXISTS")
    if require_root_upgrade:
        info=ROOT_HELPER.lstat()
        if (info.st_uid!=0 or info.st_gid!=0
                or stat.S_IMODE(info.st_mode)!=0o444
                or digest(ROOT_HELPER.read_bytes())!=policy["script_sha256"]):
            raise PermissionError("ROOT_HELPER_CODE_NOT_UPDATED_AND_VERIFIED")
        # Root policy is intentionally unreadable at UID1000; root independent
        # executor MUST compare its exact bytes to the signed policy SHA.
        if ROOT_POLICY.is_symlink():
            raise PermissionError("ROOT_POLICY_LINK_UNSAFE")
        info=ROOT_POLICY.lstat()
        if (info.st_uid!=0 or info.st_gid!=0
                or stat.S_IMODE(info.st_mode)!=0o400):
            raise PermissionError("ROOT_POLICY_NOT_SECURE")
        # The root bootstrap previously created an *occupied* root-only
        # ledger. UID1000 must not try to list that 0700 directory or clear
        # its audit records; the root helper verifies the original records
        # and distinct new action filenames under its own privileged gate.
        info=LEDGER.lstat()
        if (LEDGER.is_symlink() or info.st_uid!=0 or info.st_gid!=0
                or stat.S_IMODE(info.st_mode)!=0o700):
            raise PermissionError("ROOT_AUDIT_LEDGER_NOT_SECURE")
        if PROOF.exists():
            raise PermissionError("OWNER_ONE_SHOT_PROOF_ALREADY_ISSUED")
    return policy

def oauth(helper)->str:
    endpoint="https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    challenge=helper._form(endpoint+"devicecode",{
        "client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(challenge.get(k),str) for k in (
        "device_code","user_code","verification_uri")):
        raise PermissionError("OWNER_DEVICE_CODE_NOT_AVAILABLE")
    expires=min(600,int(challenge.get("expires_in",0)))
    if expires<60:raise PermissionError("OWNER_DEVICE_CODE_EXPIRED")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("EXACT_ROOT_POLICY_SHA256="+ROOT_POLICY_SHA,flush=True)
    print("REVIEWED_THREE_OBJECT_SCOPE_SHA256="+SCOPE,flush=True)
    print("NO_RUNTIME_MCP_OR_TICKET_RESTART=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    deadline=time.monotonic()+expires
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<deadline:
        time.sleep(interval)
        token=helper._form(endpoint+"token",{
           "client_id":helper.CLIENT_ID,
           "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
           "device_code":challenge["device_code"],
        })
        if isinstance(token.get("access_token"),str):
            return helper.jwt_owner(token["access_token"])
        status=token.get("error")
        if status=="slow_down":interval=min(20,interval+5)
        elif status!="authorization_pending":
            raise PermissionError("OWNER_OAUTH_NOT_APPROVED")
    raise PermissionError("OWNER_OAUTH_EXPIRED")

def issue():
    policy=preflight(require_root_upgrade=True)
    if not sys.stdin.isatty():
        raise PermissionError("OWNER_AUTHENTICATED_LOCAL_TTY_REQUIRED")
    helper=load_trusted(OWNER_AUTH,"v2_uid1000_owner_oauth")
    verifier=load_trusted(OWNER_VERIFIER,"v2_uid1000_owner_signer")
    oid=oauth(helper)
    if oid not in verifier.EXACT_OWNER_OAUTH_SUBJECTS:
        raise PermissionError("NOT_VERIFIED_AOT_OWNER")
    if input("Confirm exact action with "+CONFIRM+": ").strip()!=CONFIRM:
        raise PermissionError("EXACT_OWNER_CONFIRMATION_MISSING")
    if preflight(require_root_upgrade=True)!=policy:
        raise PermissionError("PRODUCTION_OR_OWNER_POLICY_DRIFT_AFTER_AUTH")
    key=verifier.read_service_owner_signing_key(SIGNER)
    pub=verifier.read_pinned_root_owner_public_key(ROOT_PIN,require_root_owned=True)
    if verifier.public_key_sha256(key.public_key())!=verifier.public_key_sha256(pub):
        raise PermissionError("PINNED_OWNER_KEY_MISMATCH")
    now=datetime.now(timezone.utc)
    signed=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid.uuid4().hex,
        release_id="release-"+SOURCE[:16],
        candidate_sha=SOURCE,rollback_sha=LKG,
        scope_sha256=SCOPE,
        # Exact root-policy content binds the revised trusted helper bytes,
        # rather than the original source-only three-object data manifest.
        manifest_sha256=ROOT_POLICY_SHA,
        freeze_sha256=FREEZE_SHA,
        verified_tenant_id=verifier.TID,verified_owner_oid=oid,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot",confirmed_decision="approve",
        at=now,private_key=key)
    verifier.verify_exact_owner_release(
        signed,public_key=pub,at=now,
        expected_candidate_sha=SOURCE,expected_rollback_sha=LKG,
        expected_release_id="release-"+SOURCE[:16],
        expected_scope_sha256=SCOPE,
        expected_manifest_sha256=ROOT_POLICY_SHA,
        expected_freeze_sha256=FREEZE_SHA)
    envelope={
        "schema_version":"1.0","action":ACTION,
        "source_sha":SOURCE,"scope_sha256":SCOPE,
        "bundle_sha256":BUNDLE_SHA,"root_policy_sha256":ROOT_POLICY_SHA,
        "status":"AUTHENTICATED_OWNER_APPROVED_NOT_EXECUTED",
        "signed_owner_proof":signed,
    }
    data=canonical(envelope)+b"\n"
    fd=os.open(PROOF,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchmod(fd,0o600)
        if os.write(fd,data)!=len(data):
            raise OSError("OWNER_PROOF_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    print("FRESH_OWNER_SIGNED_V2_HEALTH_DECISION=RECORDED")
    print("OWNER_PROOF_SHA256="+digest(PROOF.read_bytes()))
    print("LIVE_FULL_INTEGRITY_SCAN_STARTED=false")
    return 0

def main():
    args=argparse.ArgumentParser()
    mode=args.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source-check-only",action="store_true")
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--authorize",action="store_true")
    ns=args.parse_args()
    try:
        if ns.source_check_only:
            preflight(require_root_upgrade=False)
            print("SOURCE_OWNER_PROOF_PREPARATION=PASS")
            print("FRESH_OWNER_DECISION_ISSUED=false")
        elif ns.check_only:
            preflight(require_root_upgrade=True)
            print("ROOT_UPGRADED_OWNER_PROOF_PREFLIGHT=PASS")
            print("FRESH_OWNER_DECISION_ISSUED=false")
        else:
            return issue()
        return 0
    except Exception as exc:
        print("EXACT_V2_OWNER_SIGNED_PROOF=DENIED "+
              type(exc).__name__+":"+
              (str(exc)[:125] if isinstance(exc,PermissionError)
               else "SENSITIVE_DETAILS_REDACTED"),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
