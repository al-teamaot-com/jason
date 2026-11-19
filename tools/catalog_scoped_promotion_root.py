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
import subprocess
import tempfile
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


class CatalogPMv4ProtectedHost(NativeCatalogHost):
    """Put independent Ticket Core and Runbook Management in native rollback gate.

    Called *inside* promote_scoped_catalog_pair's existing try/rollback block,
    so any post-image PMv4 regression triggers its original paired rollback.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._independent_pmv4_before=None

    @staticmethod
    def _independent_pmv4_readback():
        import sqlite3
        names=('jason-pmv4-ticket-core','jason-pmv4-shadow-gateway')
        proc=subprocess.run(['docker','inspect',*names],
                            capture_output=True,timeout=25,check=False)
        if proc.returncode:fail('INDEPENDENT_PMV4_DOCKER_UNAVAILABLE')
        try:images=json.loads(proc.stdout)
        except (ValueError,TypeError):fail('INDEPENDENT_PMV4_DOCKER_INVALID')
        if not isinstance(images,list) or len(images)!=2:
            fail('INDEPENDENT_PMV4_CONTAINERS_MISSING')
        containers={}
        for item in images:
            name=item['Name'].lstrip('/')
            health=(item['State'].get('Health') or {}).get('Status')
            if name not in names or item['State'].get('Running') is not True or health!='healthy':
                fail('INDEPENDENT_PMV4_TICKET_HEALTH_FAILED')
            containers[name]=(item['Id'],item['Image'],item['State']['StartedAt'])
        unit=subprocess.run(
            ['systemctl','show','jason-runbook-management-read.service',
             '-p','MainPID','-p','ActiveState','-p','SubState',
             '-p','ExecMainStatus','-p','ActiveEnterTimestamp'],
            capture_output=True,timeout=15,check=False,text=True)
        if unit.returncode:fail('INDEPENDENT_PMV4_RUNBOOK_QUERY_FAILED')
        fields=dict(x.split('=',1) for x in unit.stdout.splitlines() if '=' in x)
        if (fields.get('ActiveState')!='active' or fields.get('SubState')!='running'
                or not fields.get('MainPID') or fields.get('MainPID')=='0'):
            fail('INDEPENDENT_PMV4_RUNBOOK_NOT_RUNNING')
        uri='file:/var/lib/jason/openclaw/json-playbooks.sqlite3?mode=ro'
        try:
            db=sqlite3.connect(uri,uri=True,timeout=5)
            try:
                registry=(
                    db.execute('SELECT COUNT(*) FROM json_playbooks').fetchone()[0],
                    db.execute('SELECT MAX(generation) FROM json_playbook_registry_meta').fetchone()[0])
            finally:db.close()
        except sqlite3.Error as exc:
            raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_PMV4_REGISTRY_UNAVAILABLE') from exc
        return {'containers':containers,'runbook':fields,'registry':registry}

    def protected_container_snapshot(self):
        snapshot=super().protected_container_snapshot()
        if self._independent_pmv4_before is None:
            self._independent_pmv4_before=self._independent_pmv4_readback()
        return snapshot

    def verify_unchanged_protected_containers(self,original):
        super().verify_unchanged_protected_containers(original)
        if (self._independent_pmv4_before is None or
                self._independent_pmv4_readback()!=self._independent_pmv4_before):
            fail('INDEPENDENT_PMV4_REGRESSION_ROLLBACK_REQUIRED')


def _restage_unchanged_catalog_scope(host:NativeCatalogHost, offer:Mapping[str,Any]):
    """Refresh an UNSIGNED source-only offer when unrelated PMv4 main advances.

    Never modify an approved/consumed offer or an attempted deployment.
    Hold the native production lock, preserve exact original in root audit,
    and roll back both root/public offers if the second atomic write fails.
    """
    validate_offer(offer)
    path=_root_offer_path(offer['release_id'])
    public=AUTH_ROOT/'offers'/(offer['release_id']+'.json')
    approval=AUTH_ROOT/'owner-approvals'/(offer['release_id']+'.json')
    transaction=ROOT/'transactions'/(offer['release_id']+'.json')
    active=ROOT/'active.json'
    uid=pwd.getpwnam('al').pw_uid
    gid=pwd.getpwnam('al').pw_gid
    def no_prior_authority():
        if any(p.exists() or p.is_symlink() for p in (approval,transaction,active)):
            fail('OFFER_RESTAGE_EXISTING_APPROVAL_OR_TRANSACTION')
    def encoded(item):
        return json.dumps(dict(item),sort_keys=True,separators=(',',':')).encode()+b'\n'
    def existing():
        current=_load_root_offer(offer['release_id'])
        original=secure_read(path,max_bytes=16384)
        public_original=secure_read(public,uid=uid,max_bytes=16384)
        if original!=public_original or original!=encoded(current):
            fail('OFFER_RESTAGE_ROOT_PUBLIC_MISMATCH')
        return current,original
    def validate_scope(previous):
        mutable={'protected_main_sha','fresh_admission_receipt_sha256','manifest_sha256'}
        if (set(previous)!=set(offer)
                or any(previous[k]!=offer[k] for k in previous if k not in mutable)
                or previous['protected_main_sha']==offer['protected_main_sha']):
            fail('OFFER_RESTAGE_CATALOG_SCOPE_OR_MAIN_INVALID')
        # An unrelated PMv4 merge must not rewrite prior catalog scope. Fresh
        # attest_source_scope already independently validates the latest
        # source against reviewed catalog snapshot and protected CI.
        command=['git','-c',f'safe.directory={host.repo}','-C',str(host.repo),
                 'merge-base','--is-ancestor',
                 previous['protected_main_sha'],offer['protected_main_sha']]
        result=subprocess.run(command,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=15)
        if result.returncode:fail('OFFER_RESTAGE_MAIN_NOT_DESCENDANT')
    def public_replace(payload):
        folder=public.parent
        info=folder.lstat()
        if (folder.is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=0o700):
            fail('OFFER_RESTAGE_PUBLIC_DIRECTORY_UNTRUSTED')
        handle,name=tempfile.mkstemp(prefix='.catalog-offer-',dir=folder)
        try:
            os.fchown(handle,uid,gid)
            os.fchmod(handle,0o600)
            with os.fdopen(handle,'wb') as output:
                output.write(payload);output.flush();os.fsync(output.fileno())
            os.replace(name,public)
            fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:
            if os.path.exists(name):os.unlink(name)
    no_prior_authority()
    old,oldbytes=existing()
    validate_scope(old)
    with host.transaction_lock(offer):
        no_prior_authority()
        same,raw=existing()
        if raw!=oldbytes or same!=old:fail('OFFER_RESTAGE_CHANGED_AFTER_LOCK')
        host._frozen(offer)
        # Avoid stale-main writes or a concurrent source advance after the
        # independently verified new offer was constructed.
        remote=subprocess.run(
            ['git','-c',f'safe.directory={host.repo}','-C',str(host.repo),
             'ls-remote','origin','refs/heads/main'],
            capture_output=True,timeout=25,check=False)
        if (remote.returncode or remote.stdout.decode().split()[:1]
                !=[offer['protected_main_sha']]):
            fail('OFFER_RESTAGE_MAIN_ADVANCED')
        history=ROOT/'superseded-source-only-offers'
        if not history.exists():
            history.mkdir(mode=0o700)
        info=history.lstat()
        if (history.is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700):
            fail('OFFER_RESTAGE_AUDIT_DIRECTORY_UNTRUSTED')
        audit=history/(offer['release_id']+'-'+old['manifest_sha256']+'.json')
        if audit.exists() or audit.is_symlink():
            if secure_read(audit,max_bytes=16384)!=oldbytes:
                fail('OFFER_RESTAGE_AUDIT_CONFLICT')
        else:
            handle=os.open(audit,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
                           getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(handle,'wb') as output:
                output.write(oldbytes);output.flush();os.fsync(output.fileno())
        updated=encoded(offer)
        root_changed=False
        public_changed=False
        try:
            atomic_root_json(path,offer)
            root_changed=True
            public_replace(updated)
            public_changed=True
            if (secure_read(path,max_bytes=16384)!=updated
                    or secure_read(public,uid=uid,max_bytes=16384)!=updated):
                fail('OFFER_RESTAGE_READBACK_FAILED')
            no_prior_authority()
        except BaseException:
            # Atomic rename may succeed before a subsequent fsync fails.
            # Compare both files independently rather than trusting flags.
            try:
                public_bytes=secure_read(public,uid=uid,max_bytes=16384)
                if public_bytes==updated:
                    public_replace(oldbytes)
                elif public_bytes!=oldbytes:
                    fail('OFFER_RESTAGE_PUBLIC_EXTERNAL_CHANGE')
                root_bytes=secure_read(path,max_bytes=16384)
                if root_bytes==updated:
                    atomic_root_json(path,old)
                elif root_bytes!=oldbytes:
                    fail('OFFER_RESTAGE_ROOT_EXTERNAL_CHANGE')
                if (secure_read(path,max_bytes=16384)!=oldbytes or
                        secure_read(public,uid=uid,max_bytes=16384)!=oldbytes):
                    fail('OFFER_RESTAGE_ROLLBACK_READBACK_FAILED')
            except BaseException:
                host.open_circuit_breaker('CATALOG_OFFER_RESTAGE_ROLLBACK_UNVERIFIED')
                raise
            raise
    return {'status':'catalog_unsigned_offer_restaged_without_production_mutation',
            'release_id':offer['release_id'],
            'source_sha':offer['protected_main_sha'],
            'candidate_sha':offer['candidate_sha'],
            'manifest_sha256':offer['manifest_sha256'],
            'prior_source_sha':old['protected_main_sha'],
            'owner_approval_required':True,'production_mutations':False}


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
    host=CatalogPMv4ProtectedHost(repo=repo)
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
            if current!=offer:
                return _restage_unchanged_catalog_scope(host,offer)
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
