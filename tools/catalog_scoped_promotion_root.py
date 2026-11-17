#!/usr/bin/env python3
"""Trusted root callback for the EXISTING Jason Production Manager host worker.

SOURCE ONLY. This is not a root installer; it must be hash-pinned and
separately installed, and the existing host-reconcile worker must be upgraded
under an exact authorized release before any request can execute it.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
from typing import Any,Mapping

from tools.catalog_scoped_promotion import (
    ADMISSION_RECEIPT_SHA256, ADMISSION_EVIDENCE_PATH,
    validate_offer,make_offer,promote_scoped_catalog_pair,fail,
)
from tools.catalog_scoped_release_admission import attest_source_scope,load_manifest
from tools.catalog_scoped_promotion_host import (
    NativeCatalogHost,STATE,ROOT,SOURCE_REPO,NATIVE,secure_read,atomic_root_json,
)

ID=re.compile(r'^release-[0-9a-f]{16}$')
AUTH_ROOT=Path('/var/lib/jason/authority/catalog-scoped-release')
ACTS=frozenset({'catalog_scope_stage','catalog_scope_promote','catalog_scope_recover'})


def _trusted_public_offer(offer:Mapping[str,Any]):
    public=AUTH_ROOT/'offers'
    uid=pwd.getpwnam('al').pw_uid
    gid=pwd.getpwnam('al').pw_gid
    if public.is_symlink() or not AUTH_ROOT.is_dir() or AUTH_ROOT.is_symlink():
        fail('PUBLIC_CATALOG_APPROVAL_ROOT_NOT_INSTALLED')
    if (AUTH_ROOT.stat().st_uid!=uid
            or stat.S_IMODE(AUTH_ROOT.stat().st_mode)!=0o700):
        fail('PUBLIC_CATALOG_APPROVAL_ROOT_UNTRUSTED')
    if not public.exists():
        public.mkdir(mode=0o700)
        os.chown(public,uid,gid)
    info=public.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=0o700:
        fail('PUBLIC_OFFER_DIRECTORY_UNTRUSTED')
    path=public/(offer['release_id']+'.json')
    content=json.dumps(dict(offer),sort_keys=True,separators=(',',':')).encode()+b'\n'
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_bytes()!=content:
            fail('PUBLIC_OFFER_CONFLICT')
        return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as h:
            h.write(content);h.flush();os.fsync(h.fileno())
        os.chown(path,uid,gid,follow_symlinks=False)
    finally:os.close(fd)


def _root_offer_path(release_id:str)->Path:
    if not isinstance(release_id,str) or ID.fullmatch(release_id) is None:
        fail('RELEASE_ID_INVALID')
    return ROOT/'offers'/(release_id+'.json')


def _load_root_offer(release_id:str)->dict[str,Any]:
    offer=json.loads(secure_read(_root_offer_path(release_id),max_bytes=16384))
    validate_offer(offer)
    if offer['release_id']!=release_id:
        fail('ROOT_OFFER_ID_MISMATCH')
    return offer


def _signed_approval(release_id:str,offer:Mapping[str,Any])->Mapping[str,Any]:
    uid=pwd.getpwnam('al').pw_uid
    path=AUTH_ROOT/'owner-approvals'/(release_id+'.json')
    request=json.loads(secure_read(path,max_bytes=16384,uid=uid))
    if (set(request)!={'schema_version','authorization','release_id',
            'candidate_sha','manifest_sha256','approved_by','organization_id',
            'signed_owner_proof','standing_authority','production_mutation'}
            or request['schema_version']!='1.0'
            or request['authorization']!='fresh_entra_catalog_scoped_owner'
            or request['release_id']!=release_id
            or request['candidate_sha']!=offer['candidate_sha']
            or request['manifest_sha256']!=offer['manifest_sha256']
            or request['organization_id']!='aot'
            or request['standing_authority'] is not False
            or request['production_mutation'] is not False
            or not isinstance(request['signed_owner_proof'],Mapping)):
        fail('SIGNED_OWNER_APPROVAL_REQUEST_MISMATCH')
    if request['approved_by']!=request['signed_owner_proof'].get('payload',{}).get('owner_principal'):
        fail('SIGNED_OWNER_REQUEST_IDENTITY_MISMATCH')
    return request['signed_owner_proof']


def execute_native_catalog_scoped_request(
    request:Mapping[str,Any],*,repo:Path=SOURCE_REPO,
    native_ci_checks:Any=None,
)->dict[str,Any]:
    """Accept only one native typed request; no raw shell, Docker, or paths."""
    if (not isinstance(request,Mapping)
            or request.get('action') not in ACTS
            or not isinstance(request.get('request_id'),str)
            or not re.fullmatch(r'[0-9a-f]{32}',request['request_id'])
            or not isinstance(request.get('source_revision'),str)
            or not re.fullmatch(r'[0-9a-f]{40}',request['source_revision'])
            or not isinstance(request.get('release_id'),str)
            or ID.fullmatch(request['release_id']) is None
            or request.get('admission_receipt_sha256')!=ADMISSION_RECEIPT_SHA256):
        fail('ROOT_REQUEST_SCOPE_INVALID')
    action=request['action']
    if set(request)!=({'schema_version','action','request_id','source_revision',
                       'release_id','admission_receipt_sha256'}
                      if action=='catalog_scope_stage' else
                      {'schema_version','action','request_id','source_revision',
                       'release_id','admission_receipt_sha256','offer_sha256'}):
        fail('ROOT_REQUEST_UNEXPECTED_KEYS')
    if request['schema_version']!='1.0':fail('ROOT_REQUEST_SCHEMA_INVALID')
    host=NativeCatalogHost(repo=repo)
    host.enforce_installed_production_trust()
    if native_ci_checks is None:
        # Read-only, root-pinned CI attestor with the same protected check
        # names as the existing Production Manager plus SEC-007.
        from tools.catalog_scoped_protected_ci import check_catalog_protected_ci
        native_ci_checks=lambda sha:check_catalog_protected_ci(sha,repo=repo)
    if action=='catalog_scope_stage':
        fresh=attest_source_scope(repo,native_ci_checks=native_ci_checks,
                                  preflight_script=NATIVE)
        manifest=load_manifest(repo,main_sha=fresh['protected_source']['verified_main_sha'])
        historical_path=Path('/usr/local/lib/jason/catalog-scoped-promotion')/ADMISSION_EVIDENCE_PATH
        historical=json.loads(secure_read(historical_path,mode=0o644,max_bytes=10000))
        offer=make_offer(manifest,historical,fresh)
        if offer['release_id']!=request['release_id'] or offer['protected_main_sha']!=request['source_revision']:
            fail('ROOT_OFFER_SOURCE_CHANGED')
        path=_root_offer_path(offer['release_id'])
        if path.exists() or path.is_symlink():
            current=_load_root_offer(offer['release_id'])
            if current!=offer:fail('ROOT_OFFER_STALE_OR_DIFFERENT')
        else:
            atomic_root_json(path,offer)
        _trusted_public_offer(offer)
        return {'status':'catalog_offer_staged_without_mutation',
                'release_id':offer['release_id'],'source_sha':offer['protected_main_sha'],
                'candidate_sha':offer['candidate_sha'],
                'manifest_sha256':offer['manifest_sha256'],
                'admission_receipt_sha256':ADMISSION_RECEIPT_SHA256,
                'owner_approval_required':True,'production_mutations':False}
    offer=_load_root_offer(request['release_id'])
    if (offer['protected_main_sha']!=request['source_revision']
            or offer['manifest_sha256']!=request['offer_sha256']):
        fail('ROOT_REQUEST_OFFER_MISMATCH')
    if action=='catalog_scope_recover':
        return host.recover_interrupted(offer)
    signed=_signed_approval(offer['release_id'],offer)
    return promote_scoped_catalog_pair(offer,signed,host=host)
