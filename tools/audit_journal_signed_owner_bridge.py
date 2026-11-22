#!/usr/bin/env python3
"""One archive-only, Root-admitted signed ChatGPT Owner authorization.

Root publishes a read-only exact-scope offer. Jason's authenticated MCP
Owner signs that offer using its existing pinned Ed25519 signer. The Root
installer rechecks original offer, production facts and the signature before
making ONE irreversible one-use claim and invoking the original installer.

Source-only. This does NOT create a Root execution path or enable an issuer.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any,Mapping

ACTION="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
DECISION="APPROVE_EXACT_DAILY_AUDIT_JOURNAL_ARCHIVE"
TENANT="f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
STAGED=Path("/var/lib/jason-owner-release/audit-journal-signed-stage")
PUBLIC=Path("/var/lib/jason/authority/audit-journal-release")
ROOT_TRUST=Path("/etc/jason-owner-release/verified-owner-public-key.json")
ARCHIVE="/srv/jason/archive/governed-audit/orchestration"
HEX40=re.compile(r"[a-f0-9]{40}\Z")
HEX64=re.compile(r"[a-f0-9]{64}\Z")
OWNER_PRINCIPAL="person-entra-bee80bdcffb04c50b453c09d4d411f5f"

class ArchiveOwnerDenied(PermissionError):pass
def need(ok,reason):
    if not ok:raise ArchiveOwnerDenied("AUDIT_JOURNAL_SIGNED_ROOT_"+reason)
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(raw):return sha256(raw).hexdigest()
def timestamp():
    return datetime.now(timezone.utc).isoformat()
def verified_public_dir(path,owner=1000,mode=0o700):
    x=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(x.st_mode)
         and x.st_uid==owner and stat.S_IMODE(x.st_mode)==mode,
         "PUBLIC_DIRECTORY_CUSTODY")
def stage_directories_once():
    """Root-only creation of authorization spools, not deployment targets."""
    need(os.geteuid()==0,"ROOT_STAGE_DIRECTORY_CREATION_REQUIRED")
    verified_public_dir(PUBLIC.parent)
    verified_public_dir(STAGED.parent,0,0o700)
    for path,owner in ((STAGED,0),(PUBLIC,1000),
                       (PUBLIC/"offers",1000),
                       (PUBLIC/"owner-approvals",1000)):
        if not os.path.lexists(path):
            path.mkdir(mode=0o700)
            os.chown(path,owner,owner)
            os.chmod(path,0o700)
        verified_public_dir(path,owner,0o700)


def private_file(path,owner,mode,maximum=1_000_000):
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid==owner and stat.S_IMODE(info.st_mode)==mode
         and info.st_nlink==1 and 0<info.st_size<=maximum,
         "EXACT_RECORD_CUSTODY")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        fd_info=os.fstat(fd)
        need((fd_info.st_dev,fd_info.st_ino,fd_info.st_size)==
             (info.st_dev,info.st_ino,info.st_size),
             "EXACT_RECORD_CHANGED")
        raw=os.read(fd,maximum+1)
        need(len(raw)==info.st_size,"EXACT_RECORD_SHORT_READ")
        return raw
    finally:os.close(fd)
def private_json(path,owner,mode,maximum=1_000_000):
    data=json.loads(private_file(path,owner,mode,maximum))
    need(isinstance(data,dict),"ROOT_JSON_OBJECT_REQUIRED")
    return data
def exclusive(path,raw,owner,mode):
    need(not os.path.lexists(path),"ONE_USE_RECORD_ALREADY_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb",closefd=False) as f:
            os.fchmod(fd,mode)
            if os.geteuid()==0:os.fchown(fd,owner,owner)
            f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory)
    finally:os.close(directory)

def freeze_proof():
    raw=private_file(FREEZE,1000,0o600,4096)
    p=json.loads(raw)
    need(p.get("schema_version")=="1.0"
         and p.get("status")=="active"
         and p.get("scope")=="manual-and-automatic-production-promotions"
         and p.get("release_exception")=="none approved"
         and "exact-SHA owner unfreeze decision" in p.get("remove_only_after",""),
         "ORIGINAL_GLOBAL_FREEZE_NOT_PRESERVED")
    return digest(raw)

def manifest(scope,candidate,freeze_sha,root_gate):
    need(scope.get("action")==ACTION and
         scope.get("policy")=={
             "candidate_sha":candidate,"rollback_sha":ROLLBACK},
         "EXACT_REVIEWED_ARCHIVE_SCOPE_REQUIRED")
    need(root_gate.get("breaker")=="closed"
         and root_gate.get("drift")=="pass"
         and root_gate.get("peers_verified") is True
         and root_gate.get("mount_verified") is True,
         "NATIVE_ROOT_GATE_UNAVAILABLE")
    return {
        "schema_version":"1.0","action":ACTION,
        "candidate_sha":candidate,"rollback_sha":ROLLBACK,
        "scope_sha256":digest(canon(scope)),
        "freeze_sha256":freeze_sha,
        "archive_root":ARCHIVE,"journal_only":True,
        "one_use":True,"standing_authority":False,
        "provider_mutations":False,
        "availability_interruption_authorized":True,
    }

def create_staged_offer(scope,candidate,root_gate):
    """Only Root can attest live exact stage; no release/producer mutation."""
    need(os.geteuid()==0 and re.fullmatch("[a-f0-9]{40}",candidate or ""),
         "ROOT_EXACT_CANDIDATE_REQUIRED")
    frozen=freeze_proof()
    m=manifest(scope,candidate,frozen,root_gate)
    now=timestamp()
    release_id="release-"+candidate[:16]
    stage={
       "schema_version":"1.0","action":ACTION,
       "release_id":release_id,"candidate_sha":candidate,
       "owner_oid":OWNER,"rollback_sha":ROLLBACK,
       "scope":scope,"scope_sha256":digest(canon(scope)),
       "manifest":m,"manifest_sha256":digest(canon(m)),
       "freeze_sha256":frozen,"root_gate":root_gate,
       "staged_at":now,"production_mutations":False,
       "owner_approval_issued":False,
    }
    offer={
       "schema_version":"1.0","action":ACTION,
       "release_id":release_id,"candidate_sha":candidate,
       "rollback_sha":ROLLBACK,"scope_sha256":stage["scope_sha256"],
       "manifest_sha256":stage["manifest_sha256"],
       "freeze_sha256":frozen,"archive_root":ARCHIVE,
       "owner_oid":OWNER,"production_breaker_verified":True,
       "production_drift_verified":True,"protected_peers_verified":True,
       "separate_archive_mount_verified":True,"journal_only":True,
       "availability_interruption_authorized":True,
       "one_use":True,"standing_authority":False,
       "production_mutations":False,"root_stage_receipt_sha256":digest(canon(stage)),
       "prepared_at":now,
    }
    stage_directories_once()
    stage_file=STAGED/(release_id+".json")
    public_file=PUBLIC/"offers"/(release_id+".json")
    need(not os.path.lexists(stage_file) and not os.path.lexists(public_file),
         "STAGE_ALREADY_PUBLISHED")
    exclusive(stage_file,canon(stage),0,0o400)
    exclusive(public_file,canon(offer),1000,0o600)
    return offer

def verify_previously_signed_root_offer(scope,candidate,root_gate):
    """Return authenticated Owner evidence; no mutation, no Entra challenge."""
    from kernel.signed_owner_release import (
        read_pinned_root_owner_public_key,verify_exact_owner_release,
    )
    need(os.geteuid()==0 and HEX40.fullmatch(candidate or "") is not None,
         "ROOT_EXACT_RELEASE_REQUIRED")
    release_id="release-"+candidate[:16]
    verified_public_dir(STAGED,0,0o700)
    verified_public_dir(PUBLIC)
    verified_public_dir(PUBLIC/"offers")
    verified_public_dir(PUBLIC/"owner-approvals")
    stage=private_json(STAGED/(release_id+".json"),0,0o400,1_000_000)
    offer=private_json(PUBLIC/"offers"/(release_id+".json"),1000,0o600,16384)
    signed=private_json(PUBLIC/"owner-approvals"/(release_id+".json"),1000,0o600,16384)
    expected=manifest(scope,candidate,freeze_proof(),root_gate)
    need(stage.get("schema_version")=="1.0"
         and stage.get("action")==ACTION and stage.get("release_id")==release_id
         and stage.get("candidate_sha")==candidate
         and stage.get("rollback_sha")==ROLLBACK
         and stage.get("scope")==scope
         and stage.get("scope_sha256")==digest(canon(scope))
         and stage.get("manifest")==expected
         and stage.get("manifest_sha256")==digest(canon(expected))
         and stage.get("freeze_sha256")==expected["freeze_sha256"]
         and stage.get("owner_oid")==OWNER
         and stage.get("root_gate")==root_gate
         and stage.get("production_mutations") is False
         and stage.get("owner_approval_issued") is False,
         "ROOT_STAGE_EVIDENCE_CHANGED")
    now=datetime.now(timezone.utc)
    earlier=datetime.fromisoformat(stage["staged_at"])
    need(earlier.tzinfo is not None and
         0 <= (now-earlier).total_seconds()<=600,
         "ROOT_STAGE_EXPIRED")
    need(offer=={
       "schema_version":"1.0","action":ACTION,
       "release_id":release_id,"candidate_sha":candidate,
       "rollback_sha":ROLLBACK,"scope_sha256":stage["scope_sha256"],
       "manifest_sha256":stage["manifest_sha256"],
       "freeze_sha256":stage["freeze_sha256"],"archive_root":ARCHIVE,
       "owner_oid":OWNER,"production_breaker_verified":True,
       "production_drift_verified":True,"protected_peers_verified":True,
       "separate_archive_mount_verified":True,"journal_only":True,
       "availability_interruption_authorized":True,"one_use":True,
       "standing_authority":False,"production_mutations":False,
       "root_stage_receipt_sha256":digest(canon(stage)),
       "prepared_at":stage["staged_at"],
    },"PUBLIC_OFFER_CHANGED")
    need(signed.get("schema_version")=="1.0"
         and signed.get("action")==ACTION
         and signed.get("release_id")==release_id
         and signed.get("candidate_sha")==candidate
         and signed.get("scope_sha256")==stage["scope_sha256"]
         and signed.get("manifest_sha256")==stage["manifest_sha256"]
         and signed.get("root_stage_receipt_sha256")==digest(canon(stage))
         and signed.get("standing_authority") is False
         and signed.get("owner_approval_is_one_use") is True
         and signed.get("production_mutations") is False
         and isinstance(signed.get("signed_owner_proof"),dict)
         and set(signed)=={
             "schema_version","action","release_id","candidate_sha",
             "scope_sha256","manifest_sha256","root_stage_receipt_sha256",
             "signed_owner_proof","standing_authority",
             "owner_approval_is_one_use","production_mutations"
         }, "SIGNED_OWNER_REQUEST_NOT_EXACT")
    key=read_pinned_root_owner_public_key(ROOT_TRUST)
    proof=verify_exact_owner_release(
        signed["signed_owner_proof"],public_key=key,
        expected_candidate_sha=candidate,expected_rollback_sha=ROLLBACK,
        expected_release_id=release_id,
        expected_scope_sha256=stage["scope_sha256"],
        expected_manifest_sha256=stage["manifest_sha256"],
        expected_freeze_sha256=stage["freeze_sha256"],at=now,
    )
    need(proof.get("owner_oid")==OWNER
         and proof.get("owner_principal")==OWNER_PRINCIPAL
         and proof.get("tenant_id")==TENANT
         and proof.get("one_release_only") is True
         and proof.get("standing_authority") is False,
         "SIGNED_OWNER_NOT_LICENSED_EXACT_OWNER")
    consumed=STAGED/(release_id+".consumed.json")
    need(not os.path.lexists(consumed),
         "SIGNED_OWNER_APPROVAL_CONSUMED")
    return {
        "release_id":release_id,"candidate_sha":candidate,
        "scope_sha256":stage["scope_sha256"],
        "root_stage_receipt_sha256":digest(canon(stage)),
        "signed_owner_proof_sha256":digest(canon(signed["signed_owner_proof"])),
        "approval_id":proof["approval_id"],"owner_oid":OWNER,
        "verified_at":timestamp(),"same_scope_recheck_passed":True,
        "standalone_archive_only":True,
        "new_global_unfreeze":False,
    }

def consume_one_use(candidate,proof):
    need(os.geteuid()==0 and proof.get("candidate_sha")==candidate
         and proof.get("owner_oid")==OWNER
         and proof.get("same_scope_recheck_passed") is True
         and proof.get("standalone_archive_only") is True
         and proof.get("new_global_unfreeze") is False,
         "EXACT_OWNER_CONSUMPTION_REQUIRED")
    verified_public_dir(STAGED,0,0o700)
    target=STAGED/("release-"+candidate[:16]+".consumed.json")
    exclusive(target,canon(proof),0,0o400)
    return target
