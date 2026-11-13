#!/usr/bin/env python3
"""One-use, exact Owner-governed *future* production SQLite health recovery.

SOURCE ONLY: this module cannot install itself or run from a mutable worktree.
A separate exact-action Owner approval and trusted root installation are needed.
No generic shell, provider mutation, deployment, or permanent elevated agent.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import time
import uuid

SOURCE = "95832507e6e5f804f092cb5d3ebdea90ba1a49bf"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION = "owner-full-integrity-v2-bounded-repair-20261113"
ROOT_SCRIPT = Path("/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py")
POLICY = Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json")
LEDGER = Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger")
BUNDLE = Path("/srv/jason/archive/owner-full-integrity-v2-repair-source-" + SOURCE + ".tar")
MANIFEST = Path("/srv/jason/archive/owner-full-integrity-v2-repair-manifest-" + SOURCE + ".json")
ROOT_SOURCE = Path("/usr/local/lib/jason/authority-health-v2-" + SOURCE[:12])
FULL_UNIT = Path("/etc/systemd/system/jason-openclaw-authority-full-integrity.service")
FAST_UNIT = Path("/etc/systemd/system/jason-openclaw-authority-health.service")
FULL_DROPIN_DIR = Path("/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d")
FULL_DROPIN = FULL_DROPIN_DIR / "91-owner-full-proof-v2.conf"
FAST_EMERGENCY = Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/91-owner-emergency-full-proof-degraded.conf")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
FAST = Path("/var/lib/jason/openclaw/operational-health.json")
ROOT_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
OWNER_AUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_PROOF = Path("/usr/local/lib/jason/owner_signed_release.py")
RUNTIME = "jason-runtime"
MCP = "jason-mcp-pilot"
CONFIRM = "APPROVE-EXACT-V2-FULL-SQLITE-PROOF-ONLY"

class RepairDenied(PermissionError):
    pass

def digest(data: bytes) -> str:
    return sha256(data).hexdigest()

def canonical(obj: dict) -> bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def read_secure_root(path: Path, maximum: int = 1024 * 1024) -> bytes:
    parent=path.parent.lstat()
    if (path.is_symlink() or path.parent.is_symlink() or parent.st_uid!=0
            or parent.st_mode & 0o022 or not stat.S_ISDIR(parent.st_mode)):
        raise RepairDenied("UNTRUSTED_ROOT_PARENT")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
                or info.st_mode & 0o022 or info.st_nlink!=1
                or info.st_size > maximum):
            raise RepairDenied("UNTRUSTED_ROOT_OBJECT")
        data=os.read(fd,maximum+1)
        if len(data)!=info.st_size:
            raise RepairDenied("ROOT_FILE_CHANGED_DURING_READ")
        return data
    finally:
        os.close(fd)

def protected_release_record(path: Path) -> dict:
    # Protected root record intentionally lives in al-owned 0700 release
    # directory. Its inode itself is root-owned and non-writable.
    parent=path.parent.lstat()
    if (path.is_symlink() or path.parent.is_symlink()
            or parent.st_uid!=1000 or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode)!=0o700):
        raise RepairDenied("PROTECTED_RELEASE_PARENT_UNTRUSTED")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
                or info.st_nlink!=1 or info.st_mode & 0o022
                or info.st_size>100*1024):
            raise RepairDenied("PROTECTED_RELEASE_ROOT_RECORD_UNTRUSTED")
        raw=os.read(fd,100*1024+1)
        if len(raw)!=info.st_size:
            raise RepairDenied("PROTECTED_RELEASE_RECORD_CHANGED")
        return json.loads(raw)
    finally:
        os.close(fd)


def load_trust(path: Path, name: str):
    read_secure_root(path)
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        raise RepairDenied("TRUSTED_LIBRARY_LOAD_DENIED")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def fixed_policy() -> dict:
    document=json.loads(read_secure_root(POLICY,32*1024))
    required={"schema_version","exact_action","one_shot","source_sha",
              "production_lkg","script_sha256","bundle_sha256","manifest_sha256",
              "scope_sha256","freeze_sha256","promotion_hold_sha256",
              "runtime_image_id","mcp_image_id","owner_auth_sha256",
              "owner_proof_sha256","full_unit_sha256","fast_unit_sha256",
              "old_fast_emergency_sha256","service_max_seconds",
              "full_scan_max_seconds","no_provider_writes","no_runtime_change"}
    if (set(document)!=required or document["schema_version"]!="1.0"
            or document["exact_action"]!=ACTION or document["one_shot"] is not True
            or document["source_sha"]!=SOURCE
            or document["production_lkg"]!=LKG
            or document["service_max_seconds"]!=5700
            or document["full_scan_max_seconds"]!=5400
            or document["no_provider_writes"] is not True
            or document["no_runtime_change"] is not True):
        raise RepairDenied("POLICY_CONTRACT_CHANGED")
    for field,file in (
        ("script_sha256",ROOT_SCRIPT),("owner_auth_sha256",OWNER_AUTH),
        ("owner_proof_sha256",OWNER_PROOF),
        ("full_unit_sha256",FULL_UNIT),("fast_unit_sha256",FAST_UNIT),
        ("old_fast_emergency_sha256",FAST_EMERGENCY),
        ("owner_auth_sha256",OWNER_AUTH),
        ("owner_proof_sha256",OWNER_PROOF),
    ):
        if document[field]!=digest(read_secure_root(file)):
            raise RepairDenied("PINNED_ROOT_FILE_CHANGED:"+field)
    return document

def checked_bundle(policy: dict) -> tuple[dict,dict[str,bytes]]:
    # Bundle resides in an untrusted al-owned archive. Hashes and archive
    # members, not the path's ownership or its JSON fields, are authoritative.
    if BUNDLE.is_symlink() or MANIFEST.is_symlink():
        raise RepairDenied("BUNDLE_SYMLINK")
    if BUNDLE.stat().st_size > 2*1024*1024 or MANIFEST.stat().st_size>32768:
        raise RepairDenied("BUNDLE_TOO_LARGE")
    binary=BUNDLE.read_bytes()
    raw_manifest=MANIFEST.read_bytes()
    if (digest(binary)!=policy["bundle_sha256"]
            or digest(raw_manifest)!=policy["manifest_sha256"]):
        raise RepairDenied("ROOT_REPAIR_BUNDLE_HASH_CHANGED")
    manifest=json.loads(raw_manifest)
    scope=manifest.pop("scope_sha256",None)
    if (scope!=policy["scope_sha256"] or digest(canonical(manifest))!=scope
            or manifest["source_sha"]!=SOURCE
            or manifest["production_lkg"]!=LKG
            or manifest["freeze_sha256"]!=policy["freeze_sha256"]
            or manifest["promotion_hold_sha256"]!=policy["promotion_hold_sha256"]
            or manifest["no_runtime_or_mcp_mutation"] is not True
            or manifest["no_ticket_or_provider_mutation"] is not True
            or manifest["requires_new_owner_exact_signature"] is not True
            or manifest["requires_new_root_install_authorization"] is not True
            or manifest["no_integrity_waiver"] is not True
            or manifest["requires_genuine_full_pass"] is not True
            or manifest["max_full_scan_seconds"]!=5400
            or manifest["max_service_seconds"]!=5700
            or len(manifest["source"])!=2
            or manifest["new_unit_dropin"]["root_target"]!=str(FULL_DROPIN)):
        raise RepairDenied("SOURCE_MANIFEST_SCOPE_CHANGED")
    expected_unit_hashes={
        "full_service":policy["full_unit_sha256"],
        "fast_service":policy["fast_unit_sha256"],
        "emergency_dropin":policy["old_fast_emergency_sha256"],
    }
    if any((manifest["preexisting_root_systemd"].get(key) or {}).get("sha256")!=value
           for key,value in expected_unit_hashes.items()):
        raise RepairDenied("PREEXISTING_UNIT_POLICY_HASH_DRIFT")
    manifest["scope_sha256"]=scope
    expected={row["archive_member"]:row for row in [
        *manifest["source"],manifest["new_unit_dropin"]]}
    if (set(r["root_target"] for r in manifest["source"]) != {
            str(ROOT_SOURCE/"openclaw_authority_health_snapshot.py"),
            str(ROOT_SOURCE/"openclaw_authority_operational_health.py"),
        }):
        raise RepairDenied("ROOT_SOURCE_PATH_UNEXPECTED")
    objects={}
    with tarfile.open(fileobj=io.BytesIO(binary),mode="r:") as tf:
        names=set()
        for member in tf:
            if member.name in names:
                raise RepairDenied("DUPLICATE_ARCHIVE_MEMBER")
            names.add(member.name)
            if (not member.isfile() or member.uid!=0 or member.gid!=0
                    or member.mtime!=0 or member.issym() or member.islnk()
                    or member.isdev()):
                raise RepairDenied("UNSAFE_ARCHIVE_MEMBER")
            content=tf.extractfile(member).read()
            if member.name=="_metadata/reviewed-manifest.json":
                if content!=raw_manifest:
                    raise RepairDenied("EMBEDDED_MANIFEST_MISMATCH")
                continue
            row=expected.get(member.name)
            if (row is None or len(content)!=row["size"]
                    or digest(content)!=row["sha256"]
                    or stat.S_IMODE(member.mode)!=int(row["mode"],8)):
                raise RepairDenied("ARCHIVE_OBJECT_DRIFT")
            objects[row["root_target"]]=content
        if names!=set(expected)|{"_metadata/reviewed-manifest.json"}:
            raise RepairDenied("ARCHIVE_SOURCE_INCOMPLETE")
    return manifest,objects

def root_state(policy: dict) -> dict:
    if (Path("/opt/jason/current").resolve(strict=True)
            !=Path("/opt/jason/releases")/LKG
            or digest(FREEZE.read_bytes())!=policy["freeze_sha256"]
            or digest(HOLD.read_bytes())!=policy["promotion_hold_sha256"]):
        raise RepairDenied("PRODUCTION_LKG_OR_FREEZE_CHANGED")
    state=protected_release_record(CONTROL)
    drift=protected_release_record(DRIFT)
    if (state.get("circuit_breaker",{}).get("state")!="open"
            or state.get("circuit_breaker",{}).get("reason")!="continuous_production_drift_detected"
            or (state.get("last_known_good",{}).get("manifest") or {}).get("revision")!=LKG
            or drift.get("status")!="drift_detected"
            or drift.get("problems") != [{
                "kind":"failed_system_unit","state":"failed",
                "unit":"jason-openclaw-authority-health.service",
            }]):
        raise RepairDenied("UNRELATED_OR_CHANGED_ROOT_BREAKER")
    for name,image in ((RUNTIME,policy["runtime_image_id"]),
                       (MCP,policy["mcp_image_id"])):
        result=json.loads(subprocess.check_output(
            ["docker","inspect",name],timeout=15,text=True))
        if (not isinstance(result,list) or len(result)!=1
                or result[0]["Image"]!=image
                or result[0].get("State",{}).get("Status")!="running"
                or (name==RUNTIME and
                    result[0].get("State",{}).get("Health",{}).get("Status")!="healthy")
                or (result[0].get("Config",{}).get("Labels") or {}).get(
                    "com.teamaot.jason.source_revision")!=LKG):
            raise RepairDenied("PRODUCTION_CONTAINER_CHANGED:"+name)
    mcp_env=json.loads(subprocess.check_output(
        ["docker","inspect","--format","{{json .Config.Env}}",MCP],
        text=True,timeout=15))
    if mcp_env.count("JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false")!=1:
        raise RepairDenied("UNAUTHORIZED_STAGE_A0_ISSUER_STATE")
    full_info=FULL.lstat()
    if (FULL.is_symlink() or not stat.S_ISREG(full_info.st_mode)
            or full_info.st_uid!=1000
            or stat.S_IMODE(full_info.st_mode)!=0o600):
        raise RepairDenied("UNTRUSTED_LAST_FULL_TIMEOUT")
    full=json.loads(FULL.read_bytes())
    if (full.get("status")!="fail"
            or full.get("failures")!=["operational_health_timeout"]
            or full.get("snapshot_source_exit_code")!=124):
        raise RepairDenied("NOT_THE_REVIEWED_TIMEOUT")
    if subprocess.check_output(
        ["systemctl","show","jason-openclaw-authority-health.service",
         "-p","ActiveState","--value"],text=True,timeout=12).strip()!="failed":
        raise RepairDenied("AUTHORITY_HEALTH_NOT_FAILED")
    if subprocess.check_output(
        ["systemctl","show","jason-openclaw-authority-full-integrity.service",
         "-p","ActiveState","--value"],text=True,timeout=12).strip()=="active":
        raise RepairDenied("FULL_PROOF_ALREADY_RUNNING")
    if (ROOT_SOURCE.exists() or ROOT_SOURCE.is_symlink()
            or FULL_DROPIN_DIR.exists() or FULL_DROPIN_DIR.is_symlink()):
        raise RepairDenied("ROOT_REPAIR_PREFIX_NOT_EMPTY")
    for path in (*[ROOT_SOURCE / name for name in (
            "openclaw_authority_health_snapshot.py",
            "openclaw_authority_operational_health.py")],FULL_DROPIN):
        if path.exists() or path.is_symlink():
            raise RepairDenied("ROOT_REPAIR_TARGET_NOT_EMPTY")
    return {
        "runtime_id":json.loads(subprocess.check_output(
            ["docker","inspect",RUNTIME],text=True,timeout=15))[0]["Id"],
        "mcp_id":json.loads(subprocess.check_output(
            ["docker","inspect",MCP],text=True,timeout=15))[0]["Id"],
    }

@contextmanager
def native_release_lock():
    fd=os.open(LOCK,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                or info.st_uid!=1000 or info.st_mode&0o002):
            raise RepairDenied("NATIVE_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RepairDenied("NATIVE_RELEASE_TRANSACTION_BUSY") from exc
        yield
    finally:
        os.close(fd)

def root_audit(path: Path, data: dict):
    payload=canonical(data)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchown(fd,0,0)
        os.fchmod(fd,0o600)
        if os.write(fd,payload)!=len(payload):
            raise RepairDenied("AUDIT_WRITE_SHORT")
        os.fsync(fd)
    finally:
        os.close(fd)

def stage_objects(manifest: dict, objects: dict[str,bytes], *, root: Path = Path("/")):
    """Pure exact object staging; caller has native lock and signed Owner proof."""
    expected={row["root_target"]:row for row in [
        *manifest["source"],manifest["new_unit_dropin"]]}
    if set(objects)!=set(expected):
        raise RepairDenied("UNEXPECTED_ROOT_STAGING_OBJECTS")
    if root!=Path("/") and (not root.is_absolute() or Path("/tmp") not in root.parents
                            or not root.is_dir() or root.is_symlink()):
        raise RepairDenied("ONLY_PRIVATE_DISPOSABLE_TEST_ROOT")
    created=[]
    try:
        for target in sorted(objects):
            row=expected[target]
            dest=root/target.lstrip("/")
            current=dest.parent
            stack=[]
            while not current.exists():
                stack.append(current)
                current=current.parent
            for directory in reversed(stack):
                directory.mkdir(mode=0o755)
                if os.geteuid()==0:
                    os.chown(directory,0,0)
                created.append(directory)
            if dest.exists() or dest.is_symlink() or dest.parent.is_symlink():
                raise RepairDenied("ROOT_STAGING_TARGET_COLLISION")
            fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL
                       |getattr(os,"O_NOFOLLOW",0),0o600)
            try:
                if os.write(fd,objects[target])!=len(objects[target]):
                    raise RepairDenied("ROOT_STAGING_SHORT_WRITE")
                os.fchmod(fd,int(row["mode"],8))
                if os.geteuid()==0:
                    os.fchown(fd,0,0)
                os.fsync(fd)
            finally:
                os.close(fd)
        verify_objects(manifest,objects,root=root)
        return created
    except Exception:
        # Never blindly delete unknown inodes or changes after a partial write.
        # Preserve the failed scratch for explicit exact-owner root review.
        raise

def verify_objects(manifest: dict, objects: dict[str,bytes], *, root: Path=Path("/")):
    expected={row["root_target"]:row for row in [
        *manifest["source"],manifest["new_unit_dropin"]]}
    if set(objects)!=set(expected):
        raise RepairDenied("ROOT_VERIFY_SCOPE_CHANGED")
    for target,row in expected.items():
        path=root/target.lstrip("/")
        if path.is_symlink():
            raise RepairDenied("ROOT_SYMLINK_REJECTED")
        meta=path.lstat()
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink!=1
                or stat.S_IMODE(meta.st_mode)!=int(row["mode"],8)
                or digest(path.read_bytes())!=row["sha256"]
                or (os.geteuid()==0 and (meta.st_uid!=0 or meta.st_gid!=0))):
            raise RepairDenied("ROOT_VERIFICATION_FAILED")

def rollback_objects(manifest: dict, objects: dict[str,bytes],
                     *, root: Path=Path("/"), allow_partial: bool=False):
    expected={row["root_target"]:row for row in [
        *manifest["source"],manifest["new_unit_dropin"]]}
    # Verify every inode and all data BEFORE removing any owned source.
    # The two leaf directories were absent at initial root preflight.
    for folder in (root/str(ROOT_SOURCE).lstrip("/"),
                   root/str(FULL_DROPIN_DIR).lstrip("/")):
        if folder.is_symlink():
            raise RepairDenied("UNKNOWN_ROOT_DIRECTORY_LINK")
        if folder.is_dir():
            allowed={root/x.lstrip("/") for x in expected}
            for child in folder.iterdir():
                if child not in allowed or child.is_symlink():
                    raise RepairDenied("FOREIGN_CHILD_BLOCKS_ROOT_ROLLBACK")
    for target,row in expected.items():
        path=root/target.lstrip("/")
        if path.is_symlink():
            raise RepairDenied("UNKNOWN_ROOT_LINK_DURING_ROLLBACK")
        if not path.exists():
            if allow_partial:
                continue
            raise RepairDenied("ROOT_ROLLBACK_MISSING_DECLARED_FILE")
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                or stat.S_IMODE(info.st_mode)!=int(row["mode"],8)
                or digest(path.read_bytes())!=row["sha256"]):
            raise RepairDenied("UNVERIFIABLE_ROOT_ROLLBACK_OBJECT")
    for target in expected:
        path=root/target.lstrip("/")
        if path.exists():
            path.unlink()
    for d in (root/str(FULL_DROPIN_DIR).lstrip("/"),root/str(ROOT_SOURCE).lstrip("/")):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return all(not (root/target.lstrip("/")).exists() for target in expected)

def signed_owner_decision(policy: dict, manifest: dict):
    if not sys.stdin.isatty():
        raise RepairDenied("OWNER_LOCAL_INTERACTIVE_TERMINAL_REQUIRED")
    helper=load_trust(OWNER_AUTH,"root_exact_health_owner_auth")
    verifier=load_trust(OWNER_PROOF,"root_exact_health_owner_proof")
    endpoint="https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    challenge=helper._form(endpoint+"devicecode",{
        "client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(challenge.get(x),str) for x in (
            "device_code","user_code","verification_uri")):
        raise RepairDenied("OWNER_OAUTH_NOT_AVAILABLE")
    ttl=min(int(challenge.get("expires_in",0)),600)
    if ttl<60:
        raise RepairDenied("OWNER_OAUTH_EXPIRED")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+SOURCE,flush=True)
    print("SCOPE_SHA256="+policy["scope_sha256"],flush=True)
    print("PRODUCTION_FULL_SCAN_MAX_SECONDS=5700",flush=True)
    print("NO_TICKET_OR_RUNTIME_RESTART=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    until=time.monotonic()+ttl
    interval=max(5,min(20,int(challenge.get("interval",5))))
    oid=None
    while time.monotonic()<until:
        time.sleep(interval)
        token=helper._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":helper.CLIENT_ID,"device_code":challenge["device_code"]})
        if isinstance(token.get("access_token"),str):
            oid=helper.jwt_owner(token["access_token"])
            break
        if token.get("error")=="slow_down":
            interval=min(interval+5,20)
        elif token.get("error")!="authorization_pending":
            raise RepairDenied("OWNER_OAUTH_NOT_APPROVED")
    if oid is None or oid not in verifier.EXACT_OWNER_OAUTH_SUBJECTS:
        raise RepairDenied("OWNER_OAUTH_NO_VERIFIED_IDENTITY")
    if input("Confirm exact action with "+CONFIRM+": ").strip()!=CONFIRM:
        raise RepairDenied("OWNER_EXACT_ACTION_CONSENT_MISSING")
    key=verifier.read_service_owner_signing_key(SIGNER)
    public=verifier.read_pinned_root_owner_public_key(ROOT_PIN)
    if verifier.public_key_sha256(key.public_key())!=verifier.public_key_sha256(public):
        raise RepairDenied("PINNED_ED25519_OWNER_SIGNER_MISMATCH")
    at=datetime.now(timezone.utc)
    proof=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid.uuid4().hex,
        release_id="release-"+SOURCE[:16],
        candidate_sha=SOURCE,rollback_sha=LKG,
        scope_sha256=policy["scope_sha256"],
        manifest_sha256=policy["manifest_sha256"],
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=verifier.TID,verified_owner_oid=oid,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot",confirmed_decision="approve",
        at=at,private_key=key)
    verifier.verify_exact_owner_release(
        proof,public_key=public,at=at,
        expected_candidate_sha=SOURCE,expected_rollback_sha=LKG,
        expected_release_id="release-"+SOURCE[:16],
        expected_scope_sha256=policy["scope_sha256"],
        expected_manifest_sha256=policy["manifest_sha256"],
        expected_freeze_sha256=policy["freeze_sha256"])
    return proof

def verify_full_proof(after: float):
    file=FULL.lstat()
    if file.st_uid!=1000 or not stat.S_ISREG(file.st_mode) or stat.S_IMODE(file.st_mode)!=0o600 or file.st_mtime<after:
        raise RepairDenied("FRESH_FULL_PROOF_FILE_NOT_TRUSTED")
    proof=json.loads(FULL.read_bytes())
    if (proof.get("status")!="pass" or proof.get("failures")!=[]
            or proof.get("snapshot_source_exit_code")!=0
            or proof.get("provider_contacted") is not False
            or proof.get("provider_credentials_used") is not False):
        raise RepairDenied("NO_GENUINE_FULL_PROOF_PASS")
    for key in ("authority","replay","security_audit","orchestration_audit"):
        db=(proof.get("files") or {}).get(key) or {}
        if db.get("integrity")!="ok" or db.get("present") is not True or db.get("mode")!="0o600":
            raise RepairDenied("FULL_SQLITE_DB_PROOF_MISSING:"+key)
    backup=proof.get("backup_restore_proof") or {}
    if (backup.get("backup_integrity")!="ok"
            or backup.get("restore_integrity")!="ok"
            or backup.get("counts_match") is not True
            or backup.get("backup_mode")!="0o600"
            or backup.get("restore_mode")!="0o600"):
        raise RepairDenied("COMPLETE_BACKUP_RESTORE_PROOF_MISSING")
    keys=proof.get("trusted_key_registry") or {}
    if (keys.get("present") is not True or keys.get("mode")!="0o600"
            or int(keys.get("active_records",0))<1):
        raise RepairDenied("TRUSTED_KEY_REGISTRY_PROOF_MISSING")
    if (proof.get("delegations") or {}).get("expired_active_records",1)!=0:
        raise RepairDenied("ACTIVE_EXPIRED_DELEGATIONS")
    return proof

def system(*args: str, timeout: int=60):
    result=subprocess.run(["systemctl",*args],capture_output=True,
                          text=True,timeout=timeout,check=False)
    if result.returncode!=0:
        raise RepairDenied("SYSTEMD_CHECK_OR_ACTION_FAILED:"+args[0])
    return result.stdout.strip()

def execute():
    if (os.geteuid()!=0 or sys.flags.isolated!=1
            or Path(__file__).resolve(strict=True)!=ROOT_SCRIPT):
        raise RepairDenied("TRUSTED_ROOT_INSTALL_AND_ISOLATED_PYTHON_REQUIRED")
    policy=fixed_policy()
    manifest,objects=checked_bundle(policy)
    ledger=LEDGER.lstat()
    if (LEDGER.is_symlink() or not stat.S_ISDIR(ledger.st_mode)
            or ledger.st_uid!=0 or stat.S_IMODE(ledger.st_mode)!=0o700
            or any(LEDGER.iterdir())):
        raise RepairDenied("EXACT_ACTION_ALREADY_USED_OR_AUDIT_UNTRUSTED")
    before=root_state(policy)
    proof=signed_owner_decision(policy,manifest)
    result={"schema_version":"1.0","exact_action":ACTION,"status":"failed",
            "source_sha":SOURCE,"scope_sha256":policy["scope_sha256"],
            "started_at":datetime.now(timezone.utc).isoformat(),
            "production_deployment":False,"ticket_runtime_changed":False,
            "full_integrity_verified":False,"root_breaker_closed":False}
    staged=False
    emergency_removed=False
    original_fast_overlay=FAST_EMERGENCY.read_bytes()
    if digest(original_fast_overlay)!=policy["old_fast_emergency_sha256"]:
        raise RepairDenied("EXPIRED_FAST_OVERLAY_UNTRUSTED")
    try:
        with native_release_lock():
            if root_state(policy)!=before or fixed_policy()!=policy:
                raise RepairDenied("PRODUCTION_CHANGED_DURING_OWNER_AUTH")
            root_audit(LEDGER/(ACTION+".attempt.json"),{
                "schema_version":"1.0","exact_action":ACTION,
                "signed_owner_proof":proof,"source_sha":SOURCE,
                "policy_digest":digest(canonical(policy)),
                "status":"claimed_before_production_mutation"})
            stage_objects(manifest,objects)
            verify_objects(manifest,objects)
            staged=True
            system("daemon-reload")
            effective=system("cat","jason-openclaw-authority-full-integrity.service")
            if (str(ROOT_SOURCE/"openclaw_authority_health_snapshot.py") not in effective
                    or "TimeoutStartSec=5700" not in effective):
                raise RepairDenied("SYSTEMD_EXACT_V2_UNIT_NOT_ACTIVE")
        # Native lock must be free for the long read-only scan and watchdog.
        started=time.time()
        system("reset-failed","jason-openclaw-authority-full-integrity.service")
        system("start","jason-openclaw-authority-full-integrity.service",timeout=5760)
        verify_full_proof(started)
        result["full_integrity_verified"]=True
        if digest(FAST_EMERGENCY.read_bytes())!=policy["old_fast_emergency_sha256"]:
            raise RepairDenied("EXPIRED_FAST_OVERRIDE_CONTENT_CHANGED")
        # A complete full PASS is required BEFORE removing the expired adapter.
        FAST_EMERGENCY.unlink()
        emergency_removed=True
        system("daemon-reload")
        system("reset-failed","jason-openclaw-authority-health.service")
        system("start","jason-openclaw-authority-health.service",timeout=100)
        fast=json.loads(FAST.read_bytes())
        if fast.get("status")!="pass" or fast.get("failures")!=[]:
            raise RepairDenied("CANONICAL_FAST_HEALTH_DID_NOT_PASS")
        system("reset-failed","jason-production-drift-watchdog.service")
        observations=[]
        for i in range(3):
            if i:
                time.sleep(17)
            system("start","jason-production-drift-watchdog.service",timeout=120)
            drift=protected_release_record(DRIFT)
            if drift.get("status")!="pass" or drift.get("problems")!=[]:
                raise RepairDenied("ROOT_DRIFT_STILL_NOT_PASS")
            stamp=str(drift.get("observed_at") or "")
            if stamp in observations:
                raise RepairDenied("ROOT_DRIFT_OBSERVATION_NOT_FRESH")
            observations.append(stamp)
        result["root_drift_distinct_passes"]=len(observations)
        # The existing native request-to-root revalidation path, never direct
        # edits of the release control state, must close the breaker.
        code=("import sys;from pathlib import Path;"
              "sys.path.insert(0,'/home/al/.local/lib/jason');"
              "import release_manager_host_runner as r;"
              "r.revalidate_circuit_breaker(Path('/var/lib/jason/openclaw/release-manager'))")
        subprocess.run(["runuser","-u","al","--","/usr/bin/python3","-c",code],
                       timeout=130,check=True,capture_output=True)
        control=protected_release_record(CONTROL)
        if control.get("circuit_breaker",{}).get("state")!="closed":
            raise RepairDenied("NATIVE_ROOT_BREAKER_NOT_CLOSED")
        result["root_breaker_closed"]=True
        result["status"]="verified"
    except Exception:
        # Preserve genuine new full PASS if generated; do not falsely revert
        # completed proof to a prior missing state. A failed breaker closure
        # is a separately actionable partial state, never a PASS.
        if emergency_removed and not FAST_EMERGENCY.exists():
            data=original_fast_overlay
            fd=os.open(FAST_EMERGENCY,os.O_CREAT|os.O_EXCL|os.O_WRONLY
                       |getattr(os,"O_NOFOLLOW",0),0o644)
            try:
                if os.write(fd,data)!=len(data):
                    raise RepairDenied("EMERGENCY_OVERLAY_RESTORE_SHORT")
                os.fchown(fd,0,0)
                os.fchmod(fd,0o644)
                os.fsync(fd)
            finally:os.close(fd)
        if not result["full_integrity_verified"]:
            try:
                rollback_objects(manifest,objects,allow_partial=True)
                system("daemon-reload")
                result["source_rollback"]="verified_absence"
            except Exception:
                result["source_rollback"]="failed_closed_manual_exact_inodes_needed"
        raise
    finally:
        result["completed_at"]=datetime.now(timezone.utc).isoformat()
        root_audit(LEDGER/(ACTION+".result.json"),result)
    print("COMPLETE_FOUR_SQLITE_AND_RESTORE_PROOF=VERIFIED")
    print("CANONICAL_FAST_HEALTH_AND_ROOT_DRIFT=VERIFIED")
    print("NATIVE_ROOT_BREAKER=CLOSED")
    print("RUNTIME_AND_MCP_UNCHANGED=true")

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    try:
        if args.check_only:
            if os.geteuid()==0:
                policy=fixed_policy()
                checked_bundle(policy)
                root_state(policy)
                print("EXACT_V2_ROOT_HEALTH_PREFLIGHT=PASS")
            else:
                print("SOURCE_ONLY_CHECK_NO_ROOT_OR_PRODUCTION_MUTATION=true")
            return 0
        execute()
    except Exception as exc:
        print("OWNER_V2_INTEGRITY_RECOVERY=DENIED "+
              type(exc).__name__+":"+
              (str(exc)[:145] if isinstance(exc,RepairDenied)
               else "SENSITIVE_DETAILS_REDACTED"),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
