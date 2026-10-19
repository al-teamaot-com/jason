#!/usr/bin/env python3
"""Root-only bounded circuit breaker transition processor.

The caller requests an intent, never an arbitrary replacement JSON document.
"""
from __future__ import annotations
import datetime
import fcntl
import json
import os
import pwd
import re
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT=Path('/var/lib/jason/openclaw/release-manager')
REQUESTS=ROOT/'protected-transitions'/'requests'
RESULTS=ROOT/'protected-transitions'/'results'
CONTROL=ROOT/'production-control-state.json'
DRIFT=ROOT/'production-drift.json'
LOCK=ROOT/'protected-transitions'/'root-control.lock'
DRIFT_CONFIG=Path('/etc/jason/release-readback-recovery/production-desired-state.json')
DRIFT_EVALUATOR=Path('/opt/jason/current/tools/production_drift_guard.py')
SHA=re.compile(r'[0-9a-f]{40}\Z')
RID=re.compile(r'[0-9a-f]{32}\Z')
PROTECTED_LKG_FIELDS=(
    'revision', 'runtime_revision', 'runtime_image_id',
    'mcp_revision', 'mcp_image_id', 'host_revision', 'host_release',
    'release_manager_source_revision', 'desired_state_policy_digest',
    'scheduled_control_units',
)


def verify_immutable_lkg_fingerprint(recorded: dict, observed: dict) -> None:
    if recorded.get('complete') is not True or observed.get('complete') is not True:
        raise ValueError('incomplete independent baseline verification')
    for key in PROTECTED_LKG_FIELDS:
        left, right = recorded.get(key), observed.get(key)
        if left is None or right is None or left != right:
            raise ValueError('immutable last-known-good mismatch: ' + key)




def protected_read(path: Path) -> dict:
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o077:
            raise PermissionError('root-only mode-0600 file required')
        with os.fdopen(fd,'r',closefd=False) as f: data=json.load(f)
    finally:os.close(fd)
    if not isinstance(data,dict) or data.get('schema_version')!='1.0':
        raise ValueError('protected evidence schema invalid')
    return data


def read_request(path: Path) -> dict:
    if not RID.fullmatch(path.stem) or path.suffix!='.json':
        raise ValueError('invalid request filename')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=pwd.getpwnam('al').pw_uid or st.st_mode&0o077:
            raise PermissionError('invalid requester ownership')
        with os.fdopen(fd,'r',closefd=False) as f:req=json.load(f)
    finally:os.close(fd)
    if not isinstance(req,dict) or req.get('request_id')!=path.stem:
        raise ValueError('request id mismatch')
    if set(req)-{'request_id','action','revision','release_id','reason'}:
        raise ValueError('unsupported request fields')
    if req.get('action') not in {'open','revalidate','set_last_known_good'}:
        raise ValueError('unsupported transition')
    if not SHA.fullmatch(str(req.get('revision') or '')):
        raise ValueError('exact revision required')
    return req


def verify_health(revision: str) -> dict:
    code='import json,sys;sys.path.insert(0,"/home/al/.local/lib/jason");import release_manager_host_runner as r;print(json.dumps(r.capture_production_manifest("'+revision+'")))'
    result=subprocess.check_output(['runuser','-u','al','--','python3','-c',code],text=True,timeout=70)
    manifest=json.loads(result)
    if manifest.get('revision')!=revision or manifest.get('complete') is not True:
        raise ValueError('independent production health not verified')
    return manifest


def refresh_stale_drift() -> None:
    """Regenerate drift from the independent policy while transaction lock is held.

    The normal watchdog defers under the production transaction lock. Never
    extend the 180-second validity window or trust caller-provided evidence:
    run the immutable production guard against the root-controlled policy,
    require a clean result, and atomically persist root-owned evidence.
    """
    for path in (DRIFT_CONFIG, DRIFT_EVALUATOR):
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or (info.st_mode & 0o002):
            raise PermissionError('root-owned drift evaluator and policy required')
    result=subprocess.run(
        ['/usr/bin/python3',str(DRIFT_EVALUATOR),'--config',str(DRIFT_CONFIG)],
        capture_output=True,text=True,timeout=70,check=False,
    )
    if result.returncode!=0:
        raise ValueError('independent production drift refresh did not pass')
    payload=json.loads(result.stdout)
    if (payload.get('schema_version')!='1.0' or payload.get('status')!='pass'
            or payload.get('problems') or not payload.get('observed_at')):
        raise ValueError('independent drift refresh failed closed')
    # Persist only validated, independently generated root-owned evidence.
    write_json(DRIFT,payload,0,0)


