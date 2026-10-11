#!/usr/bin/env python3
"""Root-only, fail-closed, one-shot production circuit-breaker revalidation."""
import argparse
import datetime
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path('/var/lib/jason/openclaw/release-manager')
CONTROL = ROOT/'production-control-state.json'
DRIFT = ROOT/'production-drift.json'
LOCK = ROOT/'production-transaction.lock'
CONTROLLER = Path('/home/al/.local/lib/jason/release_manager_host_runner.py')
SOURCE = Path('/home/al/.local/lib/jason/release-manager-source')
SHA = re.compile(r'[0-9a-f]{40}\Z')


def read_protected(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        meta=os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o077:
            raise PermissionError('invalid root protected file ownership or permissions')
        with os.fdopen(fd,'r',closefd=False) as h:
            result=json.load(h)
    finally:
        os.close(fd)
    if not isinstance(result,dict) or result.get('schema_version')!='1.0':
        raise ValueError('invalid protected state schema')
    return result


def validate(control,drift,revision):
    if not SHA.fullmatch(revision):
        raise ValueError('exact revision required')
    if control.get('circuit_breaker',{}).get('state') != 'open':
        raise ValueError('expected open circuit breaker')
    if control.get('last_known_good',{}).get('manifest',{}).get('revision') != revision:
        raise ValueError('last-known-good revision mismatch')
    if drift.get('status') != 'pass' or drift.get('problems'):
        raise ValueError('production drift has not passed')
    timestamp=datetime.datetime.fromisoformat(drift['observed_at'].replace('Z','+00:00'))
    age=(datetime.datetime.now(datetime.timezone.utc)-timestamp).total_seconds()
    if age < -10 or age > 180:
        raise ValueError('drift result stale or in future')


def revalidate(revision,apply=False):
    if os.geteuid()!=0:
        raise PermissionError('root required even for dry-run')
    with LOCK.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        control=read_protected(CONTROL)
        drift=read_protected(DRIFT)
        validate(control,drift,revision)
        # Independent operator-facing health checks are executed as the owner,
        # not by trusting editable snapshot contents or caller claims.
        code=('import sys;sys.path.insert(0,"/home/al/.local/lib/jason");'
              'import release_manager_host_runner as r;'
              f'r.capture_production_manifest("{revision}")')
        subprocess.run(['runuser','-u','al','--','python3','-c',code],check=True,timeout=50)
        if not apply:
            print('ROOT_BREAKER_REVALIDATION=READY')
            return
        # Re-read evidence after health checks while holding transaction lock.
        control=read_protected(CONTROL)
        drift=read_protected(DRIFT)
        validate(control,drift,revision)
        now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
        control['circuit_breaker']={'state':'closed','reason':'root_authoritative_health_revalidated',
                                    'revalidated_revision':revision,'revalidated_at':now,'updated_at':now}
        control['updated_at']=now
        fd,name=tempfile.mkstemp(dir=ROOT,prefix='.root-revalidated-')
        try:
            with os.fdopen(fd,'w') as writer:
                json.dump(control,writer,indent=2,sort_keys=True)
                writer.write('\n');writer.flush();os.fsync(writer.fileno())
            os.chown(name,0,0);os.chmod(name,0o600)
            os.replace(name,CONTROL)
        finally:
            if os.path.exists(name):os.unlink(name)
        if read_protected(CONTROL)['circuit_breaker']['state']!='closed':
            raise ValueError('post-write root readback failed')
        print('ROOT_BREAKER_REVALIDATION=PASS')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--revision',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    revalidate(a.revision,a.apply)
