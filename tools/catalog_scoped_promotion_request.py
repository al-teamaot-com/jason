"""Typed, nonprivileged Production Manager -> root-worker request transport.

This is never a deployment credential. A staged offer and a signed Owner
approval are independently validated by the installed root worker. New code
must not be used on a production host until a separate exact release approval
has installed and attested the trusted worker and automatic recovery.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
from typing import Any, Mapping
from uuid import uuid4

from tools.catalog_scoped_promotion import (
    ADMISSION_RECEIPT_SHA256, validate_offer, fail,
)

ACTIONS=frozenset({"catalog_scope_stage", "catalog_scope_promote", "catalog_scope_recover"})
SHA=re.compile(r"^[a-f0-9]{40}$")
RID=re.compile(r"^release-[a-f0-9]{16}$")
HEX=re.compile(r"^[a-f0-9]{64}$")
EXPECTED_ROOT_WORKER=Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
AUTH_ROOT=Path('/var/lib/jason/authority/catalog-scoped-release')


def exact_request(action:str, *,release_id:str, source_revision:str,
                  offer_sha256:str|None=None)->dict[str,Any]:
    if (action not in ACTIONS or not isinstance(release_id,str)
            or RID.fullmatch(release_id) is None
            or not isinstance(source_revision,str) or SHA.fullmatch(source_revision) is None):
        fail("ROOT_REQUEST_IDENTITY_INVALID")
    request={
        "schema_version":"1.0", "request_id":uuid4().hex,
        "source_revision":source_revision,"action":action,
        "release_id":release_id,
        "admission_receipt_sha256":ADMISSION_RECEIPT_SHA256,
    }
    if action=="catalog_scope_stage":
        if offer_sha256 is not None:fail("STAGE_CANNOT_PREAPPROVE_OFFER")
    else:
        if not isinstance(offer_sha256,str) or HEX.fullmatch(offer_sha256) is None:
            fail("EXACT_OFFER_HASH_REQUIRED")
        request["offer_sha256"]=offer_sha256
    return request


def private_json(path:Path, *,owner_uid:int, max_bytes:int=16384)->dict[str,Any]:
    if path.is_symlink() or not path.is_file():fail("SOURCE_DOCUMENT_MISSING_OR_SYMLINK")
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=owner_uid
                or info.st_mode&0o077 or info.st_nlink!=1
                or not 1<=info.st_size<=max_bytes):
            fail("SOURCE_DOCUMENT_UNTRUSTED")
        raw=os.read(fd,max_bytes+1)
        if len(raw)!=info.st_size:fail("SOURCE_DOCUMENT_CHANGED")
    finally:os.close(fd)
    try:doc=json.loads(raw)
    except (ValueError,TypeError) as exc:
        raise PermissionError("CATALOG_SCOPED_REQUEST_SOURCE_JSON_INVALID") from exc
    if not isinstance(doc,dict):fail("SOURCE_DOCUMENT_SHAPE_INVALID")
    return doc


def precheck_owner_approval(state_root:Path,offer:Mapping[str,Any])->None:
    """Low-trust precheck only: root independently verifies original signature."""
    release_id=offer["release_id"]
    uid=os.getuid()
    approvals=state_root/"owner-approvals"/(release_id+".json")
    payload=private_json(approvals,owner_uid=uid)
    if (payload.get("release_id")!=release_id
            or payload.get("candidate_sha")!=offer["candidate_sha"]
            or payload.get("manifest_sha256")!=offer["manifest_sha256"]
            or payload.get("standing_authority") is not False
            or payload.get("production_mutation") is not False
            or not isinstance(payload.get("signed_owner_proof"),dict)):
        fail("SIGNED_OWNER_REQUEST_PRECHECK_REJECTED")


def precheck_scoped_offer(state_root:Path,release_id:str,source_revision:str,
                          *,for_promotion:bool)->dict[str,Any]:
    offer_path=state_root/"offers"/(release_id+".json")
    offer=validate_offer(private_json(offer_path,owner_uid=os.getuid()))
    if offer["release_id"]!=release_id or offer["protected_main_sha"]!=source_revision:
        fail("OFFER_CURRENT_SOURCE_MISMATCH")
    if for_promotion:
        precheck_owner_approval(state_root,offer)
    return offer


def root_worker_installed(*,script:Path=EXPECTED_ROOT_WORKER)->None:
    """Require a distinct root-installed worker with the new exact action."""
    if script.is_symlink() or not script.is_file():fail("ROOT_WORKER_NOT_INSTALLED")
    info=script.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
            or info.st_mode&0o022 or info.st_nlink!=1 or info.st_size>262144):
        fail("ROOT_WORKER_UNTRUSTED")
    content=script.read_bytes()
    # The exact trusted source pin and full code digest are enforced by the
    # root operator's separate signed installer, not this mutable client.
    if (b"catalog_scope_promote" not in content or
            b"_trusted_catalog_scoped_promotion_module" not in content):
        fail("SCOPED_ROOT_WORKER_NOT_ACTIVATED")


def submit_to_native_worker(
    state_root:Path, request:Mapping[str,Any],*,
    worker_path:Path=EXPECTED_ROOT_WORKER,
)->dict[str,Any]:
    """Atomically enqueue only one strictly typed request, never run Docker."""
    expected=exact_request(request.get("action"),
        release_id=request.get("release_id"),
        source_revision=request.get("source_revision"),
        offer_sha256=request.get("offer_sha256"))
    if set(expected)!=set(request) or request.get("schema_version")!="1.0":
        fail("ROOT_REQUEST_SCHEMA_INVALID")
    request_id=str(request.get("request_id") or "")
    if not re.fullmatch(r"[a-f0-9]{32}",request_id):fail("ROOT_REQUEST_ID_INVALID")
    root_worker_installed(script=worker_path)
    requests=state_root/"host-reconcile"/"requests"
    results=state_root/"host-reconcile"/"results"
    for directory in (requests,results):
        if directory.is_symlink() or not directory.is_dir():fail("NATIVE_HOST_SPOOL_MISSING")
        info=directory.lstat()
        if info.st_uid!=os.getuid() or info.st_mode&0o002:
            fail("NATIVE_HOST_SPOOL_UNSAFE")
    path=requests/(request_id+".json")
    if path.exists() or path.is_symlink():fail("DUPLICATE_ROOT_REQUEST")
    payload=json.dumps(dict(request),sort_keys=True,separators=(",", ":")).encode()+b"\n"
    if len(payload)>4096:fail("ROOT_REQUEST_TOO_LARGE")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with os.fdopen(fd,"wb",closefd=False) as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
    finally:os.close(fd)
    return {"status":"queued_for_independent_root_validation_not_deployed",
            "request_id":request_id,"source_revision":request["source_revision"],
            "release_id":request["release_id"],"action":request["action"],
            "result_not_yet_verified":True}
