#!/usr/bin/env python3
"""Temporary root-pinned drift policy bootstrap for approved readback units.

Requires an explicit sudo execution; does not close the circuit breaker.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

MAIN_REPO = Path('/home/al/.local/lib/jason/engineering-worker-source')
CURRENT = Path('/opt/jason/current')
POLICY = Path('/etc/jason/release-readback-recovery/production-desired-state.json')
DROPIN = Path('/etc/systemd/system/jason-production-drift-watchdog.service.d/10-readback-recovery.conf')
ADDITIONS = {'required_system_units': {'jason-release-control-readback.timer'},
             'allowed_system_units': {'jason-release-control-readback.service'}}


def checked_candidate(current: dict, candidate: dict) -> None:
    if set(current) != set(candidate):
        raise ValueError('policy keys changed')
    for key in current:
        old, new = current[key], candidate[key]
        if key in ADDITIONS:
            if not isinstance(old,list) or not isinstance(new,list):
                raise ValueError('unit lists required')
            if set(new) != set(old) | ADDITIONS[key] or set(old) & ADDITIONS[key]:
                raise ValueError('unexpected changed unit declarations')
        elif old != new:
            raise ValueError('unrelated policy change detected: ' + key)


def source_policy(revision: str) -> dict:
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('exact git sha required')
    head = subprocess.check_output(['git','-C',str(MAIN_REPO),'rev-parse','origin/main'],text=True).strip()
    if revision != head:
        raise ValueError('revision not current protected main')
    raw = subprocess.check_output(['git','-C',str(MAIN_REPO),'show',f'{revision}:config/production-desired-state.json'])
    return json.loads(raw)


def install(revision: str, *, dry_run: bool = True) -> None:
    candidate = source_policy(revision)
    old = json.loads((CURRENT/'config/production-desired-state.json').read_text())
    checked_candidate(old,candidate)
    print('RECOVERY_POLICY_DIFF=ONLY_APPROVED_READBACK_UNITS')
    if dry_run:
        return
    if os.geteuid()!=0:
        raise PermissionError('root required')
    if DROPIN.exists() or POLICY.exists():
        raise FileExistsError('recovery override already exists; fail closed')
    POLICY.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    DROPIN.parent.mkdir(parents=True,exist_ok=True)
    POLICY.write_text(json.dumps(candidate,sort_keys=True,indent=2)+'\n')
    os.chown(POLICY,0,0); os.chmod(POLICY,0o600)
    DROPIN.write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 /opt/jason/current/tools/production_drift_watchdog.py --config /etc/jason/release-readback-recovery/production-desired-state.json\n')
    os.chown(DROPIN,0,0); os.chmod(DROPIN,0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','start','jason-production-drift-watchdog.service'],check=False)
    print('RECOVERY_READBACK_POLICY_INSTALLED=PASS')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revision',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    install(args.revision,dry_run=not args.apply)
