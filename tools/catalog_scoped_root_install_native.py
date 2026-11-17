#!/usr/bin/env python3
"""Root-installed single-use catalog-only production installer.

SOURCE ONLY. Not in /usr/local/lib/jason on production. An authenticated
host Owner must independently stage source-pinned root-only bootstrap code;
there is no sudoers expansion, owner impersonation or unverified chat approval.
Runtime/MCP image promotion and Autotask writes are NEVER performed here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
import argparse
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any,Mapping
from uuid import uuid4

if os.geteuid()==0 and Path(__file__).resolve()==Path('/usr/local/lib/jason/catalog-root-bootstrap/tools/catalog_scoped_root_install_native.py'):
    sys.path.insert(0,'/usr/local/lib/jason/catalog-root-bootstrap')

from tools import catalog_scoped_root_install_transaction as transaction
from tools import catalog_scoped_root_install_plan as plan_module

BOOTSTRAP=Path('/usr/local/lib/jason/catalog-root-bootstrap')
ENTRY=BOOTSTRAP/'tools/catalog_scoped_root_install_native.py'
POLICY=Path('/etc/jason-owner-release/catalog-scoped-root-bootstrap-trust.json')
STATE=Path('/var/lib/jason-catalog-scoped-promotion')
AUDIT=STATE/'root-installer-audit'
OWNER_VERIFIER=Path('/usr/local/lib/jason/owner_signer_recovery.py')
NATIVE_LOCK=Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')
FREEZE=Path('/var/lib/jason/openclaw/release-manager/production-deployment-freeze')
CONTROL=Path('/var/lib/jason/openclaw/release-manager/production-control-state.json')
WORKER=Path('/usr/local/lib/jason/release_host_reconcile_worker.py')
ROOT_POLICY=Path('/etc/jason-owner-release/catalog-scoped-promotion-installed.json')
BUNDLE_ROOT=Path('/usr/local/lib/jason/catalog-scoped-promotion')
TIMER='jason-catalog-scoped-recovery.timer'
IMAGE_NAMES=('jason-runtime','jason-mcp-pilot','jason-teams-gateway',
             'jason-pmv4-shadow-gateway','openbao')
HEX64=re.compile(r'^[0-9a-f]{64}$')
HEX40=re.compile(r'^[0-9a-f]{40}$')


class NativeBootstrapDenied(PermissionError):pass


def fail(code:str)->None:raise NativeBootstrapDenied('CATALOG_NATIVE_BOOTSTRAP_'+code)


def now()->str:return datetime.now(timezone.utc).isoformat(timespec='seconds')


def secure_blob(path:Path,*,owner:int=0,maximum:int=1_000_000,mode:int|None=None)->bytes:
    if path.is_symlink():fail('SOURCE_SYMLINK')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=owner
                or st.st_nlink!=1 or st.st_mode&0o022
                or (mode is not None and stat.S_IMODE(st.st_mode)!=mode)
                or not 1<=st.st_size<=maximum):
            fail('SOURCE_FILE_OWNER_MODE_SIZE')
        data=os.read(fd,maximum+1)
        if len(data)!=st.st_size:fail('SOURCE_FILE_CHANGED')
        return data
    finally:os.close(fd)


def safe_root_dir(p:Path,*,create:bool=False,mode:int=0o700)->None:
    if create and not p.exists():
        p.mkdir(mode=mode)
        os.chown(p,0,0)
    st=p.lstat()
    if (p.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid!=0
            or stat.S_IMODE(st.st_mode)!=mode):
        fail('ROOT_DIRECTORY_UNTRUSTED')


def atomic_root_file(dest:Path, data:bytes, *,mode:int,overwrite:bool=False)->None:
    parent=dest.parent
    st=parent.lstat()
    if (parent.is_symlink() or not stat.S_ISDIR(st.st_mode)
            or st.st_uid!=0 or st.st_mode&0o022):
        fail('ROOT_DESTINATION_PARENT_UNTRUSTED')
    if dest.exists() or dest.is_symlink():
        if not overwrite:fail('ROOT_DESTINATION_ALREADY_EXISTS')
        secure_blob(dest,maximum=1_000_000)
    handle,tmp=tempfile.mkstemp(prefix='.jason-catalog-install-',dir=parent)
    try:
        with os.fdopen(handle,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chown(tmp,0,0,follow_symlinks=False)
        os.chmod(tmp,mode)
        os.replace(tmp,dest)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    if secure_blob(dest,mode=mode)!=data:fail('ROOT_INSTALLED_READBACK_DIFFERENT')


def run(*argv:str, timeout:int=60)->str:
    proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        text=True,timeout=timeout,check=False)
    if proc.returncode:fail('TRUSTED_SUBPROCESS_FAILED')
    return proc.stdout.strip()


def inspect(name:str)->dict[str,Any]:
    if name not in IMAGE_NAMES:fail('UNEXPECTED_CONTAINER')
    val=json.loads(run('docker','inspect',name,timeout=20))
    if not isinstance(val,list) or len(val)!=1:fail('CONTAINER_INSPECT_CARDINALITY')
    d=val[0]
    if not isinstance(d,dict) or not d.get('Image') or not d.get('Id'):
        fail('CONTAINER_INSPECT_MISSING_DATA')
    return d


class NativeRootInstaller:
    def __init__(self,plan:Mapping[str,Any],evidence_root:Path,trust:Mapping[str,Any]):
        self.plan=transaction.verify_plan(plan)
        self.evidence_root=evidence_root
        self.trust=dict(trust)
        self.before:dict[str,Any]={}
        self.owner:dict[str,Any]|None=None
        self.installed:set[str]=set()
        self.journal:Path|None=None

    def verify_root_bootstrap_trust(self,*,allow_existing_catalog_policy:bool=False)->None:
        if (os.geteuid()!=0 or sys.flags.isolated!=1
                or Path(__file__).resolve(strict=True)!=ENTRY):
            fail('ROOT_INSTALLED_ISOLATED_EXECUTION_REQUIRED')
        safe_root_dir(BOOTSTRAP,mode=0o755)
        for sub in ('tools','implementation','implementation/kernel'):
            safe_root_dir(BOOTSTRAP/sub,mode=0o755)
        raw=secure_blob(POLICY,mode=0o600,maximum=8192)
        policy=json.loads(raw)
        expected={'schema_version','action','protected_source_sha','bootstrap_sha256',
                  'transaction_sha256','plan_sha256','install_scope_sha256',
                  'evidence_root','owner_verifier_sha256','source_bundle_sha256',
                  'bootstrap_stage_files'}
        if (not isinstance(policy,dict) or set(policy)!=expected
                or policy['schema_version']!='1.0'
                or policy['action']!='catalog-root-bootstrap-once-v1'
                or policy['protected_source_sha']!=self.plan['source_sha']
                or policy['plan_sha256']!=self.plan['install_plan_sha256']
                or policy['install_scope_sha256']!=self.plan['installation_scope_sha256']
                or policy['evidence_root']!=str(self.evidence_root)):
            fail('ROOT_BOOTSTRAP_POLICY_SCOPE_CHANGED')
        for file,key in ((ENTRY,'bootstrap_sha256'),
                         (BOOTSTRAP/'tools/catalog_scoped_root_install_transaction.py','transaction_sha256'),
                         (OWNER_VERIFIER,'owner_verifier_sha256')):
            expected_sha=policy[key]
            if (not isinstance(expected_sha,str) or not HEX64.fullmatch(expected_sha)
                    or sha256(secure_blob(file,maximum=400000)).hexdigest()!=expected_sha):
                fail('ROOT_BOOTSTRAP_DEPENDENCY_HASH_MISMATCH')
        stage=policy.get('bootstrap_stage_files')
        allowed=set(plan_module.FILES)|{
            'tools/catalog_scoped_root_install_native.py',
            'tools/catalog_scoped_root_install_transaction.py',
            'tools/catalog_scoped_root_install_plan.py',
            'tools/catalog_scoped_promotion_bundle.py',
        }
        if not isinstance(stage,dict) or set(stage)!=allowed:
            fail('ROOT_BOOTSTRAP_STAGING_SCOPE_CHANGED')
        for relative,expected_digest in stage.items():
            if (not isinstance(expected_digest,str) or not HEX64.fullmatch(expected_digest)
                    or relative.startswith('/') or '..' in Path(relative).parts):
                fail('ROOT_BOOTSTRAP_STAGED_BLOB_INVALID')
            path=BOOTSTRAP/relative
            expected_mode=0o555 if path==ENTRY else 0o644
            if (sha256(secure_blob(path,mode=expected_mode,maximum=500000)).hexdigest()
                    != expected_digest):
                fail('ROOT_BOOTSTRAP_STAGED_BLOB_HASH_DRIFT')
        if policy['source_bundle_sha256']!=self._bundle_manifest()['bundle_sha256']:
            fail('BOOTSTRAP_BUNDLE_SOURCE_CHANGED')
        self.trust=policy
        if ROOT_POLICY.exists() or ROOT_POLICY.is_symlink():
            if not allow_existing_catalog_policy:fail('ROOT_CATALOG_POLICY_ALREADY_INSTALLED')
            if json.loads(secure_blob(ROOT_POLICY,mode=0o600))!=self.plan['root_policy_after_separate_approval']:
                fail('ROOT_RECOVERY_EXISTING_POLICY_DRIFT')

    def _bundle_manifest(self)->dict[str,Any]:
        # The prepared unprivileged evidence has zero authority by itself.
        path=self.evidence_root/'immutable-source-bundle/SOURCE_ONLY_MANIFEST.json'
        if path.is_symlink() or not path.is_file():fail('STAGED_BUNDLE_MANIFEST_MISSING')
        doc=json.loads(path.read_bytes())
        if (not isinstance(doc,dict)
                or doc.get('status')!='source_only_not_installed'
                or doc.get('source_sha')!=self.plan['source_sha']
                or doc.get('root_installation_authorized') is not False):
            fail('STAGED_SOURCE_BUNDLE_INVALID')
        return doc

    @contextmanager
    def lock_existing_production_manager(self):
        if NATIVE_LOCK.is_symlink() or not NATIVE_LOCK.is_file():fail('NATIVE_PM_LOCK_MISSING')
        fd=os.open(NATIVE_LOCK,os.O_RDWR|getattr(os,'O_NOFOLLOW',0))
        try:
            st=os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid!=pwd.getpwnam('al').pw_uid
                    or st.st_mode&0o002):fail('NATIVE_PM_LOCK_OWNER_CHANGED')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise NativeBootstrapDenied('CATALOG_NATIVE_BOOTSTRAP_PRODUCTION_MANAGER_BUSY') from exc
            yield
        finally:
            try:fcntl.flock(fd,fcntl.LOCK_UN)
            finally:os.close(fd)

    def _gh(self,endpoint:str)->dict[str,Any]:
        if (not endpoint.startswith('repos/al-teamaot-com/jason/')
                or any(token in endpoint for token in ('..',' ', '\n',';','&'))):
            fail('GITHUB_QUERY_SCOPE_INVALID')
        argv=['/usr/sbin/runuser','-u','al','--','env','HOME=/home/al',
              'PATH=/usr/bin:/bin','/usr/bin/gh','api',endpoint]
        try:
            raw=run(*argv,timeout=35)
            doc=json.loads(raw)
        except (OSError,ValueError,TypeError) as exc:
            raise NativeBootstrapDenied('CATALOG_NATIVE_BOOTSTRAP_PROTECTED_GIT_API_UNAVAILABLE') from exc
        if not isinstance(doc,dict):fail('GITHUB_RESULT_NOT_OBJECT')
        return doc

    def _protected_git_and_ci(self)->None:
        sha=self.plan['source_sha']
        remote=self._gh('repos/al-teamaot-com/jason/git/ref/heads/main')
        if remote.get('object',{}).get('sha')!=sha:
            fail('PROTECTED_MAIN_ADVANCED')
        # An explicit fixed release gate: all required protected checks must
        # be currently successful for the same commit. Never trust previous
        # green results on an older source or a synthetic local admission.
        fresh_path=self.evidence_root/'verified-readonly-admission.json'
        if fresh_path.is_symlink() or not fresh_path.is_file():
            fail('FRESH_READONLY_ADMISSION_MISSING')
        fresh=json.loads(fresh_path.read_bytes())
        received=fresh.get('receipt_sha256')
        before=dict(fresh)
        before.pop('receipt_sha256',None)
        if (received!=self.plan['fresh_admission_receipt_sha256']
                or sha256(plan_module.canonical(before)).hexdigest()!=received
                or fresh.get('status')!='SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE'
                or fresh.get('production_mutations') is not False
                or fresh.get('owner_approval_recorded') is not False
                or fresh.get('protected_source',{}).get('verified_main_sha')!=sha):
            fail('READONLY_ADMISSION_SOURCE_OR_RECEIPT_DRIFT')
        ci=fresh.get('protected_ci')
        required=ci.get('required_checks') if isinstance(ci,dict) else None
        if (not isinstance(ci,dict) or ci.get('passed') is not True
                or not isinstance(required,list)
                or len(required)<9 or len(required)>40
                or len(set(required))!=len(required)
                or 'governed-security-regressions' not in required
                or any(not isinstance(x,str) or re.fullmatch('[a-z0-9-]{3,100}',x) is None
                       for x in required)):
            fail('EXACT_PROTECTED_CI_POLICY_INVALID')
        checks=self._gh('repos/al-teamaot-com/jason/commits/'+sha+'/check-runs?per_page=100')
        if not isinstance(checks.get('total_count'),int) or checks['total_count']>100:
            fail('PROTECTED_CI_CHECK_RUN_PAGINATION_REQUIRED')
        latest={}
        for check in checks.get('check_runs',[]):
            if not isinstance(check,dict):fail('CI_CHECK_RUN_SHAPE')
            name=check.get('name')
            if isinstance(name,str) and (name not in latest or
                int(check.get('id',0))>int(latest[name].get('id',0))):
                latest[name]=check
        for name in required:
            item=latest.get(name)
            if item is None or item.get('status')!='completed' or item.get('conclusion')!='success':
                fail('PROTECTED_CI_FAILED_OR_INCOMPLETE')

    def _verify_bundle(self)->None:
        manifest=self._bundle_manifest()
        paths={x['source']:x for x in self.plan['root_file_plan']}
        if set(manifest.get('files',{}))!=set(paths):fail('STAGED_BUNDLE_FILE_SET_CHANGED')
        for relative,ref in manifest['files'].items():
            if relative not in paths or relative.startswith('/') or '..' in Path(relative).parts:
                fail('STAGED_SOURCE_OUTSIDE_EXACT_SCOPE')
            path=self.evidence_root/'immutable-source-bundle'/relative
            if path.is_symlink():fail('STAGED_SOURCE_SYMLINK')
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            try:
                st=os.fstat(fd)
                if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1
                        or st.st_uid!=pwd.getpwnam('al').pw_uid
                        or st.st_mode&0o022 or st.st_size>500000):
                    fail('STAGED_SOURCE_OWNER_OR_SIZE_CHANGED')
                raw=os.read(fd,500001)
            finally:os.close(fd)
            if (len(raw)!=st.st_size or sha256(raw).hexdigest()!=paths[relative]['sha256']
                    or sha256(raw).hexdigest()!=ref.get('sha256')):
                fail('STAGED_EXACT_SOURCE_BLOB_MISMATCH')

    def independent_live_source_ci_and_freeze(self,plan:Mapping[str,Any])->None:
        if plan['install_plan_sha256']!=self.trust.get('plan_sha256'):
            fail('PLAN_REVALIDATION_CHANGED')
        self._protected_git_and_ci()
        self._verify_bundle()
        old=secure_blob(WORKER,maximum=300000,mode=0o755)
        if sha256(old).hexdigest()!=plan['rollback_root_worker_sha256']:
            fail('ORIGINAL_ROOT_WORKER_DRIFT')
        original=secure_blob(FREEZE,owner=pwd.getpwnam('al').pw_uid,
                             maximum=4096,mode=0o600)
        if sha256(original).hexdigest()!=plan['freeze_sha256']:
            fail('PRODUCTION_FREEZE_CHANGED')
        if Path('/opt/jason/current').resolve(strict=True).name!=plan['rollback_source_sha']:
            fail('HOST_RELEASE_CHANGED')
        control=json.loads(secure_blob(CONTROL,maximum=131072,mode=0o600))
        lkg=((control.get('last_known_good') or {}).get('manifest') or {})
        if (control.get('circuit_breaker',{}).get('state')!='closed'
                or lkg.get('revision')!=plan['rollback_source_sha']
                or lkg.get('complete') is not True):
            fail('PROTECTED_BREAKER_OR_LKG_NOT_CLOSED')
        self.before={name:inspect(name) for name in IMAGE_NAMES}
        if any(x.get('State',{}).get('Running') is not True for x in self.before.values()):
            fail('PROTECTED_CONTAINER_NOT_RUNNING')
        expected={
            'jason-runtime':plan['rollback_runtime_image_id'],
            'jason-mcp-pilot':plan['rollback_mcp_image_id'],
        }
        for name,image in expected.items():
            if (self.before[name].get('Image')!=image or
                    self.before[name].get('Config',{}).get('Labels',{}).get(
                        'com.teamaot.jason.source_revision')!=plan['rollback_source_sha']):
                fail('ORIGINAL_RUNTIME_OR_MCP_DRIFT')
        self.before['_original_freeze']=original
        self.before['_original_worker']=old

    def deny_prior_attempt_or_changed_root_files(self,plan:Mapping[str,Any])->None:
        if ROOT_POLICY.exists() or ROOT_POLICY.is_symlink():
            fail('EXISTING_ROOT_CATALOG_POLICY')
        if STATE.exists() or STATE.is_symlink():
            # There may be a separately governed root state (e.g. previous
            # incomplete attempt). Do not repair or overwrite it silently.
            fail('ROOT_CATALOG_INSTALL_STATE_ALREADY_EXISTS')
        for entry in plan['root_file_plan']:
            dest=Path(entry['destination'])
            if dest!=WORKER and (dest.exists() or dest.is_symlink()):
                fail('PREEXISTING_SCOPED_TARGET_REQUIRES_REVIEW')
        checked=subprocess.run(['systemctl','is-active',TIMER],stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,text=True,timeout=12)
        if checked.stdout.strip()=='active':fail('CATALOG_RECOVERY_TIMER_ALREADY_ACTIVE')

    def _verified_oauth_module(self):
        filename='jason_catalog_owner_oauth_pinned'
        spec=importlib.util.spec_from_file_location(filename,OWNER_VERIFIER)
        if spec is None or spec.loader is None:fail('PINNED_ENTRA_VERIFIER_NOT_LOADABLE')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if (module.TENANT!=transaction.TID or
                frozenset(module.OWNERS)!=transaction.OWNER_OIDS or
                module.CLIENT_ID!='9b9996e9-5c34-48b7-948c-f44f89352f89' or
                module.SCOPE!='https://mcp-jason.teamaot.com/mcp/Jason.Read'):
            fail('PINNED_ENTRA_OWNER_POLICY_CHANGED')
        return module

    def obtain_verified_entra_owner_for_exact_action(self,plan:Mapping[str,Any])->Mapping[str,Any]:
        helper=self._verified_oauth_module()
        root='https://login.microsoftonline.com/'+helper.TENANT+'/oauth2/v2.0/'
        challenge=helper._form(root+'devicecode',{
            'client_id':helper.CLIENT_ID,'scope':helper.SCOPE})
        if not all(isinstance(challenge.get(name),str) for name in
                   ('device_code','user_code','verification_uri')):
            fail('ENTRA_DEVICE_OAUTH_CHALLENGE_UNAVAILABLE')
        lifetime=min(int(challenge.get('expires_in',0)),600)
        if lifetime<60:fail('ENTRA_CHALLENGE_TOO_SHORT')
        print('EXACT_ACTION='+transaction.ACTION,flush=True)
        print('ROOT_SOURCE_SHA='+plan['source_sha'],flush=True)
        print('ROOT_INSTALL_SCOPE_SHA256='+plan['installation_scope_sha256'],flush=True)
        print('ROOT_INSTALL_PLAN_SHA256='+plan['install_plan_sha256'],flush=True)
        print('ROLLBACK_ROOT_WORKER_SHA256='+plan['rollback_root_worker_sha256'],flush=True)
        print('ORIGINAL_FREEZE_SHA256='+plan['freeze_sha256'],flush=True)
        print('RUNTIME_MCP_IMAGE_PROMOTION_APPROVED=false',flush=True)
        print('AUTOTASK_PROVIDER_WRITES_APPROVED=false',flush=True)
        print('BROWSER_VERIFICATION_URL='+challenge['verification_uri'],flush=True)
        print('SIGN_IN_CODE='+challenge['user_code'],flush=True)
        deadline=time.monotonic()+lifetime
        interval=max(5,min(20,int(challenge.get('interval',5))))
        verified_token=None
        oid=None
        while time.monotonic()<deadline:
            time.sleep(interval)
            response=helper._form(root+'token',{
                'grant_type':'urn:ietf:params:oauth:grant-type:device_code',
                'client_id':helper.CLIENT_ID,'device_code':challenge['device_code']})
            if isinstance(response.get('access_token'),str):
                verified_token=response['access_token']
                oid=helper.jwt_owner(verified_token)
                break
            if response.get('error')=='slow_down':interval=min(20,interval+5)
            elif response.get('error')!='authorization_pending':
                fail('ENTRA_OWNER_SIGNIN_REJECTED')
        if verified_token is None or oid is None:fail('ENTRA_OWNER_SIGNIN_EXPIRED')
        prompt='Type '+transaction.CONFIRM+' to authorize ONLY THIS root installation: '
        if input(prompt).strip()!=transaction.CONFIRM:
            fail('OWNER_EXACT_ACTION_CONSENT_MISSING')
        # Never persist or print a bearer token, private signing key, or MFA.
        e={
            'schema_version':'1.0','action':transaction.ACTION,
            'approval_id':'catalog-root-owner-'+uuid4().hex,
            'release_id':'release-'+plan['source_sha'][:16],
            'source_sha':plan['source_sha'],
            'scope_sha256':plan['installation_scope_sha256'],
            'manifest_sha256':plan['install_plan_sha256'],
            'rollback_source_sha':plan['rollback_source_sha'],
            'freeze_sha256':plan['freeze_sha256'],
            'owner_tenant':transaction.TID,'owner_oid':oid,
            'owner_principal':'person-entra-'+oid.replace('-',''),
            'assurance':'fresh_verified_entra_device_code_signed_jwt',
            'verified_access_token_sha256':sha256(verified_token.encode()).hexdigest(),
            'approved_at':now(), 'affirmative_decision':transaction.CONFIRM,
            'one_use':True,'standing_authority':False,
            'provider_write_approved':False,
        }
        self.owner=transaction.verify_owner_evidence(plan,e)
        return e

    def _ledger_dir(self,name:str)->Path:
        if name not in {'root-installer-audit','root-installer-backup','consumed-owner-approvals',
                        'transactions','offers','freeze-backups'}:
            fail('ROOT_LEDGER_UNREVIEWED_DIRECTORY')
        return STATE/name

    def _audit(self,status:str,*,error:str='')->None:
        if self.journal is None:fail('INSTALL_JOURNAL_NOT_INITIALIZED')
        payload={
            'schema_version':'1.0','action':transaction.ACTION,
            'source_sha':self.plan['source_sha'],
            'scope_sha256':self.plan['installation_scope_sha256'],
            'plan_sha256':self.plan['install_plan_sha256'],
            'rollback_source_sha':self.plan['rollback_source_sha'],
            'freeze_sha256':self.plan['freeze_sha256'],
            'approval_id':self.owner['approval_id'] if self.owner else '',
            'verified_owner_oid':self.owner['owner_oid'] if self.owner else '',
            'verified_token_sha256':self.owner['verified_access_token_sha256'] if self.owner else '',
            'status':status,'updated_at':now(),'error_code':str(error)[:100],
            'runtime_mcp_promotion':False,'provider_write':False,
            'protected_containers_before':{
                name:{'id':data['Id'],'image':data['Image'],
                      'started_at':data['State']['StartedAt']}
                for name,data in self.before.items()
                if name in IMAGE_NAMES and isinstance(data,dict)
            },
        }
        atomic_root_file(self.journal,plan_module.canonical(payload)+b'\n',mode=0o600,
                         overwrite=self.journal.exists())

    def journal_intent_before_mutation(self,plan:Mapping[str,Any],owner:Mapping[str,Any])->None:
        if STATE.exists() or STATE.is_symlink():fail('ROOT_LEDGER_ALREADY_PRESENT')
        parent=STATE.parent.lstat()
        if (STATE.parent.is_symlink() or parent.st_uid!=0
                or parent.st_mode&0o022):fail('ROOT_LEDGER_PARENT_UNTRUSTED')
        safe_root_dir(STATE,create=True,mode=0o700)
        for name in ('root-installer-audit','root-installer-backup','consumed-owner-approvals',
                     'transactions','offers','freeze-backups'):
            safe_root_dir(self._ledger_dir(name),create=True,mode=0o700)
        self.owner=dict(owner)
        self.journal=self._ledger_dir('root-installer-audit')/('release-'+plan['source_sha'][:16]+'.json')
        if self.journal.exists() or self.journal.is_symlink():
            fail('ROOT_INSTALL_REPLAY_OR_INTERRUPTED')
        self._audit('prepared_signed_entra_owner_no_mutation')

    def consumed_owner_approvals(self)->frozenset[str]:
        directory=self._ledger_dir('consumed-owner-approvals')
        if not directory.exists():return frozenset()
        safe_root_dir(directory,mode=0o700)
        ids=[]
        for path in directory.iterdir():
            if (path.suffix!='.json' or
                    re.fullmatch('catalog-root-owner-[0-9a-f]{32}',path.stem) is None):
                fail('ROOT_OWNER_REPLAY_LEDGER_UNKNOWN_ENTRY')
            secure_blob(path,mode=0o600,maximum=4096)
            ids.append(path.stem)
        return frozenset(ids)

    def consume_owner_approval_once(self,approval_id:str)->None:
        if re.fullmatch('catalog-root-owner-[0-9a-f]{32}',approval_id or '') is None:
            fail('OWNER_CONSUMPTION_ID_INVALID')
        path=self._ledger_dir('consumed-owner-approvals')/(approval_id+'.json')
        if path.exists() or path.is_symlink():fail('OWNER_PROOF_ALREADY_CONSUMED')
        payload={
            'schema_version':'1.0','action':transaction.ACTION,
            'approval_id':approval_id,'source_sha':self.plan['source_sha'],
            'plan_sha256':self.plan['install_plan_sha256'],
            'owner_oid':self.owner['owner_oid'] if self.owner else '',
            'consumed_at':now(),'one_use':True,
        }
        atomic_root_file(path,plan_module.canonical(payload)+b'\n',mode=0o600)
        self._audit('owner_consent_consumed_before_mutation')

    def backup_original_worker_and_units(self,plan:Mapping[str,Any])->None:
        worker=secure_blob(WORKER,mode=0o755,maximum=300000)
        if sha256(worker).hexdigest()!=plan['rollback_root_worker_sha256']:
            fail('OLD_ROOT_WORKER_CHANGED_BEFORE_BACKUP')
        backup=self._ledger_dir('root-installer-backup')/'release-host-reconcile-worker.original'
        atomic_root_file(backup,worker,mode=0o600)
        for rel in ('jason-catalog-scoped-recovery.service',
                    'jason-catalog-scoped-recovery.timer'):
            dest=Path('/etc/systemd/system')/rel
            if dest.exists() or dest.is_symlink():fail('PROTECTED_UNIT_NOT_EMPTY_BEFORE_INSTALL')
        original=self.before.get('_original_freeze')
        if not isinstance(original,bytes) or sha256(original).hexdigest()!=plan['freeze_sha256']:
            fail('ORIGINAL_FREEZE_BACKUP_NOT_PROVEN')
        atomic_root_file(self._ledger_dir('root-installer-backup')/'original-freeze.bin',
                         original,mode=0o600)
        self._audit('original_worker_and_freeze_backed_up')

    def _ensure_destination_parent(self,dest:Path)->None:
        if dest==WORKER or dest.parent==Path('/etc/systemd/system'):
            return
        if dest==ROOT_POLICY:return
        try:
            relative=dest.relative_to(BUNDLE_ROOT)
        except ValueError:
            fail('INSTALL_DESTINATION_OUTSIDE_SCOPED_BUNDLE')
        ancestor=BUNDLE_ROOT
        if not ancestor.exists():
            st=ancestor.parent.lstat()
            if (ancestor.parent.is_symlink() or st.st_uid!=0 or st.st_mode&0o022):
                fail('ROOT_BUNDLE_PARENT_UNTRUSTED')
            safe_root_dir(ancestor,create=True,mode=0o755)
        else:safe_root_dir(ancestor,mode=0o755)
        for part in relative.parts[:-1]:
            ancestor=ancestor/part
            safe_root_dir(ancestor,create=True,mode=0o755)

    def _bytes_for(self,relative:str,expected_sha:str)->bytes:
        if relative not in plan_module.FILES:fail('UNREVIEWED_INSTALL_SOURCE')
        path=self.evidence_root/'immutable-source-bundle'/relative
        if path.is_symlink():fail('STAGED_SOURCE_SYMLINK_BEFORE_COPY')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        try:
            st=os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid!=pwd.getpwnam('al').pw_uid
                    or st.st_nlink!=1 or st.st_mode&0o022 or st.st_size>500000):
                fail('STAGED_SOURCE_CHANGED_BEFORE_COPY')
            raw=os.read(fd,500001)
        finally:os.close(fd)
        if len(raw)!=st.st_size or sha256(raw).hexdigest()!=expected_sha:
            fail('STAGED_EXACT_BLOB_CHANGED_BEFORE_COPY')
        return raw

    def install_exact_root_files(self,plan:Mapping[str,Any])->None:
        self._audit('installing_hash_pinned_root_files')
        # Install the original worker replacement LAST. Before that point the
        # running PMV3/PMV4 host worker remains byte-identical to baseline.
        entries=sorted(plan['root_file_plan'],
                       key=lambda e:(e['destination']==str(WORKER),e['destination']))
        for entry in entries:
            relative=entry['source']
            expected=plan_module.target_for_source(relative)
            if any(entry[key]!=expected[key] for key in ('destination','uid','gid','mode')):
                fail('FILE_INSTALL_TARGET_NOT_IN_APPROVED_PLAN')
            raw=self._bytes_for(relative,entry['sha256'])
            dest=Path(entry['destination'])
            self._ensure_destination_parent(dest)
            atomic_root_file(dest,raw,mode=int(entry['mode'],8),overwrite=(dest==WORKER))
            self.installed.add(str(dest))
        self._audit('all_root_source_files_staged_before_policy')

    def install_root_policy(self,plan:Mapping[str,Any])->None:
        if ROOT_POLICY.exists() or ROOT_POLICY.is_symlink():fail('SCOPED_ROOT_POLICY_ALREADY_EXISTS')
        policy=plan['root_policy_after_separate_approval']
        if policy['source_sha']!=plan['source_sha']:
            fail('SCOPED_POLICY_SOURCE_SHA_DRIFT')
        atomic_root_file(ROOT_POLICY,plan_module.canonical(policy)+b'\n',mode=0o600)
        self.installed.add(str(ROOT_POLICY))
        self._audit('root_policy_recorded_no_image_promotion')

    def activate_and_verify_recovery_watchdog(self,plan:Mapping[str,Any])->None:
        run('systemctl','daemon-reload',timeout=40)
        run('systemctl','enable','--now',TIMER,timeout=65)
        if run('systemctl','is-active',TIMER,timeout=20)!='active':
            fail('ROOT_RECOVERY_WATCHDOG_NOT_ACTIVE')
        if run('systemctl','is-enabled',TIMER,timeout=20)!='enabled':
            fail('ROOT_RECOVERY_WATCHDOG_NOT_ENABLED')
        self._audit('recovery_watchdog_active_pending_final_readback')

    def _unchanged(self,plan:Mapping[str,Any])->None:
        freeze=secure_blob(FREEZE,owner=pwd.getpwnam('al').pw_uid,
                            maximum=4096,mode=0o600)
        if sha256(freeze).hexdigest()!=plan['freeze_sha256']:
            fail('PRODUCTION_FREEZE_DRIFT_AFTER_ROOT_INSTALL')
        if Path('/opt/jason/current').resolve(strict=True).name!=plan['rollback_source_sha']:
            fail('HOST_SOURCE_CHANGED_AFTER_ROOT_INSTALL')
        for name in IMAGE_NAMES:
            previous=self.before.get(name)
            after=inspect(name)
            if (not isinstance(previous,dict) or after.get('Id')!=previous.get('Id')
                    or after.get('Image')!=previous.get('Image')
                    or after.get('State',{}).get('StartedAt')!=previous.get('State',{}).get('StartedAt')):
                fail('UNRELATED_LIVE_PRODUCTION_CONTAINER_CHANGED')

    def independent_live_readback(self,plan:Mapping[str,Any])->None:
        for item in plan['root_file_plan']:
            dest=Path(item['destination'])
            if sha256(secure_blob(dest,mode=int(item['mode'],8))).hexdigest()!=item['sha256']:
                fail('INDEPENDENT_ROOT_INSTALLED_HASH_MISMATCH')
        if json.loads(secure_blob(ROOT_POLICY,mode=0o600))!=plan['root_policy_after_separate_approval']:
            fail('ROOT_POLICY_READBACK_CHANGED')
        if run('systemctl','is-active',TIMER,timeout=20)!='active':
            fail('ROOT_TIMER_READBACK_FAILED')
        self._unchanged(plan)
        self._protected_git_and_ci()
        self._audit('root_install_verified_freeze_unchanged')

    def restore_original_worker_units_and_state(self,plan:Mapping[str,Any])->None:
        # No new source, timer, or root policy is removed unless its exact
        # installed bytes match the reviewed immutable scope. Unknown drift
        # requires root breaker + manual recovery rather than blind delete.
        subprocess.run(['systemctl','disable','--now',TIMER],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                       timeout=45,check=False)
        old=secure_blob(self._ledger_dir('root-installer-backup')/
                        'release-host-reconcile-worker.original',
                        maximum=300000,mode=0o600)
        if sha256(old).hexdigest()!=plan['rollback_root_worker_sha256']:
            fail('ROOT_WORKER_BACKUP_CHANGED')
        staged=next(x for x in plan['root_file_plan']
                    if x['destination']==str(WORKER))
        existing=secure_blob(WORKER,mode=0o755,maximum=300000)
        actual=sha256(existing).hexdigest()
        if actual not in {staged['sha256'],plan['rollback_root_worker_sha256']}:
            fail('UNKNOWN_INSTALLED_ROOT_WORKER_CANNOT_RESTORE')
        if actual!=plan['rollback_root_worker_sha256']:
            atomic_root_file(WORKER,old,mode=0o755,overwrite=True)
        # Drop the scoped policy before deleting its expected root modules.
        if ROOT_POLICY.is_symlink():fail('ROOT_SCOPED_POLICY_SYMLINK_DURING_ROLLBACK')
        if ROOT_POLICY.is_file():
            current=json.loads(secure_blob(ROOT_POLICY,mode=0o600))
            if current!=plan['root_policy_after_separate_approval']:
                fail('ROOT_SCOPED_POLICY_UNKNOWN_CONTENT')
            ROOT_POLICY.unlink()
        for item in sorted(plan['root_file_plan'],key=lambda x:x['destination'],reverse=True):
            dest=Path(item['destination'])
            if dest==WORKER:continue
            if dest.is_symlink():fail('ROOT_INSTALLED_TARGET_SYMLINK_DURING_ROLLBACK')
            if dest.is_file():
                raw=secure_blob(dest,mode=int(item['mode'],8))
                if sha256(raw).hexdigest()!=item['sha256']:
                    fail('UNKNOWN_ROOT_INSTALLED_FILE_CANNOT_DELETE')
                dest.unlink()
        # Never delete a directory containing an unrelated or changed file.
        for directory in sorted(BUNDLE_ROOT.glob('**/*'),key=lambda x:len(x.parts),reverse=True) if BUNDLE_ROOT.is_dir() else []:
            if directory.is_symlink():fail('ROOT_SCOPED_BUNDLE_DIR_SYMLINK')
            if directory.is_dir():
                safe_root_dir(directory,mode=0o755)
                if not any(directory.iterdir()):directory.rmdir()
        if BUNDLE_ROOT.exists():
            safe_root_dir(BUNDLE_ROOT,mode=0o755)
            if not any(BUNDLE_ROOT.iterdir()):BUNDLE_ROOT.rmdir()
        run('systemctl','daemon-reload',timeout=40)
        self._audit('original_worker_and_units_restored_pending_freeze_readback')

    def independently_verify_rollback_and_freeze(self,plan:Mapping[str,Any])->None:
        if sha256(secure_blob(WORKER,mode=0o755)).hexdigest()!=plan['rollback_root_worker_sha256']:
            fail('ORIGINAL_ROOT_WORKER_NOT_RESTORED')
        if ROOT_POLICY.exists() or ROOT_POLICY.is_symlink():
            fail('SCOPED_ROOT_POLICY_NOT_REMOVED')
        if BUNDLE_ROOT.exists() or BUNDLE_ROOT.is_symlink():
            fail('SCOPED_ROOT_BUNDLE_NOT_REMOVED')
        for ext in ('service','timer'):
            dest=Path('/etc/systemd/system')/('jason-catalog-scoped-recovery.'+ext)
            if dest.exists() or dest.is_symlink():
                fail('CATALOG_RECOVERY_UNIT_NOT_ROLLED_BACK')
        try:active=run('systemctl','is-active',TIMER,timeout=20)
        except NativeBootstrapDenied:active='inactive'
        if active=='active':fail('CATALOG_RECOVERY_TIMER_STILL_ACTIVE')
        self._unchanged(plan)
        self._audit('exact_old_root_worker_and_freeze_rollback_verified')

    def open_root_production_breaker(self,reason:str)->None:
        if reason!='CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED':
            fail('UNREVIEWED_BREAKER_REASON')
        # The original PM owns a protected root:root mode-0600 breaker record
        # inside an al-owned mode-0700 state directory. The exact path is
        # fixed here; no generic file write or policy grant is introduced.
        parent=CONTROL.parent
        info=parent.lstat()
        if (parent.is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid!=pwd.getpwnam('al').pw_uid
                or stat.S_IMODE(info.st_mode)!=0o700):
            fail('ROOT_PROTECTED_BREAKER_PARENT_UNTRUSTED')
        previous=json.loads(secure_blob(CONTROL,mode=0o600,maximum=131072))
        if previous.get('schema_version')!='1.0':
            fail('ROOT_BREAKER_SCHEMA_CHANGED')
        previous['circuit_breaker']={
            'state':'open','reason':reason,'source':'catalog_root_install_bootstrap',
            'release_id':'release-'+self.plan['source_sha'][:16],
            'opened_at':now(),'updated_at':now(),
        }
        previous['updated_at']=now()
        payload=plan_module.canonical(previous)+b'\n'
        if len(payload)>131072:fail('ROOT_PROTECTED_BREAKER_RECORD_TOO_LARGE')
        fd,tmp=tempfile.mkstemp(prefix='.catalog-root-breaker-',dir=parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.chown(tmp,0,0,follow_symlinks=False)
            os.chmod(tmp,0o600)
            secure_blob(CONTROL,mode=0o600,maximum=131072)
            os.replace(tmp,CONTROL)
            directory_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        if json.loads(secure_blob(CONTROL,mode=0o600,maximum=131072)).get('circuit_breaker',{}).get('state')!='open':
            fail('ROOT_PROTECTED_BREAKER_OPEN_READBACK_FAILED')

    def record_completion(self,plan:Mapping[str,Any],outcome:str)->None:
        if outcome not in {
            'exact_catalog_root_install_verified','catalog_root_rolled_back_verified',
            'catalog_root_rollback_unverified','root_install_backup_failed_before_mutation',
        }:
            fail('UNAPPROVED_RELEASE_OUTCOME')
        self._audit(outcome)


    def recover_interrupted(self)->dict[str,Any]:
        """Rollback a PREVIOUS signed exact installer attempt; never repromote.

        Requires independently root-pinned bootstrap code and original one-use
        evidence. Recover does not ask for, mint or reuse another Owner proof.
        """
        self.verify_root_bootstrap_trust(allow_existing_catalog_policy=True)
        with self.lock_existing_production_manager():
            audit=self._ledger_dir('root-installer-audit')
            safe_root_dir(STATE,mode=0o700)
            safe_root_dir(audit,mode=0o700)
            path=audit/('release-'+self.plan['source_sha'][:16]+'.json')
            journal=json.loads(secure_blob(path,mode=0o600,maximum=30000))
            if (journal.get('schema_version')!='1.0'
                    or journal.get('action')!=transaction.ACTION
                    or journal.get('source_sha')!=self.plan['source_sha']
                    or journal.get('scope_sha256')!=self.plan['installation_scope_sha256']
                    or journal.get('plan_sha256')!=self.plan['install_plan_sha256']
                    or journal.get('rollback_source_sha')!=self.plan['rollback_source_sha']
                    or journal.get('freeze_sha256')!=self.plan['freeze_sha256']):
                fail('INTERRUPTED_JOURNAL_SCOPE_CHANGED')
            self.journal=path
            approval=journal.get('approval_id')
            ledger=self._ledger_dir('consumed-owner-approvals')
            safe_root_dir(ledger,mode=0o700)
            if not isinstance(approval,str) or re.fullmatch('catalog-root-owner-[0-9a-f]{32}',approval) is None:
                fail('INTERRUPTED_OWNER_APPROVAL_MISSING')
            self.owner={
                'approval_id':approval,
                'owner_oid':str(journal.get('verified_owner_oid') or ''),
                'verified_access_token_sha256':str(journal.get('verified_token_sha256') or ''),
            }
            consumed_path=ledger/(approval+'.json')
            consumption_missing=(not consumed_path.exists() and not consumed_path.is_symlink())
            if not consumption_missing:
                proof=json.loads(secure_blob(consumed_path,mode=0o600,maximum=4096))
                if (proof.get('approval_id')!=approval
                        or proof.get('plan_sha256')!=self.plan['install_plan_sha256']
                        or proof.get('source_sha')!=self.plan['source_sha']):
                    fail('INTERRUPTED_OWNER_CONSUMPTION_DRIFT')
            elif journal.get('status') not in {
                    'prepared_signed_entra_owner_no_mutation',
                    'interrupted_before_owner_consumption_verified',
            }:
                fail('INTERRUPTED_OWNER_CONSUMPTION_MISSING_AFTER_MUTATION')
            safe=journal.get('protected_containers_before')
            if (not isinstance(safe,dict) or set(safe)!=set(IMAGE_NAMES)):
                fail('INTERRUPTED_PROTECTED_CONTAINER_BASELINE_MISSING')
            self.before={}
            for name,item in safe.items():
                if (not isinstance(item,dict) or
                        set(item)!={'id','image','started_at'}):
                    fail('INTERRUPTED_CONTAINER_EVIDENCE_INVALID')
                self.before[name]={
                    'Id':item['id'],'Image':item['image'],
                    'State':{'StartedAt':item['started_at']},
                }
            if consumption_missing:
                # The process died after recording intent but before writing
                # the one-use Owner consumption file. Only original, untouched
                # host state can be declared safe. Never mint/reuse the proof.
                if (ROOT_POLICY.exists() or ROOT_POLICY.is_symlink()
                        or BUNDLE_ROOT.exists() or BUNDLE_ROOT.is_symlink()
                        or sha256(secure_blob(WORKER,mode=0o755)).hexdigest()
                           !=self.plan['rollback_root_worker_sha256']):
                    self.open_root_production_breaker('CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED')
                    fail('ROOT_MUTATION_WITHOUT_DURABLE_OWNER_CONSUMPTION')
                active=subprocess.run(['systemctl','is-active',TIMER],
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,
                    check=False,text=True)
                if active.stdout.strip()=='active':
                    self.open_root_production_breaker('CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED')
                    fail('RECOVERY_TIMER_ACTIVE_WITHOUT_OWNER_CONSUMPTION')
                self._unchanged(self.plan)
                self._audit('interrupted_before_owner_consumption_verified')
                return {'status':'interrupted_before_owner_consumption_verified',
                        'source_sha':self.plan['source_sha'],
                        'original_freeze_restored':True,
                        'approval_reusable':False,
                        'runtime_mcp_promotion_approved':False,
                        'provider_write_approved':False}
            if journal.get('status') in {
                    'exact_catalog_root_install_verified',
                    'root_install_verified_freeze_unchanged',
            }:
                # Never reinterpret an already completed root install as
                # authorization to promote images or write to Autotask.
                self._unchanged(self.plan)
                return {'status':'already_installed_no_recovery_required',
                        'source_sha':self.plan['source_sha'],
                        'promotion_approved':False,'provider_write_approved':False}
            if journal.get('status') in {
                    'catalog_root_rolled_back_verified',
                    'exact_old_root_worker_and_freeze_rollback_verified',
                    'root_install_backup_failed_before_mutation',
            }:
                return {'status':'previous_attempt_already_resolved',
                        'source_sha':self.plan['source_sha'],
                        'promotion_approved':False,'provider_write_approved':False}
            backup=self._ledger_dir('root-installer-backup')/'release-host-reconcile-worker.original'
            if backup.is_file():
                # A partial install may have swapped the worker. Restore
                # exactly the recorded immutable original bytes and check
                # the original freeze and all protected containers.
                try:
                    self.restore_original_worker_units_and_state(self.plan)
                    self.independently_verify_rollback_and_freeze(self.plan)
                except BaseException:
                    self.open_root_production_breaker('CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED')
                    self._audit('catalog_root_rollback_unverified')
                    raise
            else:
                # A missing backup is safe ONLY if no installed root change
                # exists. Never guess that an incomplete journal was harmless.
                if (ROOT_POLICY.exists() or BUNDLE_ROOT.exists()
                        or sha256(secure_blob(WORKER,mode=0o755)).hexdigest()
                           !=self.plan['rollback_root_worker_sha256']):
                    self.open_root_production_breaker('CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED')
                    fail('INTERRUPTED_INSTALL_MISSING_BACKUP_AFTER_MUTATION')
                self._unchanged(self.plan)
            self._audit('catalog_root_rolled_back_verified')
            return {'status':'interrupted_exact_root_install_rolled_back_verified',
                    'source_sha':self.plan['source_sha'],
                    'original_freeze_restored':True,
                    'approval_reusable':False,
                    'runtime_mcp_promotion_approved':False,
                    'provider_write_approved':False}


def load_bootstrap_plan(*,expected_plan_sha256:str,evidence_root:Path)->tuple[dict[str,Any],dict[str,Any]]:
    if (not HEX64.fullmatch(expected_plan_sha256)
            or not evidence_root.is_absolute() or evidence_root.is_symlink()
            or evidence_root.name!='catalog-scoped-root-install-20261117'
            or evidence_root.parent!=Path('/srv/jason/archive/engineering-evidence')):
        fail('UNTRUSTED_EVIDENCE_ROOT_OR_PLAN_HASH')
    path=evidence_root/'unsigned-root-install-plan.json'
    if path.is_symlink() or not path.is_file():fail('ROOT_INSTALL_PLAN_NOT_FOUND')
    st=path.lstat()
    if (st.st_uid!=pwd.getpwnam('al').pw_uid or st.st_mode&0o022
            or st.st_size>131072 or st.st_nlink!=1):
        fail('ROOT_INSTALL_PLAN_FILE_UNTRUSTED')
    plan=json.loads(path.read_bytes())
    result=transaction.verify_plan(plan)
    if result['install_plan_sha256']!=expected_plan_sha256:
        fail('EXACT_ROOT_INSTALL_PLAN_HASH_MISMATCH')
    raw=secure_blob(POLICY,mode=0o600,maximum=8192)
    trust=json.loads(raw)
    return result,trust


def main()->int:
    parser=argparse.ArgumentParser(description='Trusted one-use catalog root installer; no image promotion')
    cmd=parser.add_mutually_exclusive_group(required=True)
    cmd.add_argument('--check-only',action='store_true')
    cmd.add_argument('--execute',action='store_true')
    cmd.add_argument('--recover',action='store_true')
    parser.add_argument('--exact-plan-sha256',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0 or sys.flags.isolated!=1 or Path(__file__).resolve()!=ENTRY:
        fail('ROOT_INSTALLED_ISOLATED_EXECUTION_REQUIRED')
    plan,trust=load_bootstrap_plan(
        expected_plan_sha256=args.exact_plan_sha256,
        evidence_root=Path('/srv/jason/archive/engineering-evidence/catalog-scoped-root-install-20261117'),
    )
    host=NativeRootInstaller(plan,Path('/srv/jason/archive/engineering-evidence/catalog-scoped-root-install-20261117'),trust)
    host.verify_root_bootstrap_trust(allow_existing_catalog_policy=args.recover)
    if args.recover:
        print(json.dumps(host.recover_interrupted(),sort_keys=True))
        return 0
    if args.check_only:
        # Never claims production eligible or installed and never consumes an
        # Owner challenge. No root file modifications in this path.
        host.independent_live_source_ci_and_freeze(plan)
        host.deny_prior_attempt_or_changed_root_files(plan)
        print(json.dumps({'status':'ROOT_INSTALL_READONLY_PREFLIGHT_PASS_NOT_APPROVED',
            'source_sha':plan['source_sha'],
            'install_scope_sha256':plan['installation_scope_sha256'],
            'plan_sha256':plan['install_plan_sha256'],
            'production_mutations':False,'owner_approval_recorded':False},sort_keys=True))
        return 0
    result=transaction.execute_root_install_transaction(plan,host)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