def verify_drift() -> None:
    drift=protected_read(DRIFT)
    if drift.get('status')!='pass' or drift.get('problems'):
        raise ValueError('production drift is not clean')
    observed=datetime.datetime.fromisoformat(drift['observed_at'].replace('Z','+00:00'))
    age=(datetime.datetime.now(datetime.timezone.utc)-observed).total_seconds()
    if not -10 <= age <= 180:
        refresh_stale_drift()
        drift=protected_read(DRIFT)
        if drift.get('status')!='pass' or drift.get('problems'):
            raise ValueError('independent drift refresh did not pass')
        observed=datetime.datetime.fromisoformat(drift['observed_at'].replace('Z','+00:00'))
        age=(datetime.datetime.now(datetime.timezone.utc)-observed).total_seconds()
        if not -10 <= age <= 180:
            raise ValueError('root-owned drift evidence is stale after independent refresh')


def apply_transition(req: dict, state: dict) -> dict:
    action=req['action'];revision=req['revision']
    if action=='open':
        state['circuit_breaker']={'state':'open','reason':str(req.get('reason') or 'release_failure')[:300],
                                   'source':'root_governed_transition','updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        return state
    verify_drift()
    if action=='revalidate':
        last=state.get('last_known_good') or {}
        if last.get('manifest',{}).get('revision')!=revision:
            raise ValueError('last known good revision mismatch')
        manifest=verify_health(revision)
        verify_immutable_lkg_fingerprint(last['manifest'],manifest)
        state['last_revalidation']=manifest
    else:
        release_id=str(req.get('release_id') or '')
        base_id='release-'+revision[:16]
        if release_id != base_id and not re.fullmatch(re.escape(base_id)+r'-retry-[1-9][0-9]{0,2}',release_id):
            raise ValueError('release identity mismatch')
        path=ROOT/'records'/(release_id+'.json')
        record=json.loads(path.read_text())
        if release_id != base_id:
            historical=json.loads((ROOT/'records'/(base_id+'.json')).read_text())
            if historical.get('state')!='rolled_back' or (historical.get('failure') or {}).get('rollback_verified') is not True:
                raise ValueError('retry historical rollback is not verified')
            if (historical.get('release_candidate') or {}).get('candidate_sha')!=revision:
                raise ValueError('retry historical candidate mismatch')
            if record.get('reissued_from')!=base_id or (record.get('release_candidate') or {}).get('candidate_sha')!=revision:
                raise ValueError('retry release candidate linkage mismatch')
        if record.get('state') not in {'production','closed'} or record.get('owner_approval',{}).get('approved') is not True or record['owner_approval'].get('candidate_sha')!=revision:
            raise ValueError('record lacks exact production approval')
        manifest=verify_health(revision)
        state['last_known_good']={'release_id':release_id,'manifest':manifest,'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    state['circuit_breaker']={'state':'closed','reason':'root_verified_'+action,'revalidated_revision':revision,
                              'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    return state


def write_json(path:Path, value:dict, owner_uid:int, owner_gid:int) -> None:
    fd,name=tempfile.mkstemp(prefix='.transition-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chown(name,owner_uid,owner_gid);os.chmod(name,0o600)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def process() -> None:
    if os.geteuid()!=0:raise PermissionError('root only')
    al=pwd.getpwnam('al')
    with LOCK.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for path in sorted(REQUESTS.glob('*.json')):
            try:
                req=read_request(path)
                state=protected_read(CONTROL)
                result=apply_transition(req,state)
                write_json(CONTROL,result,0,0)
                assert protected_read(CONTROL)['circuit_breaker']==result['circuit_breaker']
                response={'request_id':req['request_id'],'success':True,'action':req['action'],'revision':req['revision']}
            except Exception as ex:
                response={'request_id':path.stem,'success':False,'detail':type(ex).__name__+': '+str(ex)[:250]}
            write_json(RESULTS/(path.stem+'.json'),response,al.pw_uid,al.pw_gid)
            path.unlink()

if __name__=='__main__':process()
