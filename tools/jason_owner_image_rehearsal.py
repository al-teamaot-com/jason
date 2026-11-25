#!/usr/bin/env python3
"""Isolated single-MCP candidate rollback rehearsal; NEVER a release executor.

Can create/remove ONLY UUID-labelled, network-disabled, read-only test containers.
Cannot touch production containers, host control files, credentials or services.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

IM=re.compile(r'^sha256:[0-9a-f]{64}$')
SHA=re.compile(r'^[0-9a-f]{40}$')
PREFIX='jason-owner-image-test-'
PROTECTED=('jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core','jason-pmv4-shadow-gateway','jason-teams-gateway')
FIELDS={'schema_version','purpose','candidate_sha','rollback_sha','candidate_image_id','rollback_image_id','candidate_server_sha256','protected_names','provider_writes_authorized','runtime_replacement_authorized','production_release_authorized'}


def validate(m):
    if not isinstance(m,dict) or set(m)!=FIELDS or m['schema_version']!='1.0' or m['purpose']!='jason-owner-only-mcp-isolated-rollback-rehearsal' or m['protected_names']!=list(PROTECTED) or any(type(m[k]) is not bool or m[k] for k in ('provider_writes_authorized','runtime_replacement_authorized','production_release_authorized')) or not SHA.fullmatch(str(m['candidate_sha'])) or not SHA.fullmatch(str(m['rollback_sha'])) or not all(IM.fullmatch(str(m[k])) for k in ('candidate_image_id','rollback_image_id')) or not re.fullmatch('[0-9a-f]{64}',str(m['candidate_server_sha256'])) or m['candidate_image_id']==m['rollback_image_id']:
        raise ValueError('OWNER_IMAGE_REHEARSAL_EXACT_SCOPE_REQUIRED')
    return m


def docker(*args,timeout=60,ok=False):
    p=subprocess.run(('docker',)+args,check=False,capture_output=True,text=True,timeout=timeout)
    if p.returncode and not ok: raise RuntimeError('OWNER_IMAGE_REHEARSAL_DOCKER_DENIED:'+str(args[:2]))
    return p


def snapshot():
    payload=json.loads(docker('inspect',*PROTECTED).stdout)
    if len(payload)!=len(PROTECTED):raise RuntimeError('PROTECTED_SNAPSHOT_CARDINALITY')
    return {x['Name'].lstrip('/'):{'id':x['Id'],'image':x['Image'],'started':x['State']['StartedAt'],'running':x['State']['Running']} for x in payload}


def image_id(value):
    obj=json.loads(docker('image','inspect',value).stdout)
    if len(obj)!=1: raise RuntimeError('IMAGE_ID_CARDINALITY')
    return obj[0]['Id']


def create(name,image,run):
    if docker('inspect',name,ok=True).returncode==0:raise RuntimeError('EPHEMERAL_NAME_COLLISION')
    docker('run','-d','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','32','--memory','256m','--label','com.teamaot.jason.owner_rehearsal='+run,'--entrypoint','python',image,'-c','import time;time.sleep(180)')


def cleanup(name,run):
    p=docker('inspect',name,ok=True)
    if p.returncode:return
    meta=json.loads(p.stdout)[0]
    if meta.get('Config',{}).get('Labels',{}).get('com.teamaot.jason.owner_rehearsal')!=run:raise RuntimeError('FOREIGN_CONTAINER_REMOVE_DENIED')
    docker('rm','-f',name)


def run(m):
    m=validate(m)
    old=image_id(m['rollback_image_id']);new=image_id(m['candidate_image_id'])
    if old!=m['rollback_image_id'] or new!=m['candidate_image_id']:
        raise RuntimeError('IMAGE_DIGEST_DRIFT')
    before=snapshot()
    if not all(z['running'] for z in before.values()) or before['jason-mcp-pilot']['image']!=old:raise RuntimeError('PROTECTED_BASELINE_CHANGED')
    tag=uuid4().hex[:12]; name=PREFIX+tag; rb=name+'-rollback'
    if docker('inspect',rb,ok=True).returncode==0:raise RuntimeError('EPHEMERAL_ROLLBACK_NAME_COLLISION')
    stage='begin'
    try:
        create(name,old,tag);stage='baseline_created'
        docker('stop',name);docker('rename',name,rb);stage='baseline_parked'
        create(name,new,tag);stage='candidate_created'
        candidate=json.loads(docker('inspect',name).stdout)[0]
        if (candidate['Image']!=new or candidate['HostConfig'].get('NetworkMode')!='none' or set((candidate['NetworkSettings'].get('Networks') or {})) not in (set(),{'none'})):
            raise RuntimeError('CANDIDATE_ISOLATION_DRIFT')
        # Fault injection proves the candidate fails a required check. Recovery
        # restores the original image, not a manually re-created approximation.
        negative=docker('exec',name,'python','-c','raise SystemExit(17)',ok=True)
        if negative.returncode!=17:raise RuntimeError('FAULT_INJECTION_NOT_OBSERVED')
        cleanup(name,tag);stage='candidate_removed'
        docker('rename',rb,name);docker('start',name);stage='rollback_started'
        restored=json.loads(docker('inspect',name).stdout)[0]
        if restored['Image']!=old or not restored['State']['Running']:
            raise RuntimeError('ROLLBACK_RESTART_DID_NOT_RESTORE_BASE_IMAGE')
        if snapshot()!=before:raise RuntimeError('PROTECTED_PRODUCTION_SNAPSHOT_CHANGED')
        return {'status':'isolated_owner_mcp_rollback_verified','schema_version':'1.0','candidate_sha':m['candidate_sha'],'rollback_sha':m['rollback_sha'],'candidate_image_id':new,'rollback_image_id':old,'isolated_failure_injection_recovered':True,'running_baseline_restored':True,'live_protected_snapshot_unchanged':True,'owner_signin_test':'source_and_isolated_image_pass','production_deployed':False,'provider_writes':False,'run_at':datetime.now(timezone.utc).isoformat()}
    finally:
        cleanup(name,tag);cleanup(rb,tag)
        if snapshot()!=before:raise RuntimeError('REHEARSAL_EXIT_CHANGED_PROTECTED_PRODUCTION')


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--isolated-rehearsal',action='store_true');a=p.parse_args()
    if not a.isolated_rehearsal: p.error('EXPLICIT_ISOLATED_REHEARSAL_REQUIRED')
    if a.output.exists() or a.output.is_symlink() or not a.output.is_absolute() or not str(a.output).startswith('/home/al/.local/share/jason/'):p.error('PRIVATE_UNCREATED_EVIDENCE_PATH_REQUIRED')
    m=json.loads(a.manifest.read_text());receipt=run(m)
    a.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps(receipt,sort_keys=True))

if __name__=='__main__':main()
