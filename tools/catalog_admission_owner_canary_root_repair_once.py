#!/usr/bin/env python3
"""One-use AOT Owner exact root repair: catalog admission TEST-ONLY version pin.

Only two files: the root-owned catalog source-admission module and its existing
root-private SHA receipt. No image, offer, grant, core service or freeze write.
Native catalog promotion remains separately Owner signed and root governed.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

SOURCE=Path('/home/al/.local/lib/jason/engineering-source-repo')
ROOT=Path('/usr/local/lib/jason/catalog-scoped-promotion')
REL='tools/catalog_scoped_release_admission.py'
INSTALL=ROOT/REL
POLICY=Path('/etc/jason-owner-release/catalog-scoped-promotion-installed.json')
HOST=ROOT/'tools/catalog_scoped_promotion_host.py'
ROUTER=ROOT/'tools/catalog_scoped_promotion_root.py'
HOST_SHA='39b51dda22be70f2468493fc68574fd4085713506d5a270aee863cf8fb697e9d'
ROUTER_SHA='9d34a497012816cc8b4c1dbcbe5ee5c55a644a3bc0ceb188f2e5e3c908160e66'
OLD_SHA='fb73b5d5a6a23c54066dc0440263b6222ab1b02798556c868093a8766ca81d6f'
NEW_SHA='9a1dfe91acf1fd5e8b00c5afb7664ed9dd99ea85dda8e3883145a44f5ecb7b08'
REPAIR_REL='tools/catalog_admission_owner_canary_root_repair_once.py'
AUDIT=Path('/etc/jason-owner-release/catalog-admission-canary-compat-v1')
LOCK=Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')
FREEZE=Path('/var/lib/jason/openclaw/release-manager/production-deployment-freeze')
FREEZE_SHA='bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f'
CONTROL=Path('/var/lib/jason/openclaw/release-manager/production-control-state.json')
DRIFT_POLICY=Path('/etc/jason/release-readback-recovery/production-desired-state.json')
DRIFT_GUARD=Path('/opt/jason/current/tools/production_drift_guard.py')
OWNER_HELPER=Path('/usr/local/lib/jason/owner_signer_recovery.py')
OWNER_HELPER_SHA='24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153'
OWNER_TENANT='f7054323-d52b-4863-8c2f-1898f0b6077c'
OWNER_OID='bee80bdc-ffb0-4c50-b453-c09d4d411f5f'
CONFIRM='APPROVE-CATALOG-ADMISSION-TEST-ONLY-ROOT-TRUST-REPAIR'
REVISION='d1b8c196dadd4b672ec8ba47075f27bb61c98d63'
PROTECTED=('jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core','jason-pmv4-shadow-gateway','jason-teams-gateway','openbao')
SHA=re.compile(r'^[a-f0-9]{40}$')

class Denied(PermissionError):pass

def need(ok,why):
    if not ok:raise Denied('CATALOG_CANARY_ROOT_'+why)

def digest(b):return sha256(b).hexdigest()

def read(path,mode,maxlen=100000):
    need(not path.is_symlink() and path.is_file(),'ROOT_FILE_NOT_REGULAR')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and
             stat.S_IMODE(info.st_mode)==mode and info.st_nlink==1 and
             0<info.st_size<=maxlen,'ROOT_FILE_OWNER_MODE_CHANGED')
        raw=os.read(fd,maxlen+1)
        need(len(raw)==info.st_size,'ROOT_FILE_SIZE_CHANGED')
        return raw
    finally:os.close(fd)

def git(*args):
    p=subprocess.run(['git','-c',f'safe.directory={SOURCE}','-C',str(SOURCE),*args],
        capture_output=True,timeout=40,check=False)
    need(p.returncode==0,'TRUSTED_GIT_UNAVAILABLE')
    return p.stdout

def clean_main(reviewed):
    need(SHA.fullmatch(reviewed) is not None,'REVIEWED_SHA_INVALID')
    main=git('ls-remote','origin','refs/heads/main').decode().split()
    need(len(main)==2 and main[1]=='refs/heads/main' and
         SHA.fullmatch(main[0]) is not None,'PROTECTED_MAIN_INVALID')
    sha=main[0]
    need(git('rev-parse','refs/remotes/origin/main').decode().strip()==sha,
         'PROTECTED_MAIN_NOT_FETCHED')
    p=subprocess.run(['git','-c',f'safe.directory={SOURCE}','-C',str(SOURCE),
        'merge-base','--is-ancestor',reviewed,sha],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    need(p.returncode==0,'REVIEWED_SOURCE_NOT_PROTECTED_ANCESTOR')
    need(git('show',f'{sha}:{REPAIR_REL}')==git('show',f'{reviewed}:{REPAIR_REL}')
         ==Path(__file__).read_bytes(),'EXECUTED_ROOT_SCRIPT_NOT_REVIEWED')
    material=git('show',f'{reviewed}:{REL}')
    need(digest(material)==NEW_SHA and git('show',f'{sha}:{REL}')==material,
         'ADMISSION_MODULE_NOT_REVIEWED')
    need(git('remote','get-url','origin').decode().strip() in
         {'https://github.com/al-teamaot-com/jason.git',
          'https://github.com/al-teamaot-com/jason'},
         'GIT_ORIGIN_UNTRUSTED')
    return sha,material

def containers():
    p=subprocess.run(['docker','inspect',*PROTECTED],capture_output=True,timeout=30)
    need(p.returncode==0,'PROTECTED_CONTAINER_INSPECTION_FAILED')
    rows=json.loads(p.stdout)
    need(len(rows)==len(PROTECTED),'PROTECTED_CONTAINER_COUNT_CHANGED')
    result={}
    for x in rows:
        name=x['Name'].lstrip('/')
        need(name in PROTECTED and x['State']['Running'] is True,
             'PROTECTED_CONTAINER_NOT_RUNNING')
        result[name]={'id':x['Id'],'image':x['Image'],
                       'started_at':x['State']['StartedAt']}
    need(set(result)==set(PROTECTED),'PROTECTED_CONTAINER_SCOPE_CHANGED')
    return result

def drift_clean():
    p=subprocess.run(['/usr/bin/python3',str(DRIFT_GUARD),
        '--config',str(DRIFT_POLICY)],capture_output=True,timeout=100)
    need(p.returncode==0,'INDEPENDENT_DRIFT_NOT_PASS')
    data=json.loads(p.stdout)
    need(data.get('status')=='pass' and data.get('problems')==[],
         'INDEPENDENT_DRIFT_NOT_PASS')
    return data

def guard():
    need(Path('/opt/jason/current').resolve(strict=True).name==REVISION,
         'PROTECTED_HOST_REVISION_CHANGED')
    need(digest(FREEZE.read_bytes())==FREEZE_SHA,'PRODUCTION_FREEZE_CHANGED')
    state=json.loads(read(CONTROL,0o600,limit_control_size()))
    need((state.get('circuit_breaker') or {}).get('state')=='closed',
         'PRODUCTION_BREAKER_NOT_CLOSED')
    drift_clean()
    return containers()

def limit_control_size():return 200000

def preflight(reviewed):
    need(os.geteuid()==0 and os.environ.get('SUDO_USER')=='al',
         'AUTHENTICATED_LOCAL_SUDO_REQUIRED')
    info=Path(__file__).lstat()
    need(not Path(__file__).is_symlink() and info.st_uid==0 and
         stat.S_IMODE(info.st_mode)==0o500 and info.st_nlink==1,
         'ROOT_EXECUTOR_NOT_PINNED')
    main,candidate=clean_main(reviewed)
    old=read(INSTALL,0o644,maxlen=90000)
    need(digest(old)==OLD_SHA,'OLD_ADMISSION_NOT_TRUSTED')
    need(digest(read(HOST,0o644,maxlen=110000))==HOST_SHA,
         'PROTECTED_CATALOG_HOST_CHANGED')
    need(digest(read(ROUTER,0o644,maxlen=100000))==ROUTER_SHA,
         'PROTECTED_CATALOG_ROUTER_CHANGED')
    raw_policy=read(POLICY,0o600,maxlen=9000)
    policy=json.loads(raw_policy)
    need(policy.get('schema_version')=='1.0' and
         policy.get('action')=='catalog-scoped-runtime-mcp-one-release-v1' and
         policy.get('admission_module_sha256')==OLD_SHA,
         'INSTALLED_ADMISSION_RECEIPT_UNTRUSTED')
    new_policy=dict(policy);new_policy['admission_module_sha256']=NEW_SHA
    new_raw=(json.dumps(new_policy,sort_keys=True,indent=2)+'\n').encode()
    need(set(new_policy)==set(policy) and all(new_policy[k]==policy[k]
         for k in policy if k!='admission_module_sha256'),
         'POLICY_CHANGE_OUTSIDE_ONE_SHA')
    txroot=Path('/var/lib/jason-catalog-scoped-promotion')
    info=txroot.lstat()
    need(not txroot.is_symlink() and info.st_uid==0 and
         stat.S_IMODE(info.st_mode)==0o700,'NATIVE_TX_ROOT_UNTRUSTED')
    for path in (txroot/'transactions/release-755fa5fe3f75958f.json',txroot/'active.json'):
        need(not path.exists() and not path.is_symlink(),
             'NATIVE_PRODUCTION_TRANSACTION_ALREADY_EXISTS')
    before=guard()
    return {'main':main,'reviewed':reviewed,'old_module':old,
        'new_module':candidate,'old_policy':raw_policy,'new_policy':new_raw,
        'before':before,'freeze_sha':FREEZE_SHA,
        'old_module_sha256':digest(old),'new_module_sha256':NEW_SHA,
        'policy_before_sha256':digest(raw_policy),
        'policy_after_sha256':digest(new_raw)}

def atomic_root(path,expected,new,mode):
    need(read(path,mode,maxlen=110000)==expected,
         'FILE_CHANGED_UNDER_EXACT_TRANSACTION')
    fd,tmp=tempfile.mkstemp(prefix='.catalog-owner-canary-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(new);out.flush();os.fsync(out.fileno())
        os.chown(tmp,0,0);os.chmod(tmp,mode)
        os.replace(tmp,path)
        dirfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
        need(read(path,mode,maxlen=110000)==new,'ROOT_EXACT_READBACK_FAILED')
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def journal(path,data):
    raw=(json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw);out.flush();os.fsync(out.fileno())

def native_trust_check():
    snippet=("import sys;sys.path.insert(0,'/usr/local/lib/jason/catalog-scoped-promotion');"
             "from tools.catalog_scoped_promotion_host import NativeCatalogHost;"
             "NativeCatalogHost().enforce_installed_production_trust()")
    process=subprocess.run(['/usr/bin/python3','-I','-c',snippet],
        capture_output=True,timeout=90)
    need(process.returncode==0,'PINNED_NATIVE_ROOT_HOST_REJECTED_ADMISSION_RECEIPT')

def owner_sign_in():
    file=OWNER_HELPER
    need(digest(read(file,0o555,maxlen=100000))==OWNER_HELPER_SHA,
         'OWNER_SIGNER_CHANGED')
    spec=importlib.util.spec_from_file_location('pinned_catalog_canary_owner',file)
    need(spec is not None and spec.loader is not None,'PINNED_OWNER_SIGNER_UNLOADABLE')
    auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
    need(auth.TENANT==OWNER_TENANT and OWNER_OID in auth.OWNERS,
         'OWNER_GOVERNANCE_IDENTITY_CHANGED')
    uri='https://login.microsoftonline.com/'+OWNER_TENANT+'/oauth2/v2.0/'
    challenge=auth._form(uri+'devicecode',{'client_id':auth.CLIENT_ID,
        'scope':auth.SCOPE})
    need(all(isinstance(challenge.get(x),str) for x in
         ('verification_uri','user_code','device_code')),
         'OWNER_AUTH_CHALLENGE_INVALID')
    print('BROWSER_VERIFICATION_URL='+challenge['verification_uri'],flush=True)
    print('SIGN_IN_CODE='+challenge['user_code'],flush=True)
    end=time.monotonic()+min(600,int(challenge.get('expires_in',0)))
    wait=max(5,min(20,int(challenge.get('interval',5))))
    while time.monotonic()<end:
        time.sleep(wait)
        response=auth._form(uri+'token',{'grant_type':
            'urn:ietf:params:oauth:grant-type:device_code',
            'client_id':auth.CLIENT_ID,'device_code':challenge['device_code']})
        if isinstance(response.get('access_token'),str):
            principal=auth.jwt_owner(response['access_token'])
            need(principal==OWNER_OID,'OWNER_SUBJECT_NOT_ALLOWED')
            return principal
        if response.get('error')=='slow_down':wait=min(wait+5,20)
        elif response.get('error')!='authorization_pending':
            need(False,'OWNER_AUTH_REJECTED')
    need(False,'OWNER_AUTH_EXPIRED')

def apply(reviewed):
    plan=preflight(reviewed)
    print('EXACT_ACTION=catalog-admission-reviewed-owner-canary-test-only-root-trust-v1',flush=True)
    for key in ('main','reviewed','old_module_sha256','new_module_sha256',
                'policy_before_sha256','policy_after_sha256'):
        print(key.upper()+'='+str(plan[key]),flush=True)
    print('ROOT_WRITES=exact_admission_module_and_single_policy_digest_only',flush=True)
    print('IMAGE_PROMOTION=false; PROVIDER_WRITES=false; PMV4_DEPLOYMENT=false; FREEZE_CHANGE=false',flush=True)
    need(sys.stdin.isatty() and sys.stdout.isatty(),'OWNER_LOCAL_TTY_REQUIRED')
    owner=owner_sign_in()
    need(input('Type '+CONFIRM+' to approve only this root test-source admission correction: ').strip()==CONFIRM,
         'EXACT_OWNER_DECISION_MISSING')
    next_plan=preflight(reviewed)
    need(next_plan==plan,'SCOPE_CHANGED_SINCE_OWNER_APPROVAL')
    AUDIT.mkdir(exist_ok=True,mode=0o700)
    info=AUDIT.lstat()
    need(not AUDIT.is_symlink() and info.st_uid==0 and
         stat.S_IMODE(info.st_mode)==0o700,'ROOT_AUDIT_UNTRUSTED')
    attempt=AUDIT/'one-use-attempt.json'
    complete=AUDIT/'one-use-complete.json'
    need(not attempt.exists() and not complete.exists(),
         'ROOT_ONEUSE_ALREADY_CONSUMED')
    journal(attempt,{'schema_version':'1.0','status':'owner_approval_consumed_before_root_mutation',
        'action':'catalog-admission-reviewed-owner-canary-test-only-root-trust-v1',
        'owner_oid':owner,'reviewed_sha':reviewed,'main':plan['main'],
        'old_module_sha256':plan['old_module_sha256'],
        'new_module_sha256':plan['new_module_sha256'],
        'policy_before_sha256':plan['policy_before_sha256'],
        'policy_after_sha256':plan['policy_after_sha256'],
        'approved_at':datetime.now(timezone.utc).isoformat()})
    fd=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW)
    attempted=[]
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==1000 and
             not info.st_mode&0o002,'PRODUCTION_LOCK_UNTRUSTED')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        again=preflight(reviewed)
        need(again==plan,'ROOT_PLAN_CHANGED_UNDER_LOCK')
        updates=((INSTALL,plan['old_module'],plan['new_module'],0o644),
                 (POLICY,plan['old_policy'],plan['new_policy'],0o600))
        for item in updates:
            attempted.append(item)
            atomic_root(*item)
        native_trust_check()
        need(guard()==plan['before'],'PROTECTED_PMV4_OR_IMAGES_CHANGED')
        journal(complete,{'schema_version':'1.0',
            'status':'exact_catalog_admission_test_source_trust_repair_verified',
            'reviewed_sha':reviewed,'main':plan['main'],
            'owner_oid':owner,'new_module_sha256':NEW_SHA,
            'new_policy_sha256':plan['policy_after_sha256'],
            'production_container_mutations':False,'root_trust_files_changed':True,
            'provider_writes':False,'one_use':True,'completed_at':datetime.now(timezone.utc).isoformat()})
    except BaseException:
        rollback=[]
        for path,old,new,mode in reversed(attempted):
            now=read(path,mode,maxlen=110000)
            if now==new:atomic_root(path,new,old,mode)
            else:need(now==old,'FOREIGN_ROOT_CHANGE_PREVENTS_ROLLBACK')
            rollback.append(str(path))
        journal(AUDIT/'one-use-failed.json',{'status':'failed_closed_original_bytes_restored',
                'restored':rollback,'owner_oid':owner,'reviewed_sha':reviewed})
        raise
    finally:
        try:fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)
    print('CATALOG_TEST_ONLY_ADMISSION_ROOT_TRUST_REPAIR=VERIFIED',flush=True)
    print('CATALOG_PRODUCTION_IMAGES_CHANGED=false',flush=True)

def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-only',action='store_true')
    group.add_argument('--execute',action='store_true')
    p.add_argument('--reviewed-ci-sha',required=True)
    opts=p.parse_args()
    if opts.check_only:
        state=preflight(opts.reviewed_ci_sha)
        print(json.dumps({'status':'CATALOG_TEST_ONLY_ROOT_PREFLIGHT_PASS',
            'source_sha':state['main'],
            'reviewed_sha':state['reviewed'],
            'module_before_sha256':state['old_module_sha256'],
            'module_after_sha256':state['new_module_sha256'],
            'policy_before_sha256':state['policy_before_sha256'],
            'policy_after_sha256':state['policy_after_sha256'],
            'production_mutations':False,'owner_approval_recorded':False},sort_keys=True))
    else:apply(opts.reviewed_ci_sha)
    return 0
if __name__=='__main__':raise SystemExit(main())
