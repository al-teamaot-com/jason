#!/usr/bin/env python3
"""Root-installed native host adapter for exactly one reviewed catalog release.

SOURCE-ONLY, NOT INSTALLED. In a developer worktree all mutating methods must
fail before touching Docker, freeze, services, grants or root state.
The authorized root installer must pin executable source, signer trust and
protected control-readback support before enabling this existing-PM action.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping

from implementation.kernel.signed_owner_release import read_pinned_root_owner_public_key
from tools.catalog_scoped_promotion import (
    ScopedPromotionDenied, PROTECTED_CONTAINERS, validate_offer,
    historical_receipt_verified, ADMISSION_EVIDENCE_PATH, fail,
)
from tools.catalog_scoped_release_admission import (
    host_readback,verify_live_image_evidence,verify_native_preflights,
    load_manifest,verified_source_scope,
)

STATE=Path('/var/lib/jason/openclaw/release-manager')
ROOT=Path('/var/lib/jason/catalog-scoped-promotion')
POLICY=Path('/etc/jason-owner-release/catalog-scoped-promotion-installed.json')
TRUST=Path('/etc/jason-owner-release/verified-owner-public-key.json')
INSTALLED=Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_host.py')
# Root installer copies the EXISTING exact native deploy helper into the
# immutable hash-pinned root bundle; the live checkout is never executable
# via a privileged mutable/less-strict path.
NATIVE=Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/deploy_live_container.py')
LOCK=STATE/'production-transaction.lock'
FREEZE=STATE/'production-deployment-freeze'
CONTROL=STATE/'production-control-state.json'
DRIFT=STATE/'production-drift.json'
SOURCE_REPO=Path('/home/al/.local/lib/jason/engineering-source-repo')
BASE_LIVE=('jason-runtime','jason-mcp-pilot')
SHA=re.compile(r'^[0-9a-f]{40}$')
ID=re.compile(r'^owner-mcp-[0-9a-f]{32}$')


def utcnow():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def secure_read(path:Path, *,max_bytes:int=131072,uid:int=0,mode:int=0o600)->bytes:
    if path.is_symlink() or not path.is_file():fail('TRUSTED_FILE_MISSING_OR_LINK')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=uid
                or stat.S_IMODE(info.st_mode)!=mode or info.st_nlink!=1
                or not 1<=info.st_size<=max_bytes):fail('TRUSTED_FILE_OWNERSHIP_OR_SIZE')
        raw=os.read(fd,max_bytes+1)
        if len(raw)!=info.st_size:fail('TRUSTED_FILE_READ_INCOMPLETE')
        return raw
    finally:os.close(fd)


def atomic_root_json(path:Path, data:Mapping[str,Any]):
    parent=path.parent
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_uid!=0 or parent.stat().st_mode&0o022:
        fail('ROOT_STATE_DIRECTORY_UNTRUSTED')
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if path.is_symlink() or info.st_uid!=0 or not stat.S_ISREG(info.st_mode):
            fail('ROOT_STATE_FILE_UNTRUSTED')
    handle,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=parent)
    try:
        with os.fdopen(handle,'wb') as f:
            f.write(json.dumps(dict(data),sort_keys=True,separators=(',',':')).encode()+b'\n')
            f.flush();os.fsync(f.fileno())
        os.chmod(name,0o600)
        os.replace(name,path)
        d=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:
        if os.path.exists(name):os.unlink(name)


def atomic_root_protected_control(data:Mapping[str,Any]):
    """Update only the EXISTING root control file inside al-owned PM state.

    Jason's native Production Manager owns the state parent as al:al mode
    0700 while protecting the live breaker itself as root:root mode 0600.
    The scoped release must preserve that model and must not generalize the
    root-only store writer for other caller-controlled paths.
    """
    if os.geteuid()!=0:
        fail('ROOT_CONTROL_WRITER_REQUIRES_ROOT')
    path=CONTROL
    parent=path.parent
    info=parent.lstat()
    al=pwd.getpwnam('al')
    if (parent.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or info.st_uid!=al.pw_uid
            or stat.S_IMODE(info.st_mode)!=0o700):
        fail('NATIVE_CONTROL_PARENT_OWNERSHIP_CHANGED')
    previous=secure_read(path,max_bytes=131072)
    if not previous:
        fail('ROOT_CONTROL_PREVIOUS_EVIDENCE_MISSING')
    payload=json.dumps(dict(data),sort_keys=True,separators=(',',':')).encode()+b'\n'
    if len(payload)>131072:
        fail('ROOT_CONTROL_RECORD_TOO_LARGE')
    fd,tmp=tempfile.mkstemp(prefix='.catalog-root-control-',dir=parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        os.chown(tmp,0,0,follow_symlinks=False)
        os.chmod(tmp,0o600)
        # A valid root-owned old file must still exist. Never publish over
        # an untrusted replacement introduced from the operator-owned dir.
        secure_read(path,max_bytes=131072)
        os.replace(tmp,path)
        descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    if secure_read(path,max_bytes=131072)!=payload:
        fail('ROOT_CONTROL_WRITE_READBACK_FAILED')


def inspect_container(name:str)->dict[str,Any]:
    done=subprocess.run(['docker','inspect',name],stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,check=False,timeout=20)
    if done.returncode:fail('DOCKER_INSPECT_UNAVAILABLE')
    try:values=json.loads(done.stdout)
    except (ValueError,TypeError) as exc:raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_INSPECT_INVALID') from exc
    if not isinstance(values,list) or len(values)!=1 or not isinstance(values[0],dict):
        fail('DOCKER_INSPECT_SHAPE')
    return values[0]


def docker_run(*args:str,timeout:int=480):
    process=subprocess.run(['docker',*args],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=timeout,check=False)
    if process.returncode:fail('DOCKER_COMMAND_FAILED')


def env_value(container:Mapping[str,Any],key:str)->str|None:
    values=[x.split('=',1)[1] for x in (container.get('Config') or {}).get('Env',[])
            if isinstance(x,str) and x.startswith(key+'=')]
    if len(values)>1:fail('DUPLICATE_CONTAINER_ENV')
    return values[0] if values else None


def container_baseline(name:str,revision:str,image:str):
    c=inspect_container(name)
    if (c['Image']!=image or
        (c.get('Config') or {}).get('Labels',{}).get('com.teamaot.jason.source_revision')!=revision
        or (c.get('State') or {}).get('Running') is not True):
        fail('LIVE_BASELINE_MISMATCH')
    return c


class NativeCatalogHost:
    """Production side effects require a separately installed root trust pin."""
    def __init__(self,repo:Path=SOURCE_REPO,state:Path=STATE,root:Path=ROOT):
        self.repo=repo
        self.state=state
        self.root=root
        self.policy:dict[str,Any]|None=None
        self.freeze_before:dict[str,Any]|None=None
        self.release_id:str|None=None
        self.protected_before:dict[str,Any]|None=None

    def enforce_installed_production_trust(self):
        if os.geteuid()!=0 or Path(__file__).resolve()!=INSTALLED:
            fail('ROOT_INSTALLED_EXECUTION_REQUIRED')
        raw=secure_read(POLICY,max_bytes=8192)
        try:policy=json.loads(raw)
        except ValueError as exc:raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_INSTALLED_POLICY_INVALID') from exc
        expected={'schema_version','action','source_sha','host_module_sha256',
                  'catalog_core_sha256','admission_module_sha256','native_deployer_sha256',
                  'root_readback_guard_sha256','native_root_control_supported',
                  'automatic_recovery_installed','no_global_owner_elevation',
                  'recovery_module_sha256','recovery_service_sha256',
                  'recovery_timer_sha256','root_worker_sha256'}
        if (not isinstance(policy,dict) or set(policy)!=expected
                or policy['schema_version']!='1.0'
                or policy['action']!='catalog-scoped-runtime-mcp-one-release-v1'
                or not isinstance(policy['source_sha'],str) or not SHA.fullmatch(policy['source_sha'])
                or policy['native_root_control_supported'] is not True
                or policy['automatic_recovery_installed'] is not True
                or policy['no_global_owner_elevation'] is not True):
            fail('INSTALLED_ROOT_POLICY_INVALID')
        for path,key in (
            (INSTALLED,'host_module_sha256'),
            (INSTALLED.parent/'catalog_scoped_promotion.py','catalog_core_sha256'),
            (INSTALLED.parent/'catalog_scoped_release_admission.py','admission_module_sha256'),
            (NATIVE,'native_deployer_sha256'),
            (Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_control_readback.py'),
             'root_readback_guard_sha256'),
            (Path('/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_recovery.py'),
             'recovery_module_sha256'),
            (Path('/usr/local/lib/jason/release_host_reconcile_worker.py'),
             'root_worker_sha256'),
            (Path('/etc/systemd/system/jason-catalog-scoped-recovery.service'),
             'recovery_service_sha256'),
            (Path('/etc/systemd/system/jason-catalog-scoped-recovery.timer'),
             'recovery_timer_sha256'),
        ):
            if not isinstance(policy[key],str) or re.fullmatch('[0-9a-f]{64}',policy[key]) is None:
                fail('INSTALLED_MODULE_PIN_INVALID')
            info=path.lstat()
            if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
                    or info.st_uid!=0 or info.st_mode&0o022
                    or sha256(path.read_bytes()).hexdigest()!=policy[key]):
                fail('INSTALLED_MODULE_DRIFT')
        for folder in (INSTALLED.parent,INSTALLED.parent.parent,self.root):
            info=folder.lstat()
            if folder.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
                fail('ROOT_BUNDLE_DIRECTORY_UNTRUSTED')
        for argv,expected in (
            (['systemctl','is-enabled','jason-catalog-scoped-recovery.timer'],'enabled'),
            (['systemctl','is-active','jason-catalog-scoped-recovery.timer'],'active'),
        ):
            checked=subprocess.run(argv,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,timeout=12,check=False,text=True)
            if checked.returncode!=0 or checked.stdout.strip()!=expected:
                fail('AUTOMATIC_ROOT_ROLLBACK_RECOVERY_NOT_ACTIVE')
        self.policy=policy

    @contextmanager
    def transaction_lock(self,offer:Mapping[str,Any]):
        validate_offer(offer)
        path=self.state/'production-transaction.lock'
        if path.is_symlink() or not path.is_file():fail('NATIVE_RELEASE_LOCK_MISSING')
        fd=os.open(path,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid!=pwd.getpwnam('al').pw_uid
                    or info.st_mode&0o002):fail('NATIVE_RELEASE_LOCK_UNTRUSTED')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_NATIVE_RELEASE_BUSY') from exc
            self.release_id=offer['release_id']
            yield
        finally:
            try:fcntl.flock(fd,fcntl.LOCK_UN)
            finally:os.close(fd)

    def _frozen(self,offer:Mapping[str,Any])->dict[str,Any]:
        marker=self.state/'production-deployment-freeze'
        if marker.is_symlink() or not marker.is_file():fail('PRODUCTION_FREEZE_NOT_ACTIVE')
        fd=os.open(marker,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:
            info=os.fstat(fd)
            raw=os.read(fd,4097)
        finally:os.close(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=pwd.getpwnam('al').pw_uid
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1
                or not 1<=len(raw)<=4096
                or sha256(raw).hexdigest()!=offer['freeze_sha256']):
            fail('PRODUCTION_FREEZE_CHANGED')
        try:doc=json.loads(raw)
        except (ValueError,TypeError) as exc:raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_FREEZE_INVALID') from exc
        if (doc.get('status')!='active'
                or doc.get('scope')!='manual-and-automatic-production-promotions'):
            fail('FREEZE_NOT_AUTHORITATIVE')
        return {'raw':raw,'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,
                'gid':info.st_gid,'sha256':offer['freeze_sha256']}

    def fresh_source_and_live_admission(self,offer:Mapping[str,Any]):
        if self.policy is None:fail('ROOT_INSTALL_NOT_VERIFIED')
        manifest=load_manifest(self.repo,main_sha=offer['protected_main_sha'])
        if (manifest['snapshot_sha']!=offer['candidate_sha']
                or manifest['rollback_sha']!=offer['rollback_sha']
                or manifest['scope_sha256']!=offer['scope_sha256']):
            fail('FRESH_MANIFEST_SCOPE_CHANGED')
        source=verified_source_scope(self.repo,manifest,
                main_sha=offer['protected_main_sha'],
                advertised_snapshot_sha=offer['candidate_sha'])
        # Protected CI is a LIVE gate: a previously staged read-only receipt
        # is not authority to proceed after checks regress or become stale.
        from tools.catalog_scoped_protected_ci import check_catalog_protected_ci
        current_ci=check_catalog_protected_ci(offer['protected_main_sha'],repo=self.repo)
        if current_ci.get('passed') is not True or current_ci.get('failures'):
            fail('LIVE_PROTECTED_SECURITY_CI_NOT_GREEN')
        historical_file=(INSTALLED.parent.parent/'docs/engineering/evidence/catalog-scope-admission-20261117.json')
        historical=json.loads(secure_read(historical_file,max_bytes=10000,mode=0o644))
        historical_receipt_verified(historical,manifest)
        frozen=self._frozen(offer)
        live=verify_live_image_evidence(manifest,host_readback(manifest))
        if (source['verified_main_sha']!=offer['protected_main_sha']
                or live['rollback_sha']!=offer['rollback_sha']):
            fail('FRESH_SOURCE_OR_ROLLBACK_CHANGED')
        result=verify_native_preflights(manifest,script=NATIVE)
        if result['runtime']['preflight']!='PASS' or result['mcp']['preflight']!='PASS':
            fail('NATIVE_PREFLIGHT_FAILED')
        self.freeze_before=frozen
        self.offer_baseline=offer['rollback_sha']

    def circuit_breaker_closed_and_workers_quiescent(self):
        if self.policy is None:fail('NO_INSTALLED_ROOT_POLICY')
        control=json.loads(secure_read(self.state/'production-control-state.json',max_bytes=131072))
        drift=json.loads(secure_read(self.state/'production-drift.json',max_bytes=131072))
        manifest=((control.get('last_known_good') or {}).get('manifest') or {})
        if (control.get('circuit_breaker',{}).get('state')!='closed'
                or manifest.get('complete') is not True
                or manifest.get('revision')!=self.freeze_candidate_baseline()
                or drift.get('status')!='pass' or drift.get('problems')):
            fail('BREAKER_OR_BASELINE_NOT_CLOSED')
        # Must be currently produced independent root drift, not a stale
        # developer assertion that the host is healthy.
        try:when=datetime.fromisoformat(str(drift['observed_at']))
        except (ValueError,TypeError,KeyError) as exc:raise ScopedPromotionDenied('CATALOG_SCOPED_PROMOTION_DRIFT_TIME_INVALID') from exc
        if when.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-when).total_seconds()<180:
            fail('PROTECTED_DRIFT_EVIDENCE_STALE')
        # PMV3 and PMV4 host promotions hold the SAME native serialized lock;
        # all public mutations must be quiet when this adapter owns it.

    def freeze_candidate_baseline(self):
        if not self.release_id:fail('NO_ACTIVE_TRANSACTION')
        return self.offer_baseline

    def deny_unresolved_previous_attempt(self,offer:Mapping[str,Any]):
        self.offer_baseline=offer['rollback_sha']
        journal=self.root/'transactions'/(offer['release_id']+'.json')
        if journal.exists() or journal.is_symlink():
            fail('EXISTING_ATTEMPT_REQUIRES_RECONCILIATION')
        active=self.root/'active.json'
        if active.exists() or active.is_symlink():
            fail('ANOTHER_SCOPED_RELEASE_ALREADY_ACTIVE')

    def pinned_owner_public_key(self):
        return read_pinned_root_owner_public_key(TRUST)

    def consumed_approval_ids(self)->frozenset[str]:
        ledger=self.root/'consumed-owner-approvals'
        if not ledger.is_dir() or ledger.is_symlink() or ledger.stat().st_uid!=0:
            fail('CONSUMPTION_LEDGER_MISSING')
        entries=[]
        for entry in ledger.iterdir():
            if not ID.fullmatch(entry.stem) or entry.suffix!='.json':
                fail('CONSUMPTION_LEDGER_UNEXPECTED_FILE')
            secure_read(entry,max_bytes=4096)
            entries.append(entry.stem)
        return frozenset(entries)

    def protected_container_snapshot(self)->Mapping[str,Any]:
        result={}
        for name in PROTECTED_CONTAINERS:
            state=inspect_container(name)
            if state.get('State',{}).get('Running') is not True:
                fail('PROTECTED_SERVICE_NOT_RUNNING')
            result[name]={
                'id':state['Id'],'image':state['Image'],
                'started_at':state['State']['StartedAt'],
            }
        self.protected_before=result
        return result

    def _journal_path(self,offer:Mapping[str,Any])->Path:
        return self.root/'transactions'/(offer['release_id']+'.json')

    def _journal(self,offer:Mapping[str,Any])->dict[str,Any]:
        return json.loads(secure_read(self._journal_path(offer)))

    def durable_intent(self,offer:Mapping[str,Any],decision:Mapping[str,Any]):
        path=self._journal_path(offer)
        if path.exists() or path.is_symlink():fail('RELEASE_ATTEMPT_ALREADY_EXISTS')
        self.active_offer=dict(offer)
        self._journal_data={
            'schema_version':'1.0','authorization':'catalog_scoped_exact_owner',
            'release_id':offer['release_id'],'candidate_sha':offer['candidate_sha'],
            'rollback_sha':offer['rollback_sha'],
            'scope_sha256':offer['scope_sha256'],
            'manifest_sha256':offer['manifest_sha256'],
            'admission_receipt_sha256':offer['historical_admission_receipt_sha256'],
            'approval_id':decision['approval_id'],
            'owner_principal':decision['owner_principal'],
            'runtime_image_id':offer['runtime_image_id'],
            'mcp_image_id':offer['mcp_image_id'],
            'rollback_runtime_image_id':offer['rollback_runtime_image_id'],
            'rollback_mcp_image_id':offer['rollback_mcp_image_id'],
            'status':'prepared_no_mutation',
            'protected_services_before':self.protected_before,
            'created_at':utcnow(), 'one_transaction_only':True,
        }
        atomic_root_json(path,self._journal_data)

    def _journal_status(self,offer:Mapping[str,Any],state:str,**fields):
        path=self._journal_path(offer)
        payload=self._journal(offer)
        payload.update(status=state,updated_at=utcnow(),**fields)
        atomic_root_json(path,payload)

    def consume_once(self,approval_id:str):
        if not isinstance(approval_id,str) or ID.fullmatch(approval_id) is None:
            fail('APPROVAL_ID_INVALID')
        path=self.root/'consumed-owner-approvals'/(approval_id+'.json')
        if path.exists() or path.is_symlink():fail('OWNER_PROOF_REPLAY')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            with os.fdopen(fd,'wb',closefd=False) as h:
                raw=json.dumps({'schema_version':'1.0','approval_id':approval_id,
                    'release_id':self.release_id,'consumed_at':utcnow(),
                    'one_use':True},sort_keys=True).encode()+b'\n'
                h.write(raw);h.flush();os.fsync(h.fileno())
        finally:os.close(fd)
        self._journal_status({'release_id':self.release_id},'owner_approval_consumed_no_mutation')

    def _restore_freeze(self,offer:Mapping[str,Any]):
        details=self.freeze_before
        if not isinstance(details,Mapping):fail('FREEZE_ORIGINAL_UNKNOWN')
        marker=self.state/'production-deployment-freeze'
        if marker.exists() or marker.is_symlink():
            current=self._frozen(offer)
            if current['sha256']!=details['sha256']:
                fail('FREEZE_REAPPEARED_DIFFERENT')
            return
        fd,name=tempfile.mkstemp(prefix='.catalog-scope-refreeze-',dir=self.state)
        try:
            with os.fdopen(fd,'wb') as h:
                h.write(details['raw']);h.flush();os.fsync(h.fileno())
            os.chown(name,details['uid'],details['gid'],follow_symlinks=False)
            os.chmod(name,details['mode'])
            os.replace(name,marker)
        finally:
            if os.path.exists(name):os.unlink(name)
        if self._frozen(offer)['sha256']!=details['sha256']:
            fail('FREEZE_RESTORE_MISMATCH')

    @contextmanager
    def frozen_one_transaction(self,offer:Mapping[str,Any],decision:Mapping[str,Any]):
        if self.policy is None:fail('ROOT_SOURCE_NOT_ATTESTED')
        if decision['approval_id'] not in self.consumed_approval_ids():
            fail('ONE_USE_OWNER_PROOF_NOT_CONSUMED')
        snapshot=self._frozen(offer)
        if self.freeze_before is None or snapshot['sha256']!=self.freeze_before['sha256']:
            fail('FREEZE_DRIFT_BEFORE_TRANSACTION')
        backup=self.root/'freeze-backups'/(offer['release_id']+'.bin')
        if backup.exists() or backup.is_symlink():fail('FREEZE_BACKUP_ALREADY_USED')
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            with os.fdopen(fd,'wb',closefd=False) as h:
                h.write(snapshot['raw']);h.flush();os.fsync(h.fileno())
        finally:os.close(fd)
        self._journal_status(offer,'one_exact_owner_unfreeze_pending',
            freeze_sha256_before=snapshot['sha256'],freeze_backup_sha256=sha256(backup.read_bytes()).hexdigest())
        marker=self.state/'production-deployment-freeze'
        removed=False
        try:
            # This marker may only be lifted here, under the shared native
            # transaction lock and after a fresh root-pinned, one-use Owner proof.
            marker.unlink()
            removed=True
            self._journal_status(offer,'one_transaction_freeze_temporarily_lifted')
            yield
        finally:
            if removed:
                self._restore_freeze(offer)
            self._journal_status(offer,'freeze_restored_pending_final_readback')

    def freeze_restored_exactly(self,offer:Mapping[str,Any]):
        self._frozen(offer)
        if self.freeze_before is None:fail('FREEZE_SNAPSHOT_NOT_RECORDED')
        backup=self.root/'freeze-backups'/(offer['release_id']+'.bin')
        if sha256(secure_read(backup,max_bytes=4096)).hexdigest()!=offer['freeze_sha256']:
            fail('FREEZE_BACKUP_CHANGED')
        journal=self._journal(offer)
        if journal.get('status')!='freeze_restored_pending_final_readback':
            fail('FREEZE_RESTORE_RECEIPT_MISSING')
        self._journal_status(offer,'freeze_restored_verified',
            freeze_sha256_after=offer['freeze_sha256'])

    def _offer_target(self,target:str)->tuple[str,str,str]:
        if not hasattr(self,'active_offer'):fail('NO_VERIFIED_ACTIVE_OFFER')
        if target=='jason-runtime':
            return ('runtime_image_id','rollback_runtime_image_id',
                    'JASON_AUTOTASK_CATALOG_AUTH_MODE')
        if target=='jason-mcp-pilot':
            return ('mcp_image_id','rollback_mcp_image_id',
                    'JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE')
        fail('UNAUTHORIZED_SERVICE_TARGET')

    def _rollback_name(self,target:str,offer:Mapping[str,Any])->str:
        return target+'-rollback-catalog-'+offer['candidate_sha'][:12]

    def promote_exact(self,target:str,image:str,revision:str,setting:Mapping[str,str]):
        image_key,rollback_key,env_key=self._offer_target(target)
        offer=self.active_offer
        if (image!=offer[image_key] or revision!=offer['candidate_sha']
                or setting!={env_key:offer['runtime_settings' if target=='jason-runtime' else 'mcp_settings'][env_key]}):
            fail('UNAPPROVED_CONTAINER_SOURCE_OR_ENV')
        journal=self._journal(offer)
        if journal.get('status') not in {'one_transaction_freeze_temporarily_lifted',
            'runtime_replaced_pending_mcp'}:
            fail('FREEZE_AND_JOURNAL_NOT_READY_FOR_MUTATION')
        rollback_name=self._rollback_name(target,offer)
        baseline=container_baseline(target,offer['rollback_sha'],offer[rollback_key])
        if baseline.get('Id') is None:fail('BASELINE_CONTAINER_ID_MISSING')
        if subprocess.run(['docker','inspect',rollback_name],
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
            fail('ROLLBACK_CONTAINER_ALREADY_EXISTS')
        native_argv=[
            'python3',str(NATIVE),'--live',target,'--image',image,
            '--rollback',rollback_name,
            '--source-revision',revision,
            '--health-url',('http://127.0.0.1:8080/healthz'
                            if target=='jason-runtime' else 'http://127.0.0.1:8000/healthz'),
            '--harden','--set-env',env_key+'='+setting[env_key],
        ]
        self._journal_status(offer,'mutating_'+target.replace('-','_'),
            previous_container_id=baseline['Id'])
        # The original native helper handles its own single-container restore;
        # the paired controller restores both if the second replacement fails.
        completed=subprocess.run(native_argv,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,timeout=480,check=False)
        if completed.returncode or b'DEPLOYMENT=PASS' not in completed.stdout:
            fail('NATIVE_CONTAINER_REPLACEMENT_FAILED')
        installed=inspect_container(target)
        if installed.get('Image')!=image:
            fail('NATIVE_CONTAINER_DIGEST_CHANGED')
        self._journal_status(offer,
            'runtime_replaced_pending_mcp' if target=='jason-runtime'
            else 'mcp_replaced_pending_pair_readback')

    def verify_live_dual_image(self,offer:Mapping[str,Any]):
        for target, image_key, settings in (
            ('jason-runtime','runtime_image_id','runtime_settings'),
            ('jason-mcp-pilot','mcp_image_id','mcp_settings'),
        ):
            container=container_baseline(target,offer['candidate_sha'],offer[image_key])
            values=offer[settings]
            for key,value in values.items():
                if env_value(container,key)!=value:
                    fail('ACTIVATION_ENVIRONMENT_MISMATCH')
            env_revision=env_value(container,'JASON_SOURCE_REVISION')
            if env_revision not in {None,offer['candidate_sha']}:
                fail('CONTAINER_SOURCE_REVISION_FORGED')
            host=(container.get('HostConfig') or {})
            if (host.get('ReadonlyRootfs') is not True
                    or 'ALL' not in (host.get('CapDrop') or [])
                    or 'no-new-privileges:true' not in (host.get('SecurityOpt') or [])):
                fail('CONTAINER_HARDENING_MISMATCH')
            if target=='jason-runtime' and (container.get('State') or {}).get('Health',{}).get('Status')!='healthy':
                fail('RUNTIME_HEALTH_NOT_VERIFIED')
        if Path('/opt/jason/current').resolve(strict=True).name!=offer['rollback_sha']:
            fail('PROTECTED_HOST_SOURCE_CHANGED')

    def verify_unchanged_protected_containers(self,original:Mapping[str,Any]):
        current=self.protected_container_snapshot()
        if set(current)!=set(original) or any(current[k]!=original[k] for k in original):
            fail('TICKET_PMV4_SECURITY_SERVICES_CHANGED')

    def publish_scoped_control_readback(self,offer:Mapping[str,Any],decision:Mapping[str,Any]):
        if self.policy is None or self.policy.get('native_root_control_supported') is not True:
            fail('ROOT_CONTROL_OVERLAY_NOT_INSTALLED')
        path=self.root/'active.json'
        if path.exists() or path.is_symlink():fail('SCOPED_ACTIVE_OVERLAY_EXISTS')
        payload={
            'schema_version':'1.0','authorization':'owner_signed_catalog_scoped_dual_image',
            'release_id':offer['release_id'],'snapshot_sha':offer['candidate_sha'],
            'host_revision':offer['rollback_sha'],
            'scope_sha256':offer['scope_sha256'],
            'manifest_sha256':offer['manifest_sha256'],
            'runtime_image_id':offer['runtime_image_id'],
            'mcp_image_id':offer['mcp_image_id'],
            'rollback_runtime_image_id':offer['rollback_runtime_image_id'],
            'rollback_mcp_image_id':offer['rollback_mcp_image_id'],
            'freeze_sha256':offer['freeze_sha256'],
            'approval_id':decision['approval_id'],
            'owner_principal':decision['owner_principal'],
            'protected_containers':list(PROTECTED_CONTAINERS),
            'status':'scoped_pair_readback_pending',
            'recorded_at':utcnow(),'global_owner_allowlist_unchanged':True,
        }
        atomic_root_json(path,payload)
        self._journal_status(offer,'pair_installed_control_readback_pending')

    def verify_scoped_control_readback(self,offer:Mapping[str,Any],*,phase:str='inside_exact_release_lock'):
        from tools.catalog_scoped_control_readback import verify_root_readback
        path=self.root/'active.json'
        overlay=json.loads(secure_read(path))
        runtime=container_baseline('jason-runtime',offer['candidate_sha'],offer['runtime_image_id'])
        mcp=container_baseline('jason-mcp-pilot',offer['candidate_sha'],offer['mcp_image_id'])
        services=self.protected_container_snapshot()
        state=json.loads(secure_read(self.state/'production-control-state.json',max_bytes=131072))
        reading={
            'host_revision':Path('/opt/jason/current').resolve(strict=True).name,
            'runtime_revision':runtime['Config']['Labels'].get('com.teamaot.jason.source_revision'),
            'mcp_revision':mcp['Config']['Labels'].get('com.teamaot.jason.source_revision'),
            'runtime_image_id':runtime['Image'],
            'mcp_image_id':mcp['Image'],
            'runtime_healthy':runtime['State'].get('Health',{}).get('Status')=='healthy',
            'mcp_running':mcp['State'].get('Running') is True,
            'runtime_catalog_auth_mode':env_value(runtime,'JASON_AUTOTASK_CATALOG_AUTH_MODE'),
            'mcp_catalog_grant_profile':env_value(mcp,'JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE'),
            'global_owner_allowlist':env_value(mcp,'JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES'),
            'protected_services':{name:services[name]['id']==self.protected_before[name]['id']
                                 and services[name]['started_at']==self.protected_before[name]['started_at']
                                 for name in PROTECTED_CONTAINERS},
        }
        receipt=verify_root_readback(
            offer=offer,overlay=overlay,live=reading,
            freeze_sha256=(offer['freeze_sha256'] if phase=='steady_frozen' else None),
            original_breaker=state,phase=phase,
        )
        if receipt['status']!='scoped_readback_pass_not_global_source_alignment':
            fail('INDEPENDENT_ROOT_SCOPED_READBACK_NOT_VERIFIED')
        if phase=='inside_exact_release_lock':
            overlay['status']='scoped_pair_verified'
            atomic_root_json(path,overlay)
            self._journal_status(offer,'scoped_control_readback_verified')

    def rollback_both(self,offer:Mapping[str,Any]):
        """Handle both normal rollback and interrupted Docker rename/create."""
        for target,key,candidate_key in (
            ('jason-mcp-pilot','rollback_mcp_image_id','mcp_image_id'),
            ('jason-runtime','rollback_runtime_image_id','runtime_image_id'),
        ):
            original=offer[key]
            retained=self._rollback_name(target,offer)
            try:
                current=inspect_container(target)
            except ScopedPromotionDenied:
                current=None  # Native helper may have renamed old before crash.
            if current is not None and current.get('Image')==original:
                container_baseline(target,offer['rollback_sha'],original)
                continue
            if current is not None and current.get('Image')!=offer[candidate_key]:
                fail('UNKNOWN_LIVE_IMAGE_CANNOT_ROLLBACK')
            previous=inspect_container(retained)
            if (previous.get('Image')!=original
                    or previous.get('Config',{}).get('Labels',{}).get(
                        'com.teamaot.jason.source_revision')!=offer['rollback_sha']):
                fail('IMMUTABLE_ROLLBACK_CONTAINER_DRIFT')
            if current is not None:
                docker_run('rm','-f',target)
            docker_run('rename',retained,target)
            docker_run('start',target)
            container_baseline(target,offer['rollback_sha'],original)
        self._journal_status(offer,'rollback_both_attempted')

    def verify_rollback_and_host(self,offer:Mapping[str,Any]):
        container_baseline('jason-runtime',offer['rollback_sha'],offer['rollback_runtime_image_id'])
        container_baseline('jason-mcp-pilot',offer['rollback_sha'],offer['rollback_mcp_image_id'])
        if Path('/opt/jason/current').resolve(strict=True).name!=offer['rollback_sha']:
            fail('HOST_ROLLBACK_REVISION_MISMATCH')
        self._journal_status(offer,'rollback_pair_verified')

    def clear_scoped_control_readback(self,offer:Mapping[str,Any]):
        path=self.root/'active.json'
        if path.is_symlink():fail('SCOPED_OVERLAY_SYMLINK')
        if path.is_file():
            overlay=json.loads(secure_read(path))
            if overlay.get('release_id')!=offer['release_id']:
                fail('SCOPED_OVERLAY_DIFFERENT_RELEASE')
            path.unlink()

    def record_outcome(self,offer:Mapping[str,Any],outcome:str,*,error:str=''):
        if outcome not in {'production_pair_verified','rolled_back_and_verified',
                           'rollback_unverified_breaker_required','failed_before_mutation'}:
            fail('RELEASE_OUTCOME_INVALID')
        self._journal_status(offer,'owner_scoped_outcome_recorded',
            outcome=outcome,error_code=str(error or '')[:100])

    def open_circuit_breaker(self,code:str):
        if not isinstance(code,str) or not re.fullmatch(r'CATALOG_SCOPED_[A-Z_]{3,90}',code):
            fail('BREAKER_REASON_INVALID')
        path=self.state/'production-control-state.json'
        data=json.loads(secure_read(path,max_bytes=131072))
        if data.get('schema_version')!='1.0':fail('BREAKER_CONTROL_SCHEMA_INVALID')
        data['circuit_breaker']={
            'state':'open','source':'catalog_scoped_promotion_root',
            'reason':code,'release_id':self.release_id,
            'opened_at':utcnow(),'updated_at':utcnow(),
        }
        data['updated_at']=utcnow()
        atomic_root_protected_control(data)
        verify=json.loads(secure_read(path,max_bytes=131072))
        if verify.get('circuit_breaker',{}).get('state')!='open':
            fail('BREAKER_OPEN_READBACK_FAILED')

    def recover_interrupted(self,offer:Mapping[str,Any]):
        """Rollback ONLY an exact previously interrupted scoped transaction.

        Recovery consumes no new permission to promote, never reuses a signed
        proof, never auto-closes the breaker and requires an exact rollback
        readback before marking the historical attempt resolved.
        """
        validate_offer(offer)
        self.enforce_installed_production_trust()
        with self.transaction_lock(offer):
            journal=self._journal(offer)
            if (journal.get('release_id')!=offer['release_id']
                    or journal.get('candidate_sha')!=offer['candidate_sha']
                    or journal.get('rollback_sha')!=offer['rollback_sha']
                    or journal.get('scope_sha256')!=offer['scope_sha256']
                    or journal.get('manifest_sha256')!=offer['manifest_sha256']):
                fail('RECOVERY_JOURNAL_SCOPE_CHANGED')
            if journal.get('outcome') in {'production_pair_verified',
                                           'rolled_back_and_verified'}:
                fail('RECOVERY_ALREADY_RESOLVED')
            protected=journal.get('protected_services_before')
            if (not isinstance(protected,dict)
                    or set(protected)!=set(PROTECTED_CONTAINERS)):
                fail('RECOVERY_PROTECTED_SERVICES_BASELINE_MISSING')
            self.protected_before=protected
            self.active_offer=offer
            self.open_circuit_breaker('CATALOG_SCOPED_INTERRUPTED_TRANSACTION')
            backup=self.root/'freeze-backups'/(offer['release_id']+'.bin')
            # A process may die after root journals intent/consumes the proof,
            # but BEFORE the freeze backup is first created. No deploy or
            # rollback is permitted on that path: prove both original images,
            # the unmodified host/freeze and protected services, or fail closed.
            if not backup.exists():
                if journal.get('status') not in {
                    'prepared_no_mutation', 'owner_approval_consumed_no_mutation',
                    'one_exact_owner_unfreeze_pending',
                }:
                    fail('RECOVERY_FREEZE_BACKUP_MISSING_AFTER_MUTATION')
                try:
                    self._frozen(offer)
                    self.verify_rollback_and_host(offer)
                    self.verify_unchanged_protected_containers(protected)
                    self.clear_scoped_control_readback(offer)
                    self._frozen(offer)
                    self._journal_status(offer,'interrupted_before_unfreeze_verified',
                        outcome='interrupted_before_unfreeze_verified',
                        freeze_sha256_after=offer['freeze_sha256'])
                except BaseException:
                    self._journal_status(offer,'interrupted_unverified_breaker_open')
                    raise
                return {
                    'status':'interrupted_before_unfreeze_verified',
                    'release_id':offer['release_id'],
                    'rollback_sha':offer['rollback_sha'],
                    'freeze_restored':True,
                    'circuit_breaker_remains_open':True,
                    'owner_proof_not_reusable':True,
                }
            raw=secure_read(backup,max_bytes=4096)
            if sha256(raw).hexdigest()!=offer['freeze_sha256']:
                fail('RECOVERY_FREEZE_BACKUP_MISMATCH')
            account=pwd.getpwnam('al')
            self.freeze_before={
                'raw':raw,'mode':0o600,'uid':account.pw_uid,
                'gid':account.pw_gid,'sha256':offer['freeze_sha256'],
            }
            try:
                self.rollback_both(offer)
                self.verify_rollback_and_host(offer)
                self.verify_unchanged_protected_containers(protected)
                self.clear_scoped_control_readback(offer)
                self._restore_freeze(offer)
                self._frozen(offer)
                self._journal_status(offer,'interrupted_rollback_verified',
                    outcome='interrupted_recovered_rollback_verified',
                    freeze_sha256_after=offer['freeze_sha256'])
            except BaseException:
                self._journal_status(offer,'interrupted_rollback_not_verified')
                raise
            return {'status':'interrupted_recovered_rollback_verified',
                    'release_id':offer['release_id'],
                    'rollback_sha':offer['rollback_sha'],
                    'freeze_restored':True,
                    'circuit_breaker_remains_open':True,
                    'owner_proof_not_reusable':True}
