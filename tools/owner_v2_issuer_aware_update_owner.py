#!/usr/bin/env python3
"""One-use UID1000 Owner Entra approval for EXACT two-root-file code/policy update.

No root writes, restarts, integrity scans, release activation or breaker changes.
Separate from the later four-SQLite live health-recovery consent.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

MERGE="7b42ce983896711525de4c7955bf9fc43ac003d0"
ROLLBACK="45e52de4803a6f0768187793bba4990ed1d11a07"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION="owner-v2-issuer-attested-root-code-policy-replace-v2-20261115"
SCOPE_SHA="6892f490c4632a95825240110ead9193ae1269d6624a70dbfe992b9a537ae22e"
MANIFEST_SHA="b1b3dd1c49d74ffc33597081d955d7b68341bdca9b504828b5ea822df39a6aca"
PACKAGE_SHA="db8fc31ec8dcdfce78fc602dffba36e856cd19c03c81265e90978ba6c1364135"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ARCHIVE=Path("/srv/jason/archive")
MANIFEST=ARCHIVE/("owner-v2-issuer-attested-v2-two-file-root-replace-audited-manifest-"+MERGE+".json")
PACKAGE=ARCHIVE/("owner-v2-issuer-attested-v2-two-file-root-replace-audited-"+MERGE+".tar")
PROOF=ARCHIVE/("owner-v2-issuer-attested-v2-two-file-root-replace-owner-proof-"+MERGE+".json")
OWNER_AUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_VERIFIER=Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_KEY=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
ROOT_PIN=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
LEDGER=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger")
ATTEMPT=Path("/etc/jason-owner-release/owner-v2-issuer-attested-v2-"+MERGE[:12]+".attempt.json")
RESULT=Path("/etc/jason-owner-release/owner-v2-issuer-attested-v2-"+MERGE[:12]+".result.json")
CONFIRM="AUTHORIZE-EXACT-ISSUER-LKG-CORRECTED-V2-ROOT-FILES-ONLY"

def digest(data:bytes)->str:
    return sha256(data).hexdigest()

def canon(obj:dict)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def trusted_module(path:Path,name:str):
    meta=path.lstat()
    if (path.is_symlink() or meta.st_uid!=0 or not stat.S_ISREG(meta.st_mode)
            or meta.st_mode & 0o022 or path.parent.lstat().st_uid!=0):
        raise PermissionError("ORIGINAL_ROOT_TRUSTED_OAUTH_OR_VERIFIER_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise PermissionError("TRUSTED_OWNER_MODULE_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def source_preflight():
    if os.geteuid()!=1000:
        raise PermissionError("OWNER_UID1000_REQUIRED")
    plan_bytes=MANIFEST.read_bytes()
    pkg_bytes=PACKAGE.read_bytes()
    if digest(plan_bytes)!=MANIFEST_SHA or digest(pkg_bytes)!=PACKAGE_SHA:
        raise PermissionError("ROOT_UPDATE_BUNDLE_OR_MANIFEST_HASH_DRIFT")
    plan=json.loads(plan_bytes)
    copy=dict(plan)
    if (copy.pop("scope_sha256",None)!=SCOPE_SHA
            or digest(canon(copy))!=SCOPE_SHA
            or plan.get("exact_action")!=ACTION
            or plan.get("reviewed_merged_main_sha")!=MERGE
            or plan.get("rollback_protected_main_sha")!=ROLLBACK
            or plan.get("production_lkg")!=LKG
            or plan.get("production_root_replacement_authorized") is not False
            or plan.get("no_full_integrity_scan") is not True
            or plan.get("no_unit_reload_or_restart") is not True
            or plan.get("no_breaker_override") is not True):
        raise PermissionError("ROOT_UPDATE_SCOPE_CHANGED")
    receipts=plan.get("immutable_root_audit_outputs") or {}
    if (receipts.get("root_attempt_path")!=str(ATTEMPT)
            or receipts.get("root_result_path")!=str(RESULT)
            or receipts.get("mode")!="0600"
            or receipts.get("root_owner_uid")!=0
            or receipts.get("root_owner_gid")!=0
            or receipts.get("parent_directory")!="/etc/jason-owner-release"
            or receipts.get("create_attempt_before_replacing_existing_root_files") is not True):
        raise PermissionError("EXACT_ROOT_AUDIT_RECEIPTS_SCOPE_CHANGED")
    rows=plan.get("exact_replacements",[])
    if len(rows)!=2 or {r["root_target"] for r in rows}!={
            "/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py",
            "/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json"}:
        raise PermissionError("TWO_FILES_EXACT_SCOPE_CHANGED")
    for row in rows:
        p=Path(row["root_target"])
        st=p.lstat()
        if (p.is_symlink() or st.st_uid!=0 or st.st_gid!=0
                or not stat.S_ISREG(st.st_mode)
                or stat.S_IMODE(st.st_mode)!=int(row["mode"],8)
                or st.st_nlink!=1):
            raise PermissionError("EXISTING_ROOT_FILE_NOT_TRUSTED")
        if row["mode"]=="0444" and digest(p.read_bytes())!=row["old_sha256"]:
            raise PermissionError("ORIGINAL_ROOT_HELPER_CHANGED")
        if row["mode"]=="0400" and row["old_sha256"]!="60db3c65211ea7af4cc467179038402151d7a8e29697f91f85db21181fbd4d16":
            raise PermissionError("ORIGINAL_ROOT_POLICY_HASH_CONTRACT_CHANGED")
    ls=LEDGER.lstat()
    if (LEDGER.is_symlink() or ls.st_uid!=0 or ls.st_gid!=0
            or not stat.S_ISDIR(ls.st_mode) or stat.S_IMODE(ls.st_mode)!=0o700):
        raise PermissionError("INITIAL_BOOTSTRAP_LEDGER_NOT_TRUSTED")
    if (digest(FREEZE.read_bytes())!=FREEZE_SHA
            or digest(HOLD.read_bytes())!=HOLD_SHA
            or Path("/opt/jason/current").resolve(strict=True).name!=LKG):
        raise PermissionError("PRODUCTION_LKG_FREEZE_OR_HOLD_CHANGED")
    if any(p.exists() or p.is_symlink() for p in (PROOF,ATTEMPT,RESULT)):
        raise PermissionError("ROOT_UPDATE_ONE_SHOT_ALREADY_ATTEMPTED")
    return plan

def authenticate_owner(helper)->str:
    endpoint="https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    challenge=helper._form(endpoint+"devicecode",{
        "client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(challenge.get(k),str) for k in (
            "device_code","user_code","verification_uri")):
        raise PermissionError("OWNER_DEVICE_CODE_UNAVAILABLE")
    expires=min(600,int(challenge.get("expires_in",0)))
    if expires<60:raise PermissionError("OWNER_DEVICE_CODE_EXPIRED")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+MERGE,flush=True)
    print("SCOPE_SHA256="+SCOPE_SHA,flush=True)
    print("NO_SERVICE_RESTART_NO_FULL_SQLITE_SCAN_NO_BREAKER_CHANGE=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    wait=max(5,min(20,int(challenge.get("interval",5))))
    until=time.monotonic()+expires
    while time.monotonic()<until:
        time.sleep(wait)
        token=helper._form(endpoint+"token",{
            "client_id":helper.CLIENT_ID,
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "device_code":challenge["device_code"],
        })
        if isinstance(token.get("access_token"),str):
            return helper.jwt_owner(token["access_token"])
        if token.get("error")=="slow_down":
            wait=min(20,wait+5)
        elif token.get("error")!="authorization_pending":
            raise PermissionError("OWNER_ENTRA_AUTHENTICATION_REFUSED")
    raise PermissionError("OWNER_ENTRA_LOGIN_EXPIRED")

def authorize():
    before=source_preflight()
    if not sys.stdin.isatty():
        raise PermissionError("OWNER_LOCAL_INTERACTIVE_TTY_REQUIRED")
    helper=trusted_module(OWNER_AUTH,"exact_v2_root_update_oauth")
    verifier=trusted_module(OWNER_VERIFIER,"exact_v2_root_update_signature")
    oid=authenticate_owner(helper)
    if oid not in verifier.EXACT_OWNER_OAUTH_SUBJECTS:
        raise PermissionError("NOT_VERIFIED_OWNER")
    if input("Authorize ONLY two root file replacements: "+CONFIRM+": ").strip()!=CONFIRM:
        raise PermissionError("EXACT_SCOPE_OWNER_CONFIRMATION_MISSING")
    if source_preflight()!=before:
        raise PermissionError("PRODUCTION_DRIFT_AFTER_OWNER_LOGIN")
    private=verifier.read_service_owner_signing_key(OWNER_KEY)
    public=verifier.read_pinned_root_owner_public_key(ROOT_PIN,require_root_owned=True)
    if verifier.public_key_sha256(private.public_key())!=verifier.public_key_sha256(public):
        raise PermissionError("ROOT_PINNED_OWNER_ED25519_KEY_MISMATCH")
    now=datetime.now(timezone.utc)
    signed=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid.uuid4().hex,
        release_id="release-"+MERGE[:16],
        candidate_sha=MERGE,rollback_sha=ROLLBACK,
        scope_sha256=SCOPE_SHA,manifest_sha256=MANIFEST_SHA,
        freeze_sha256=FREEZE_SHA,verified_tenant_id=verifier.TID,
        verified_owner_oid=oid,verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot",confirmed_decision="approve",
        at=now,private_key=private,
    )
    verifier.verify_exact_owner_release(
        signed,public_key=public,at=now,
        expected_candidate_sha=MERGE,expected_rollback_sha=ROLLBACK,
        expected_release_id="release-"+MERGE[:16],
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=MANIFEST_SHA,
        expected_freeze_sha256=FREEZE_SHA,
    )
    decision={
        "schema_version":"1.0","exact_action":ACTION,
        "source_sha":MERGE,"rollback_sha":ROLLBACK,
        "scope_sha256":SCOPE_SHA,"manifest_sha256":MANIFEST_SHA,
        "package_sha256":PACKAGE_SHA,
        "status":"OWNER_APPROVED_NOT_APPLIED",
        "signed_owner_proof":signed,
    }
    binary=canon(decision)+b"\n"
    fd=os.open(PROOF,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchmod(fd,0o600)
        if os.write(fd,binary)!=len(binary):
            raise OSError("SHORT_OWNER_AUDIT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    print("EXACT_UID1000_OWNER_SIGNED_APPROVAL=RECORDED")
    print("OWNER_PROOF_SHA256="+digest(PROOF.read_bytes()))
    print("PRODUCTION_ROOT_REPLACED=false")

def main()->int:
    try:
        if sys.argv[1:]==["--check-only"]:
            source_preflight()
            print("EXACT_OWNER_ROOT_UPGRADE_PREFLIGHT=PASS")
            print("LIVE_ROOT_REPLACEMENT_OCCURRED=false")
        elif sys.argv[1:]==["--authorize"]:
            authorize()
        else:
            raise PermissionError("UNREVIEWED_ACTION_DENIED")
        return 0
    except Exception as exc:
        print("V2_ROOT_UPGRADE_OWNER_AUTH=DENIED "+
              type(exc).__name__+":"+
              (str(exc)[:125] if isinstance(exc,PermissionError)
               else "SENSITIVE_DETAILS_REDACTED"),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
