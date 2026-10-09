#!/usr/bin/env python3
"""Install audited root-only transition worker and request/result folders."""
import os
import json
import tempfile
import pwd
import shutil
import subprocess
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
ROOT=Path('/var/lib/jason/openclaw/release-manager/protected-transitions')

def install():
    if os.geteuid()!=0:raise PermissionError('root install required')
    al=pwd.getpwnam('al')
    for name in ('requests','results'):
        path=ROOT/name
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chown(path,al.pw_uid,al.pw_gid);os.chmod(path,0o700)
    lock=ROOT/'root-control.lock'
    if not lock.exists():lock.touch(mode=0o600)
    os.chown(lock,0,0);os.chmod(lock,0o600)
    dst=Path('/usr/local/lib/jason/release_control_transition_worker.py')
    shutil.copyfile(BASE/'tools/release_control_transition_worker.py',dst)
    os.chown(dst,0,0);os.chmod(dst,0o755)
    for suffix in ('timer','service'):
        name='jason-release-control-transition.'+suffix
        dest=Path('/etc/systemd/system')/name
        shutil.copyfile(BASE/'infrastructure/openclaw-operations/systemd'/name,dest)
        os.chown(dest,0,0);os.chmod(dest,0o644)
    # If a root-approved recovery policy overlay is installed, declare only
    # these two new root-only units there as well. Preserve every other field.
    recovery=Path('/etc/jason/release-readback-recovery/production-desired-state.json')
    if recovery.is_file():
        data=json.loads(recovery.read_text())
        base=json.loads((BASE/'config/production-desired-state.json').read_text())
        for key,unit in (('required_system_units','jason-release-control-transition.timer'),
                         ('allowed_system_units','jason-release-control-transition.service')):
            if unit not in base.get(key,[]):
                raise ValueError('unit not declared in authoritative desired-state config')
            data[key]=sorted(set(data[key])|{unit})
        fd,temp=tempfile.mkstemp(dir=recovery.parent,prefix='.transition-policy-')
        try:
            with os.fdopen(fd,'w') as f:
                json.dump(data,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
            os.chown(temp,0,0);os.chmod(temp,0o600)
            os.replace(temp,recovery)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','jason-release-control-transition.timer'],check=True)
    subprocess.run(['systemctl','start','jason-release-control-transition.service'],check=True)
    print('ROOT_RELEASE_TRANSITION_INSTALL=PASS')

if __name__=='__main__':install()
