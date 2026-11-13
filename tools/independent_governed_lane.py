#!/usr/bin/env python3
"""Source-only independent engineering lane admission/execution wrapper.

No new work queue, provider permissions, or production-release controller.
Preserves existing support-first sequencing using one local engineering lease,
while holding the native production transaction's shared lock for an entire
worker run. Missing/failed/stale support receipts defer dependent lanes.
A future exact-SHA release must install this helper BEFORE any independent
lane service may be enabled. Nothing here installs or schedules itself.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_REPO=Path('/home/al/.local/lib/jason/engineering-source-repo')
INSTALLED_ROOT=Path('/home/al/.local/lib/jason')
SPOOL_ROOT=Path('/var/lib/jason/openclaw/support-repair')
PRODUCTION_LOCK=Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')
LEGACY_SERVICE='jason-support-repair-worker.service'
LEGACY_TIMER='jason-support-repair-worker.timer'
WORK_LEASE=SPOOL_ROOT/'independent-engineering-lanes.lock'
GOOD_SUPPORT_MAX_AGE_SECONDS=600
LANES={
 'support':('support_repair_host_worker.py',('--max-active','2'),75*60),
 'todo-intake':('todo_engineering_intake.py',('--max-support-repairs','2'),20*60),
 'development':('owner_approved_development_worker.py',('--max-active','3'),75*60),
 'supervisor':('engineering_supervisor.py',(),10*60),
}
SERIALIZED=frozenset({'support','todo-intake','development'})


class LaneError(ValueError):
    pass


def instant(value:Any)->datetime|None:
    if not isinstance(value,str):return None
    try:result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def support_dependency(lane:str, receipt:dict[str,Any]|None, *,
                       revision:str,now:datetime|None=None)->str:
    if lane not in LANES:raise LaneError('unknown governed engineering lane')
    if lane in {'support','supervisor'}:return 'allowed'
    now=now or datetime.now(timezone.utc)
    if not isinstance(receipt,dict):return 'missing_successful_support_pass'
    t=instant(receipt.get('observed_at'))
    if t is None or t>now or (now-t).total_seconds()>GOOD_SUPPORT_MAX_AGE_SECONDS:
        return 'support_result_stale_or_invalid'
    if receipt.get('status')!='succeeded' or receipt.get('source_revision')!=revision:
        return 'support_result_failed_or_revision_mismatch'
    return 'allowed'


def atomic_json(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temp=tempfile.mkstemp(prefix='.independent-lane-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump(value,stream,sort_keys=True,indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def read_receipt(path:Path)->dict[str,Any]|None:
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_CLOEXEC',0))
    except FileNotFoundError:return None
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_size>16000:
            raise LaneError('invalid support receipt file identity')
        with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read(16001)
        result=json.loads(data)
        if not isinstance(result,dict):raise LaneError('invalid support receipt schema')
        return result
    finally:os.close(fd)


def owned_lock(path:Path,*,existing:bool=False,exclusive:bool=True)->int|None:
    flags=os.O_RDWR if not existing else os.O_RDONLY
    if not existing:flags|=os.O_CREAT
    flags|=getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NONBLOCK',0)
    try:fd=os.open(path,flags,0o600)
    except OSError:return None
    info=os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or info.st_mode & 0o002):
        os.close(fd)
        raise LaneError('untrusted engineering or production transaction lock')
    try:
        fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def source_revision(repo:Path)->str:
    result=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,
                          timeout=12,check=False)
    sha=result.stdout.strip()
    if result.returncode or len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise LaneError('managed source revision not verifiable')
    return sha


def verified_runner(repo:Path,installed:Path,lane:str)->Path:
    if lane not in LANES:raise LaneError('unrecognized independent lane')
    script=LANES[lane][0]
    source=repo/'tools'/script
    binary=installed/script
    if (source.is_symlink() or binary.is_symlink() or
            not source.is_file() or not binary.is_file()):
        raise LaneError('managed or installed worker source missing or symlinked')
    if source.stat().st_size<1 or source.stat().st_size>1024*1024:
        raise LaneError('worker source outside bounded review size')
    if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(binary.read_bytes()).digest():
        raise LaneError('worker differs from pinned managed source')
    return binary


def _systemd_fields(unit:str, properties:tuple[str,...], *, runner=subprocess.run)->dict[str,str]:
    env=os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    env.setdefault('DBUS_SESSION_BUS_ADDRESS',f'unix:path=/run/user/{os.getuid()}/bus')
    args=['systemctl','--user','show',unit]
    for name in properties: args.extend(['-p',name])
    result=runner(args,env=env,capture_output=True,text=True,check=False,timeout=12)
    if result.returncode or len(result.stdout)>4000:return {}
    return dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)


def old_controller_quiescent(runner=subprocess.run)->bool:
    """Prove the legacy engineering controller cannot compete with new lanes.

    This is a technical topology invariant, not Owner authorization. The old
    service must be inactive and its timer must be inactive and disabled or
    masked before a replacement lane can run.
    """
    service=_systemd_fields(LEGACY_SERVICE,('ActiveState',),runner=runner)
    timer=_systemd_fields(LEGACY_TIMER,('ActiveState','UnitFileState'),runner=runner)
    return (service.get('ActiveState')=='inactive'
            and timer.get('ActiveState')=='inactive'
            and timer.get('UnitFileState') in {'disabled','masked'})


def verify_old_controller_quiescent(probe)->None:
    if not probe():
        raise LaneError('old monolithic controller service/timer not quiescent')


def execute(lane:str, *, repo:Path, installed:Path, spool:Path,
            production_lock:Path, legacy_probe=old_controller_quiescent,
            runner=subprocess.run) -> dict[str,Any]:
    if lane not in LANES:raise LaneError('unrecognized independent lane')
    verify_old_controller_quiescent(legacy_probe)
    if spool.is_symlink() or not spool.is_dir():
        raise LaneError('canonical engineering spool unavailable')
    revision=source_revision(repo)
    worker=verified_runner(repo,installed,lane)
    output=spool/('independent-lane-'+lane+'.json')
    # Independent health/reporting lane is not blocked by support worker lock.
    own_lease=lane in SERIALIZED
    work_fd=None
    prod_fd=None
    try:
        if own_lease:
            work_fd=owned_lock(spool/'independent-engineering-lanes.lock')
            if work_fd is None:
                result={'status':'deferred','reason':'engineering_lane_busy'}
                return record(output,lane,revision,result)
        prod_fd=owned_lock(production_lock,existing=True,exclusive=False)
        if prod_fd is None:
            return record(output,lane,revision,{'status':'deferred','reason':'production_transaction_busy'})
        if lane in {'todo-intake','development'}:
            support=read_receipt(spool/'independent-lane-support.json')
            why=support_dependency(lane,support,revision=revision)
            if why!='allowed':
                return record(output,lane,revision,{'status':'deferred','reason':why})
        script,args,timeout=LANES[lane]
        command=[sys.executable,str(worker),'--repo',str(repo),'--spool',str(spool),*args]
        try:
            # Let worker own its governed provider/release restrictions. Never
            # capture credentials, raw provider output, or an unbounded stderr.
            run=runner(command,cwd=str(repo),timeout=timeout,check=False)
            code=int(run.returncode)
            result={'status':'succeeded' if code==0 else 'worker_failed',
                    'reason':'native_worker_completed','return_code':code}
        except subprocess.TimeoutExpired:
            result={'status':'worker_failed','reason':'bounded_worker_timeout'}
        except OSError:
            result={'status':'worker_failed','reason':'native_worker_launch_failed'}
        return record(output,lane,revision,result)
    finally:
        if prod_fd is not None:os.close(prod_fd)
        if work_fd is not None:os.close(work_fd)


def record(output:Path,lane:str,revision:str,result:dict[str,Any])->dict[str,Any]:
    payload={'schema_version':'1.0','service':'independent_governed_lane',
             'lane':lane,'source_revision':revision,
             'observed_at':datetime.now(timezone.utc).isoformat(),
             'advisory_only':True,'production_authority':False,**result}
    atomic_json(output,payload)
    return payload


def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('--lane',choices=sorted(LANES),required=True)
    p.add_argument('--repo',type=Path,default=SOURCE_REPO)
    p.add_argument('--spool',type=Path,default=SPOOL_ROOT)
    args=p.parse_args()
    if (os.getuid()!=1000 or args.repo!=SOURCE_REPO or args.spool!=SPOOL_ROOT
            or args.repo.is_symlink() or args.spool.is_symlink()):
        p.error('only the installed unprivileged canonical governed lane is allowed')
    try:
        result=execute(args.lane,repo=args.repo,installed=INSTALLED_ROOT,
                       spool=args.spool,production_lock=PRODUCTION_LOCK)
    except (LaneError,OSError,ValueError,subprocess.TimeoutExpired):
        # Integrity failures must remain visible as unit failures, not be
        # confused with an approved native worker rejection.
        print('INDEPENDENT_LANE_RESULT=INTEGRITY_FAILURE')
        return 1
    print('INDEPENDENT_LANE_RESULT='+result['status'].upper()+' lane='+args.lane)
    return 0

if __name__=='__main__':raise SystemExit(main())
