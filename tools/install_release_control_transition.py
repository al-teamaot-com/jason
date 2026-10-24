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
    # Apply only the four specifically reviewed #1974 unit declarations to
    # the independently root-controlled overlay, AFTER the candidate host
    # worker (including symmetric rollback support) has been installed.
    # This runs inside the existing exact-SHA host reconciliation transaction.
    import protected_root_policy_migration as migration
    control=migration._json(migration._root_only(
        Path('/var/lib/jason/openclaw/release-manager/production-control-state.json')))
    baseline=str(((control.get('last_known_good') or {}).get('manifest') or {}).get('revision') or '')
    candidate=BASE.name
    if migration.SHA.fullmatch(candidate) and migration.SHA.fullmatch(baseline) and candidate != baseline:
        prior=migration._source_policy(baseline)
        target=migration._source_policy(candidate)
        # Commit only an already staged, exact SHA and OWNER+CCC-reviewed
        # plan after host unit install. Never decide scope from one hardcoded
        # historical timer: the installed root migrator validates all fields.
        changed_units=any(
            set(prior[field]) != set(target[field])
            for field in migration.UNIT_FIELDS
        )
        if changed_units:
            outcome=migration.apply_for_candidate(candidate,baseline)
            print('JASON_ROOT_PROTECTED_POLICY_MIGRATION=' + outcome)

    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','jason-release-control-transition.timer'],check=True)
    subprocess.run(['systemctl','start','jason-release-control-transition.service'],check=True)
    print('ROOT_RELEASE_TRANSITION_INSTALL=PASS')

if __name__=='__main__':install()
