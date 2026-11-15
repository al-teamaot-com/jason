#!/usr/bin/env python3
"""ONE exact Owner-signed trusted-root update: existing V2 helper and policy.

Only a fresh independently authenticated UID1000 Owner Ed25519 proof and an
authorized local root console can perform this transaction. No services,
release pointers, breaker state, private signer keys or legacy audit changes.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import uuid

MERGE="7b42ce983896711525de4c7955bf9fc43ac003d0"
ROLLBACK="45e52de4803a6f0768187793bba4990ed1d11a07"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION="owner-v2-issuer-attested-root-code-policy-replace-v1-20261115"
SCOPE="cf866a84f38fc0b45decb7bf0a87ac34232bf124be3b1796e6a243cb86bfb196"
MANIFEST_SHA="119128ead74bc08e02dff543ae2a5ec458c3c14685c267bbd7cca230a290b6e1"
PACKAGE_SHA="b221e48383cef5cfd69fdd24b38c08ceacf8459a1b7c0b62dab6036fd721006c"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ARCHIVE=Path("/srv/jason/archive")
MANIFEST=ARCHIVE/("owner-v2-issuer-attested-two-file-root-replace-audited-manifest-"+MERGE+".json")
PACKAGE=ARCHIVE/("owner-v2-issuer-attested-two-file-root-replace-audited-"+MERGE+".tar")
OWNER_DECISION=ARCHIVE/("owner-v2-issuer-attested-two-file-root-replace-owner-proof-"+MERGE+".json")
AUDIT_ATTEMPT=Path("/etc/jason-owner-release/owner-v2-root-code-upgrade-"+MERGE[:12]+".attempt.json")
AUDIT_RESULT=Path("/etc/jason-owner-release/owner-v2-root-code-upgrade-"+MERGE[:12]+".result.json")
ROOT_RUNNER=Path("/run/jason-owner-v2-root-updater-"+MERGE[:12]+".py")
ROOT_VERIFIER=Path("/usr/local/lib/jason/owner_signed_release.py")
ROOT_PIN=Path("/etc/jason-owner-release/verified-owner-public-key.json")
LEDGER=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger")
LOCK=Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT=Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
TRUSTED_CODE=Path("/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py")
TRUSTED_POLICY=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json")
ORIGINAL_BOOTSTRAP="owner-full-integrity-v2-initial-root-trust-bootstrap-20261113"
ORIGINAL_BOOTSTRAP_SHA="45e52de4803a6f0768187793bba4990ed1d11a07"
ORIGINAL_BOOTSTRAP_SCOPE="a7524f8b761db1f3a912eea3221014b46729be34705397aa87ef283d513edf9d"
ORIGINAL_BOOTSTRAP_MANIFEST_SHA="d64d619b8bd26541fc1bcc8fa72ce047a747c093265bda55702d5e50f457199a"

class RootUpdateDenied(PermissionError):
    pass

def digest(raw:bytes)->str:
    return sha256(raw).hexdigest()

def canonical(obj:dict)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def owned_read(path:Path,uid:int,mode:str|None,maximum:int)->bytes:
    if path.is_symlink():
        raise RootUpdateDenied("REVIEWED_SOURCE_IS_SYMLINK")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=uid
                or st.st_nlink!=1 or st.st_size>maximum
                or (mode is not None and stat.S_IMODE(st.st_mode)!=int(mode,8))):
            raise RootUpdateDenied("REVIEWED_OBJECT_OWNER_MODE_OR_SIZE_CHANGED")
        raw=os.read(fd,maximum+1)
        if len(raw)!=st.st_size:
            raise RootUpdateDenied("SOURCE_INODE_READ_CHANGED")
        return raw
    finally:
        os.close(fd)

def read_manifest_package():
    bytes_plan=owned_read(MANIFEST,1000,"0640",65536)
    bytes_archive=owned_read(PACKAGE,1000,"0600",2*1024*1024)
    if digest(bytes_plan)!=MANIFEST_SHA or digest(bytes_archive)!=PACKAGE_SHA:
        raise RootUpdateDenied("ROOT_REPLACEMENT_BUNDLE_OR_MANIFEST_HASH_CHANGED")
    manifest=json.loads(bytes_plan)
    control=dict(manifest)
    scope=control.pop("scope_sha256",None)
    if (scope!=SCOPE or digest(canonical(control))!=SCOPE
            or manifest.get("exact_action")!=ACTION
            or manifest.get("reviewed_merged_main_sha")!=MERGE
            or manifest.get("rollback_protected_main_sha")!=ROLLBACK
            or manifest.get("production_lkg")!=LKG
            or manifest.get("production_root_replacement_authorized") is not False
            or manifest.get("no_full_integrity_scan") is not True
            or manifest.get("no_unit_reload_or_restart") is not True
            or manifest.get("no_breaker_override") is not True
            or manifest.get("freeze_sha256")!=FREEZE_SHA
            or manifest.get("promotion_hold_sha256")!=HOLD_SHA):
        raise RootUpdateDenied("EXACT_REVIEWED_PRODUCTION_SCOPE_CHANGED")
    rows=manifest.get("exact_replacements") or []
    paths={
        "/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py":"0444",
        "/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json":"0400",
    }
    if len(rows)!=2 or {r["root_target"]:r["mode"] for r in rows}!=paths:
        raise RootUpdateDenied("EXACT_TWO_ROOT_FILES_SCOPE_CHANGED")
    receipts=manifest.get("immutable_root_audit_outputs") or {}
    parent=Path("/etc/jason-owner-release")
    if (receipts.get("root_attempt_path")!=str(AUDIT_ATTEMPT)
            or receipts.get("root_result_path")!=str(AUDIT_RESULT)
            or receipts.get("mode")!="0600"
            or receipts.get("root_owner_uid")!=0
            or receipts.get("root_owner_gid")!=0
            or receipts.get("parent_directory")!=str(parent)
            or receipts.get("parent_owner_uid")!=0
            or receipts.get("parent_owner_gid")!=0
            or receipts.get("parent_mode")!="0755"
            or receipts.get("create_attempt_before_replacing_existing_root_files") is not True
            or receipts.get("creation_once_exclusive") is not True
            or receipts.get("historical_bootstrap_root_ledger_unchanged") is not True):
        raise RootUpdateDenied("ROOT_IMMUTABLE_AUDIT_RECEIPT_SCOPE_CHANGED")
    root_parent=parent.lstat()
    if (parent.is_symlink() or root_parent.st_uid!=0 or root_parent.st_gid!=0
            or stat.S_IMODE(root_parent.st_mode)!=0o755):
        raise RootUpdateDenied("ROOT_AUDIT_PARENT_NOT_ROOT_TRUSTED")
    for record in (AUDIT_ATTEMPT,AUDIT_RESULT):
        if record.exists() or record.is_symlink():
            raise RootUpdateDenied("ROOT_UPGRADE_ONE_SHOT_AUDIT_ALREADY_EXISTS")
    for row in rows:
        if (row.get("owner_uid")!=0 or row.get("owner_gid")!=0
                or row.get("archive_new")!="replacement/"+row["root_target"].lstrip("/")
                or row.get("archive_old")!="rollback/"+row["root_target"].lstrip("/")):
            raise RootUpdateDenied("SOURCE_TARGET_METADATA_CHANGED")
    ledger=manifest.get("preserve_existing_ledger") or {}
    if (ledger.get("root_path")!=str(LEDGER)
            or ledger.get("mode")!="0700"
            or ledger.get("no_modify_or_delete_existing_audit") is not True
            or set(ledger.get("exact_previous_evidence_files") or [])!={
                ORIGINAL_BOOTSTRAP+".attempt.json",
                ORIGINAL_BOOTSTRAP+".result.json",
            }):
        raise RootUpdateDenied("BOOTSTRAP_AUDIT_PRESERVATION_SCOPE_CHANGED")
    # Use a closed explicit inventory and prohibit tar links, devices,
    # path traversal or any archive-provided extraction behavior.
    expected={r[k]:(r,k) for r in rows for k in ("archive_new","archive_old")}
    new_old={}
    observed=set()
    with tarfile.open(fileobj=io.BytesIO(bytes_archive),mode="r:") as tf:
        for member in tf:
            if member.name in observed:
                raise RootUpdateDenied("DUPLICATE_SOURCE_ARCHIVE_MEMBER")
            observed.add(member.name)
            if (member.uid!=0 or member.gid!=0 or member.mtime!=0
                    or not member.isfile() or member.issym() or member.islnk()
                    or member.isdev()):
                raise RootUpdateDenied("UNTRUSTED_SOURCE_ARCHIVE_MEMBER")
            data=tf.extractfile(member).read()
            if member.name=="_metadata/owner-exact-root-replacement.json":
                if data!=bytes_plan:
                    raise RootUpdateDenied("ARCHIVE_EMBEDDED_SCOPE_DIFFERENT")
                continue
            if member.name not in expected:
                raise RootUpdateDenied("UNREVIEWED_ROOT_ARCHIVE_FILE")
            row,k=expected[member.name]
            sha=row["new_sha256"] if k=="archive_new" else row["old_sha256"]
            size=row["new_size"] if k=="archive_new" else row["old_size"]
            if (len(data)!=size or digest(data)!=sha
                    or member.mode!=int(row["mode"],8)):
                raise RootUpdateDenied("ROOT_ARCHIVE_MEMBER_HASH_MODE_DRIFT")
            new_old[(row["root_target"],k)]=data
        if observed!=set(expected)|{"_metadata/owner-exact-root-replacement.json"}:
            raise RootUpdateDenied("INCOMPLETE_EXACT_ROOT_PACKAGE")
    return manifest,new_old

def load_verifier():
    st=ROOT_VERIFIER.lstat()
    if (ROOT_VERIFIER.is_symlink() or st.st_uid!=0 or st.st_gid!=0
            or not stat.S_ISREG(st.st_mode) or st.st_mode&0o022):
        raise RootUpdateDenied("ROOT_VERIFIER_CODE_NOT_TRUSTED")
    spec=importlib.util.spec_from_file_location("pinned_root_owner_release",ROOT_VERIFIER)
    if spec is None or spec.loader is None:
        raise RootUpdateDenied("ROOT_VERIFIER_MODULE_UNAVAILABLE")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def verify_historical_bootstrap(verifier):
    st=LEDGER.lstat()
    if (LEDGER.is_symlink() or not stat.S_ISDIR(st.st_mode)
            or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)!=0o700):
        raise RootUpdateDenied("IMMUTABLE_ROOT_BOOTSTRAP_LEDGER_NOT_TRUSTED")
    pair={
        LEDGER/(ORIGINAL_BOOTSTRAP+".attempt.json"),
        LEDGER/(ORIGINAL_BOOTSTRAP+".result.json"),
    }
    if set(LEDGER.iterdir())!=pair:
        raise RootUpdateDenied("PREEXISTING_BOOTSTRAP_LEDGER_FOREIGN_CONTENT")
    hashes={}
    for p in pair:
        binary=owned_read(p,0,"0600",131072)
        hashes[p.name]=digest(binary)
    attempt=json.loads(owned_read(LEDGER/(ORIGINAL_BOOTSTRAP+".attempt.json"),0,"0600",131072))
    outcome=json.loads(owned_read(LEDGER/(ORIGINAL_BOOTSTRAP+".result.json"),0,"0600",131072))
    if (attempt.get("schema_version")!="1.0"
            or attempt.get("action")!=ORIGINAL_BOOTSTRAP
            or attempt.get("source_sha")!=ORIGINAL_BOOTSTRAP_SHA
            or attempt.get("scope_sha256")!=ORIGINAL_BOOTSTRAP_SCOPE
            or attempt.get("status")!="claimed_before_root_trust_installation"
            or outcome.get("schema_version")!="1.0"
            or outcome.get("action")!=ORIGINAL_BOOTSTRAP
            or outcome.get("source_sha")!=ORIGINAL_BOOTSTRAP_SHA
            or outcome.get("scope_sha256")!=ORIGINAL_BOOTSTRAP_SCOPE
            or outcome.get("status")!="verified"
            or outcome.get("ledger_directory")!=str(LEDGER)
            or set(outcome.get("approved_files") or [])!={str(TRUSTED_CODE),str(TRUSTED_POLICY)}
            or outcome.get("production_services_changed") is not False
            or outcome.get("full_sqlite_scan_ran") is not False
            or outcome.get("root_breaker_modified") is not False):
        raise RootUpdateDenied("PREEXISTING_BOOTSTRAP_AUDIT_INCONSISTENT")
    proof=attempt.get("owner_proof") or {}
    issued=(proof.get("payload") or {}).get("issued_at")
    try:
        historic=datetime.fromisoformat(issued)
    except (TypeError,ValueError) as exc:
        raise RootUpdateDenied("PRIOR_BOOTSTRAP_OWNER_SIGNATURE_TIMESTAMP_INVALID") from exc
    public=verifier.read_pinned_root_owner_public_key(ROOT_PIN,require_root_owned=True)
    verifier.verify_exact_owner_release(
        proof,public_key=public,at=historic,
        expected_candidate_sha=ORIGINAL_BOOTSTRAP_SHA,
        expected_rollback_sha=LKG,
        expected_release_id="release-"+ORIGINAL_BOOTSTRAP_SHA[:16],
        expected_scope_sha256=ORIGINAL_BOOTSTRAP_SCOPE,
        expected_manifest_sha256=ORIGINAL_BOOTSTRAP_MANIFEST_SHA,
        expected_freeze_sha256=FREEZE_SHA,
    )
    return hashes

def signed_owner_decision(verifier):
    parent=OWNER_DECISION.parent.lstat()
    if (OWNER_DECISION.is_symlink() or parent.st_uid!=1000
            or stat.S_IMODE(parent.st_mode)!=0o2770):
        raise RootUpdateDenied("OWNER_SIGNED_DECISION_PARENT_NOT_TRUSTED")
    decision=json.loads(owned_read(OWNER_DECISION,1000,"0600",32768))
    fields={"schema_version","exact_action","source_sha","rollback_sha",
            "scope_sha256","manifest_sha256","package_sha256","status",
            "signed_owner_proof"}
    if (set(decision)!=fields or decision.get("schema_version")!="1.0"
            or decision.get("exact_action")!=ACTION
            or decision.get("source_sha")!=MERGE
            or decision.get("rollback_sha")!=ROLLBACK
            or decision.get("scope_sha256")!=SCOPE
            or decision.get("manifest_sha256")!=MANIFEST_SHA
            or decision.get("package_sha256")!=PACKAGE_SHA
            or decision.get("status")!="OWNER_APPROVED_NOT_APPLIED"):
        raise RootUpdateDenied("OWNER_APPROVAL_EXACT_SCOPE_CHANGED")
    public=verifier.read_pinned_root_owner_public_key(ROOT_PIN,require_root_owned=True)
    verifier.verify_exact_owner_release(
        decision["signed_owner_proof"],public_key=public,at=datetime.now(timezone.utc),
        expected_candidate_sha=MERGE,expected_rollback_sha=ROLLBACK,
        expected_release_id="release-"+MERGE[:16],
        expected_scope_sha256=SCOPE,
        expected_manifest_sha256=MANIFEST_SHA,
        expected_freeze_sha256=FREEZE_SHA,
    )
    return decision

def root_record(path:Path):
    # Native protected readback: existing root-owned 0600 records in
    # al-owned 0700 spool, never modified by this installer.
    st=path.parent.lstat()
    if (path.parent.is_symlink() or st.st_uid!=1000
            or not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o700):
        raise RootUpdateDenied("PROTECTED_RELEASE_SPOOL_NOT_TRUSTED")
    return json.loads(owned_read(path,0,"0600",131072))

def runtime_state():
    if (Path("/opt/jason/current").resolve(strict=True)
            !=Path("/opt/jason/releases")/LKG
            or digest(FREEZE.read_bytes())!=FREEZE_SHA
            or digest(HOLD.read_bytes())!=HOLD_SHA):
        raise RootUpdateDenied("RELEASE_LKG_OR_PROTECTION_CHANGED")
    control=root_record(CONTROL)
    drift=root_record(DRIFT)
    if (control.get("circuit_breaker",{}).get("state")!="open"
            or control.get("circuit_breaker",{}).get("reason")!="continuous_production_drift_detected"
            or (control.get("last_known_good",{}).get("manifest") or {}).get("revision")!=LKG
            or drift.get("status")!="drift_detected"
            or drift.get("problems") != [{
                "kind":"failed_system_unit","state":"failed",
                "unit":"jason-openclaw-authority-health.service",
            }]):
        raise RootUpdateDenied("CURRENT_ROOT_BREAKER_OR_DRIFT_CHANGED")
    identities={}
    for name,image in [
        ("jason-runtime","sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"),
        ("jason-mcp-pilot","sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"),
    ]:
        obj=json.loads(subprocess.check_output(["docker","inspect",name],text=True,timeout=20))[0]
        if (obj["Image"]!=image or obj.get("State",{}).get("Status")!="running"
                or obj.get("Config",{}).get("Labels",{}).get(
                    "com.teamaot.jason.source_revision")!=LKG
                or (name=="jason-runtime" and obj.get("State",{}).get(
                    "Health",{}).get("Status")!="healthy")):
            raise RootUpdateDenied("RUNTIME_OR_MCP_IMAGE_CHANGED")
        if name=="jason-mcp-pilot":
            env = obj.get("Config",{}).get("Env") or []
            if (env.count("JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true") != 1
                    or env.count("JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false") != 0):
                raise RootUpdateDenied("STAGE_A0_ISSUER_NOT_EXACTLY_ENABLED")
            ledger=Path("/etc/jason-owner-release/pmv4-stage-a0-issuer-ledger")
            action="pmv4-stage-a0-same-image-owner-issuer-v1"
            m=ledger.lstat()
            if (ledger.is_symlink() or not stat.S_ISDIR(m.st_mode)
                    or (m.st_uid,m.st_gid)!=(0,0)
                    or stat.S_IMODE(m.st_mode)!=0o700):
                raise RootUpdateDenied("STAGE_A0_ISSUER_ROOT_LEDGER_UNTRUSTED")
            attempt=ledger/(action+".attempt.json")
            result=ledger/(action+".result.json")
            if set(ledger.iterdir())!={attempt,result}:
                raise RootUpdateDenied("STAGE_A0_ISSUER_LEDGER_NOT_EXACT")
            history=json.loads(owned_read(attempt,0,"0600",131072))
            outcome=json.loads(owned_read(result,0,"0600",131072))
            if (history.get("action")!=action
                    or history.get("source")!=MERGE
                    or history.get("mcp_image")!=image
                    or history.get("freeze_sha256")!=FREEZE_SHA
                    or history.get("status")!="exact_one_use_claimed_before_mutation"
                    or outcome.get("action")!=action
                    or outcome.get("result")!="verified"
                    or outcome.get("new_mcp_id")!=obj["Id"]):
                raise RootUpdateDenied("STAGE_A0_ISSUER_ROOT_ACTIVATION_NOT_PROVEN")
            # The newly installed V2 health code independently verifies the
            # *historical Owner Ed25519 signature* and root pinned issuer code.
        identities[name]=obj["Id"]
    return identities

def verify_root_file(row:dict,expected:str):
    p=Path(row["root_target"])
    st=p.lstat()
    wanted=row["old_sha256"] if expected=="old" else row["new_sha256"]
    if (p.is_symlink() or not stat.S_ISREG(st.st_mode)
            or st.st_uid!=0 or st.st_gid!=0 or st.st_nlink!=1
            or stat.S_IMODE(st.st_mode)!=int(row["mode"],8)
            or digest(owned_read(p,0,row["mode"],2*1024*1024))!=wanted):
        raise RootUpdateDenied("ROOT_REPLACEMENT_FILE_DRIFT:"+expected)
    parent=p.parent.lstat()
    if (p.parent.is_symlink() or parent.st_uid!=0 or parent.st_gid!=0
            or not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode)!=0o755):
        raise RootUpdateDenied("ROOT_REPLACEMENT_DIRECTORY_NOT_TRUSTED")

def replace_exact(row:dict,data:bytes,*,new:bool):
    """Hash-pinned swap, with exact-inode temp cleanup on every exception.

    An error may occur *after* os.replace commits and *before* the caller
    records a successful function return. The transaction owner must
    rollback all reviewed old/new target hashes on any exception after its
    one-use attempt ledger is claimed; never infer success from a flag set
    after this function returns.
    """
    target=Path(row["root_target"])
    expected=row["new_sha256"] if new else row["old_sha256"]
    if digest(data)!=expected:
        raise RootUpdateDenied("STAGED_ROOT_SOURCE_HASH_DRIFT")
    tmp=target.parent/(".owner-v2-exact-replace-"+MERGE[:12]+"-"+uuid.uuid4().hex)
    written_inode=None
    try:
        fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY
                   |getattr(os,"O_NOFOLLOW",0),0o600)
        written_stat=os.fstat(fd)
        written_inode=(written_stat.st_dev,written_stat.st_ino)
        try:
            if os.write(fd,data)!=len(data):
                raise RootUpdateDenied("SHORT_ROOT_REPLACEMENT_WRITE")
            os.fchown(fd,0,0)
            os.fchmod(fd,int(row["mode"],8))
            os.fsync(fd)
        finally:
            os.close(fd)
        if digest(owned_read(tmp,0,row["mode"],2*1024*1024))!=expected:
            raise RootUpdateDenied("TEMP_REPLACEMENT_HASH_CHANGED")
        os.replace(tmp,target)
        dirfd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        verify_root_file(row,"new" if new else "old")
    finally:
        # Never unlink a replaced/foreign inode on a guessed temp path.
        if written_inode is not None:
            try:
                remaining=tmp.lstat()
            except FileNotFoundError:
                remaining=None
            if remaining is not None:
                if (tmp.is_symlink() or not stat.S_ISREG(remaining.st_mode)
                        or remaining.st_uid!=0 or remaining.st_gid!=0
                        or remaining.st_nlink!=1
                        or (remaining.st_dev,remaining.st_ino)!=written_inode):
                    raise RootUpdateDenied("UNTRUSTED_TEMPORARY_INODE_CANNOT_DELETE")
                tmp.unlink()


def audit_once(path:Path,document:dict):
    if path.exists() or path.is_symlink():
        raise RootUpdateDenied("EXACT_OWNER_ROOT_UPGRADE_ONE_SHOT_CONSUMED")
    binary=canonical(document)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchown(fd,0,0)
        os.fchmod(fd,0o600)
        if os.write(fd,binary)!=len(binary):
            raise RootUpdateDenied("AUDIT_ROOT_SHORT_WRITE")
        os.fsync(fd)
    finally:os.close(fd)

def exact_rollback(manifest:dict,sources:dict):
    """Restore only the two known inodes, never overwrite an unknown object."""
    for row in manifest["exact_replacements"]:
        target=Path(row["root_target"])
        current=digest(owned_read(target,0,row["mode"],2*1024*1024))
        if current not in {row["old_sha256"],row["new_sha256"]}:
            raise RootUpdateDenied("UNREVIEWED_INODE_BLOCKS_EXACT_ROLLBACK")
    for row in manifest["exact_replacements"]:
        target=Path(row["root_target"])
        if digest(owned_read(target,0,row["mode"],2*1024*1024))==row["new_sha256"]:
            replace_exact(row,sources[(row["root_target"],"archive_old")],new=False)
    for row in manifest["exact_replacements"]:
        verify_root_file(row,"old")
    return True

def install():
    if (os.geteuid()!=0 or sys.flags.isolated!=1
            or Path(__file__).resolve(strict=True)!=ROOT_RUNNER):
        raise RootUpdateDenied("EXACT_VERIFIED_ROOT_OWNED_EPHEMERAL_RUNNER_REQUIRED")
    meta=ROOT_RUNNER.lstat()
    if (ROOT_RUNNER.is_symlink() or meta.st_uid!=0 or meta.st_gid!=0
            or stat.S_IMODE(meta.st_mode)!=0o400
            or not stat.S_ISREG(meta.st_mode)):
        raise RootUpdateDenied("ROOT_RUNNER_NOT_ROOT_OWNED_IMMUTABLE")
    manifest,sources=read_manifest_package()
    verifier=load_verifier()
    historical=verify_historical_bootstrap(verifier)
    before=runtime_state()
    for row in manifest["exact_replacements"]:
        verify_root_file(row,"old")
    approval=signed_owner_decision(verifier)
    if AUDIT_ATTEMPT.exists() or AUDIT_RESULT.exists():
        raise RootUpdateDenied("EXACT_ROOT_UPGRADE_ONE_SHOT_ALREADY_CONSUMED")
    fd=os.open(LOCK,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
    attempted=False
    outcome={"schema_version":"1.0","exact_action":ACTION,
             "source_sha":MERGE,"scope_sha256":SCOPE,
             "status":"failed","started_at":datetime.now(timezone.utc).isoformat(),
             "changed_production_services":False,
             "full_integrity_scan_started":False,"breaker_overridden":False,
             "rollback_status":"not_needed"}
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=1000
                or st.st_nlink!=1 or st.st_mode & 0o002):
            raise RootUpdateDenied("NATIVE_PRODUCTION_LOCK_NOT_TRUSTED")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RootUpdateDenied("NATIVE_PRODUCTION_RELEASE_LOCK_BUSY") from exc
        if (runtime_state()!=before or verify_historical_bootstrap(verifier)!=historical
                or read_manifest_package()[0]!=manifest):
            raise RootUpdateDenied("EXACT_ROOT_UPGRADE_STATE_CHANGED_BEFORE_COMMIT")
        for row in manifest["exact_replacements"]:
            verify_root_file(row,"old")
        signed_owner_decision(verifier)
        audit_once(AUDIT_ATTEMPT,{
            "schema_version":"1.0","exact_action":ACTION,
            "source_sha":MERGE,"scope_sha256":SCOPE,
            "status":"one_shot_claimed_before_mutation",
            "owner_proof":approval["signed_owner_proof"],
            "at":datetime.now(timezone.utc).isoformat(),
        })
        attempted=True
        for row in manifest["exact_replacements"]:
            replace_exact(row,sources[(row["root_target"],"archive_new")],new=True)
        if runtime_state()!=before or verify_historical_bootstrap(verifier)!=historical:
            raise RootUpdateDenied("POST_REPLACEMENT_PRODUCTION_OR_LEDGER_CHANGED")
        # Root-owned self-check: no integrity scan, restarts or mutations.
        check=subprocess.run(
            ["/usr/bin/python3","-I",str(TRUSTED_CODE),"--check-only"],
            capture_output=True,text=True,timeout=150,check=False)
        if check.returncode!=0 or "EXACT_V2_ROOT_HEALTH_PREFLIGHT=PASS" not in check.stdout:
            raise RootUpdateDenied("NEW_TRUSTED_ROOT_HELPER_READ_ONLY_ACCEPTANCE_FAILED")
        for row in manifest["exact_replacements"]:
            verify_root_file(row,"new")
        outcome.update({"status":"verified",
            "completed_at":datetime.now(timezone.utc).isoformat(),
            "root_read_only_health_preflight":"PASS",
            "root_helper_new_sha256":manifest["exact_replacements"][0]["new_sha256"],
            "root_policy_new_sha256":manifest["exact_replacements"][1]["new_sha256"],
            "bootstrap_ledger_unchanged":True,
            "rollback_prepared":True})
        audit_once(AUDIT_RESULT,outcome)
        print("EXACT_V2_ISSUER_AWARE_ROOT_CODE_POLICY_UPGRADE=VERIFIED")
        print("ROOT_V2_READ_ONLY_PREFLIGHT=PASS")
        print("ORIGINAL_BOOTSTRAP_LEDGER_UNCHANGED=true")
        print("NO_LIVE_FULL_SQLITE_SCAN_OR_SERVICE_RESTART=true")
        print("NO_FREEZE_OR_BREAKER_MUTATION=true")
        print("ROOT_RESULT_AUDIT="+str(AUDIT_RESULT))
        return 0
    except Exception:
        if attempted:
            try:
                # A swap can commit before replace_exact() raises. Always
                # inspect and restore BOTH reviewed target hashes, including
                # failures mid-write, mid-swap or before the success flag.
                exact_rollback(manifest,sources)
                outcome["rollback_status"]="original_two_root_files_verified"
            except Exception:
                outcome["rollback_status"]="fail_closed_manual_exact_root_recovery_needed"
            outcome["completed_at"]=datetime.now(timezone.utc).isoformat()
            if not AUDIT_RESULT.exists():
                try:audit_once(AUDIT_RESULT,outcome)
                except Exception:pass
        raise
    finally:
        os.close(fd)

def main():
    try:
        if sys.argv[1:]!=["--execute"]:
            raise RootUpdateDenied("ONLY_EXACT_TWO_FILE_ONE_SHOT_ACTION_SUPPORTED")
        return install()
    except Exception as exc:
        print("OWNER_V2_TWO_FILE_ROOT_UPGRADE=DENIED "+
              type(exc).__name__+":"+
              (str(exc)[:135] if isinstance(exc,RootUpdateDenied)
               else "SENSITIVE_DETAILS_REDACTED"),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
