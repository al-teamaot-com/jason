#!/usr/bin/env python3
"""Issue one fresh exact Owner release decision with immutable expired-proof lineage.

Source-only. Caller must supply a separately verified fresh Entra Owner token
and exact terminal decision. This only stores a new signed decision; root
independently re-verifies lineage and consumes it inside native production lock.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any,Mapping
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
    verify_exact_owner_release, canonical,
)
from implementation.kernel.catalog_scoped_promotion_contract import validate_offer

APPROVAL_WORDS = "APPROVE_EXACT_CATALOG_SCOPED_RUNTIME_MCP_RENEWAL"
OWNER_APPROVAL_KEYS = {
    "schema_version","authorization","release_id","candidate_sha",
    "manifest_sha256","approved_by","organization_id","signed_owner_proof",
    "standing_authority","production_mutation",
}
RENEWAL_KEYS=OWNER_APPROVAL_KEYS|{
    "predecessor_approval_id","predecessor_signed_owner_proof_sha256",
}
ID=re.compile(r"owner-mcp-[0-9a-f]{32}\Z")


class CatalogOwnerRenewalDenied(PermissionError):
    pass


def fail(reason:str):
    raise CatalogOwnerRenewalDenied("CATALOG_OWNER_RENEWAL_DENIED_"+reason)


def safe_read(path:Path,max_bytes=16384)->dict:
    if path.is_symlink():fail("OWNER_RECORD_SYMLINK")
    info=path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1
            or info.st_size<1 or info.st_size>max_bytes):
        fail("OWNER_RECORD_UNTRUSTED")
    try:return json.loads(path.read_bytes())
    except (TypeError,ValueError,OSError) as exc:
        raise CatalogOwnerRenewalDenied("CATALOG_OWNER_RENEWAL_DENIED_OWNER_RECORD_INVALID") from exc


def _historically_verified(row:Mapping[str,Any],offer:Mapping[str,Any],
                           signer:Ed25519PrivateKey,*,renewal:bool):
    if (not isinstance(row,dict)
            or set(row)!=(RENEWAL_KEYS if renewal else OWNER_APPROVAL_KEYS)
            or row.get("schema_version")!="1.0"
            or row.get("authorization")!=("fresh_entra_catalog_scoped_owner_renewal"
                                          if renewal else "fresh_entra_catalog_scoped_owner")
            or row.get("release_id")!=offer["release_id"]
            or row.get("candidate_sha")!=offer["candidate_sha"]
            or row.get("organization_id")!="aot"
            or row.get("standing_authority") is not False
            or row.get("production_mutation") is not False):
        fail("HISTORICAL_RECORD_SCOPE_INVALID")
    signed=row.get("signed_owner_proof")
    if not isinstance(signed,dict) or not isinstance(signed.get("payload"),dict):
        fail("HISTORICAL_PROOF_MISSING")
    payload=signed["payload"]
    if (row["approved_by"]!=payload.get("owner_principal")
            or row["manifest_sha256"]!=payload.get("manifest_sha256")
            or payload.get("rollback_sha")!=offer["rollback_sha"]
            or payload.get("scope_sha256")!=offer["scope_sha256"]
            or payload.get("freeze_sha256")!=offer["freeze_sha256"]):
        fail("HISTORICAL_PROOF_BINDING_MISMATCH")
    try:
        issue=datetime.fromisoformat(payload["issued_at"])
        expires=datetime.fromisoformat(payload["expires_at"])
        verify_exact_owner_release(
            signed,public_key=signer.public_key(),
            expected_candidate_sha=offer["candidate_sha"],
            expected_rollback_sha=offer["rollback_sha"],
            expected_release_id=offer["release_id"],
            expected_scope_sha256=offer["scope_sha256"],
            expected_manifest_sha256=row["manifest_sha256"],
            expected_freeze_sha256=offer["freeze_sha256"],
            at=issue+timedelta(seconds=1))
    except Exception as exc:
        raise CatalogOwnerRenewalDenied("CATALOG_OWNER_RENEWAL_DENIED_PREDECESSOR_PROOF_INVALID") from exc
    return signed,issue,expires


def queue_exact_catalog_owner_renewal(
    *,state_root:Path,release_id:str,candidate_sha:str,manifest_sha256:str,
    approved_by:str,organization_id:str,verified_token_claims:Mapping[str,Any],
    service_signer:Ed25519PrivateKey,affirmative_decision:str,
    lock_path:Path=Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock"),
)->dict[str,Any]:
    if affirmative_decision!=APPROVAL_WORDS:fail("EXACT_OWNER_TERMINAL_DECISION_REQUIRED")
    if (not isinstance(service_signer,Ed25519PrivateKey)
            or not isinstance(verified_token_claims,Mapping)
            or organization_id!="aot"
            or verified_token_claims.get("tid")!="f7054323-d52b-4863-8c2f-1898f0b6077c"
            or verified_token_claims.get("oid") not in EXACT_OWNER_OAUTH_SUBJECTS
            or approved_by!=EXACT_OWNER_OAUTH_SUBJECTS[verified_token_claims["oid"]]):
        fail("FRESH_ENTRA_OWNER_REQUIRED")
    source=state_root/"offers"/(release_id+".json")
    lockfd=os.open(lock_path,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
    try:
        lock=os.fstat(lockfd)
        if (lock_path.is_symlink() or not stat.S_ISREG(lock.st_mode)
                or lock.st_uid!=os.getuid() or lock.st_mode&0o002):
            fail("NATIVE_LOCK_UNTRUSTED")
        try:fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:fail("OTHER_PRODUCTION_RELEASE_IN_PROGRESS")
        offer=validate_offer(safe_read(source))
        if (offer["release_id"]!=release_id
                or offer["candidate_sha"]!=candidate_sha
                or offer["manifest_sha256"]!=manifest_sha256):
            fail("SOURCE_MANIFEST_OR_CANDIDATE_CHANGED")
        primary=safe_read(state_root/"owner-approvals"/(release_id+".json"))
        predecessor,_,previous_expiry=_historically_verified(
            primary,offer,service_signer,renewal=False)
        original_oid=predecessor["payload"]["owner_oid"]
        if verified_token_claims["oid"]!=original_oid:
            fail("RENEWAL_OWNER_IDENTITY_NOT_ORIGINAL")
        parent=state_root/"owner-approval-renewals"
        folder=parent/release_id
        if not parent.exists():
            parent.mkdir(mode=0o700)
        if (parent.is_symlink() or parent.stat().st_uid!=os.getuid()
                or stat.S_IMODE(parent.stat().st_mode)!=0o700):
            fail("RENEWAL_PARENT_DIRECTORY_UNTRUSTED")
        if not folder.exists():
            folder.mkdir(mode=0o700)
        if (folder.is_symlink() or folder.stat().st_uid!=os.getuid()
                or stat.S_IMODE(folder.stat().st_mode)!=0o700):
            fail("RENEWAL_DIRECTORY_UNTRUSTED")
        existing={}
        for file in folder.iterdir():
            if file.suffix!=".json" or ID.fullmatch(file.stem) is None:
                fail("RENEWAL_UNEXPECTED_FILE")
            row=safe_read(file)
            current=row.get("signed_owner_proof",{})
            if current.get("payload",{}).get("approval_id")!=file.stem:
                fail("RENEWAL_SIGNED_PROOF_ID_MISMATCH")
            existing[file.stem]=row
        if len(existing)>=8:fail("RENEWAL_CHAIN_EXHAUSTED")
        ancestry=set()
        while existing:
            previous_id=predecessor["payload"]["approval_id"]
            children=[(key,row) for key,row in existing.items()
                      if row.get("predecessor_approval_id")==previous_id]
            if len(children)!=1:fail("RENEWAL_CHAIN_AMBIGUOUS")
            key,row=children[0]
            if key in ancestry or row.get("predecessor_signed_owner_proof_sha256")!=sha256(canonical(predecessor)).hexdigest():
                fail("RENEWAL_LINEAGE_CHANGED")
            next_proof,issued,next_expiry=_historically_verified(
                row,offer,service_signer,renewal=True)
            if issued<previous_expiry or next_proof["payload"]["owner_oid"]!=original_oid:
                fail("RENEWAL_PREDECESSOR_NOT_EXPIRED")
            ancestry.add(key)
            del existing[key]
            predecessor=next_proof
            previous_expiry=next_expiry
        now=datetime.now(timezone.utc)
        if now<previous_expiry:fail("PREDECESSOR_NOT_EXPIRED")
        new_signed=issue_exact_owner_release(
            approval_id="owner-mcp-"+uuid4().hex,
            release_id=offer["release_id"],candidate_sha=offer["candidate_sha"],
            rollback_sha=offer["rollback_sha"],scope_sha256=offer["scope_sha256"],
            manifest_sha256=offer["manifest_sha256"],
            freeze_sha256=offer["freeze_sha256"],
            verified_tenant_id=str(verified_token_claims["tid"]),
            verified_owner_oid=str(verified_token_claims["oid"]),
            verified_principal=approved_by,verified_organization_id=organization_id,
            confirmed_decision="approve",at=now,private_key=service_signer)
        verify_exact_owner_release(
            new_signed,public_key=service_signer.public_key(),
            expected_candidate_sha=offer["candidate_sha"],
            expected_rollback_sha=offer["rollback_sha"],
            expected_release_id=offer["release_id"],
            expected_scope_sha256=offer["scope_sha256"],
            expected_manifest_sha256=offer["manifest_sha256"],
            expected_freeze_sha256=offer["freeze_sha256"],at=now)
        payload={
            "schema_version":"1.0",
            "authorization":"fresh_entra_catalog_scoped_owner_renewal",
            "release_id":release_id,"candidate_sha":candidate_sha,
            "manifest_sha256":manifest_sha256,
            "approved_by":approved_by,"organization_id":"aot",
            "signed_owner_proof":new_signed,
            "standing_authority":False,"production_mutation":False,
            "predecessor_approval_id":predecessor["payload"]["approval_id"],
            "predecessor_signed_owner_proof_sha256":sha256(canonical(predecessor)).hexdigest(),
        }
        path=folder/(new_signed["payload"]["approval_id"]+".json")
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            with os.fdopen(fd,"wb",closefd=False) as stream:
                stream.write(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()+b"\n")
                stream.flush();os.fsync(stream.fileno())
        finally:os.close(fd)
        return {"status":"renewal_signed_once_not_deployed",
                "release_id":release_id,"manifest_sha256":manifest_sha256,
                "approval_id":new_signed["payload"]["approval_id"],
                "predecessor_approval_id":payload["predecessor_approval_id"],
                "production_mutation":False,
                "owner_approval_is_one_use":True}
    finally:
        try:fcntl.flock(lockfd,fcntl.LOCK_UN)
        finally:os.close(lockfd)
