#!/usr/bin/env python3
"""Build a nonprivileged exact-source root bootstrap packet; never install it.

A local Owner must separately authenticate sudo and a fresh signed Entra
OID+tenant device flow at the root installer before any production mutation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import shlex
from pathlib import Path
import re
from typing import Any,Mapping

from tools import catalog_scoped_root_install_plan as p
from tools.catalog_scoped_promotion_bundle import FILES, git as source_git

SCRIPT = 'tools/catalog_scoped_root_install_native.py'
TRANSACTION = 'tools/catalog_scoped_root_install_transaction.py'
INSTALL_PLAN = 'tools/catalog_scoped_root_install_plan.py'
SOURCE_BUILDER = 'tools/catalog_scoped_promotion_bundle.py'
ROOT_RECOVERY_SERVICE = 'infrastructure/openclaw-operations/systemd/jason-catalog-root-bootstrap-recovery.service'
ROOT_RECOVERY_TIMER = 'infrastructure/openclaw-operations/systemd/jason-catalog-root-bootstrap-recovery.timer'
SOURCES = tuple(sorted(set(FILES) | {
    SCRIPT,TRANSACTION,INSTALL_PLAN,SOURCE_BUILDER,
    ROOT_RECOVERY_SERVICE,ROOT_RECOVERY_TIMER,
}))
INSTALL_ROOT=Path('/usr/local/lib/jason/catalog-root-bootstrap')
POLICY=Path('/etc/jason-owner-release/catalog-scoped-root-bootstrap-trust.json')
OWNER_VERIFIER=Path('/usr/local/lib/jason/owner_signer_recovery.py')
REPO_NAME='al-teamaot-com/jason'
SHA=re.compile(r'^[a-f0-9]{40}$')
HEX=re.compile(r'^[a-f0-9]{64}$')


class BootstrapPacketDenied(PermissionError):pass


def fail(code:str)->None:raise BootstrapPacketDenied('CATALOG_ROOT_BOOTSTRAP_PACKET_'+code)


def canonical(value:Mapping[str,Any])->bytes:
    return json.dumps(dict(value),sort_keys=True,separators=(',',':'),
                      ensure_ascii=False,allow_nan=False).encode()


def exact_packet(repo:Path,source_sha:str,plan:Mapping[str,Any],
                 original_bundle:Mapping[str,Any],
                 owner_verifier:bytes,*,require_protected_main:bool=True)->dict[str,Any]:
    from tools.catalog_scoped_root_install_transaction import verify_plan
    verified=verify_plan(plan)
    if not isinstance(source_sha,str) or SHA.fullmatch(source_sha) is None:
        fail('SOURCE_SHA_INVALID')
    if verified['source_sha']!=source_sha:
        fail('PLAN_NOT_SAME_PROTECTED_COMMIT')
    if require_protected_main and p.repo_revision(repo)!=source_sha:
        fail('SOURCE_NO_LONGER_PROTECTED_MAIN')
    if (not isinstance(original_bundle,Mapping)
            or original_bundle.get('source_sha')!=source_sha
            or original_bundle.get('status')!='source_only_not_installed'
            or original_bundle.get('production_mutations') is not False
            or original_bundle.get('root_installation_authorized') is not False
            or set(original_bundle.get('files',{}))!=set(FILES)):
        fail('EXACT_ORIGINAL_BUNDLE_NOT_VERIFIED')
    if not isinstance(owner_verifier,bytes) or not 1<=len(owner_verifier)<=200000:
        fail('PINNED_OWNER_VERIFIER_SOURCE_INVALID')
    staged={relative:source_git(repo,'show',source_sha+':'+relative)
            for relative in SOURCES}
    if any(not data or len(data)>500000 for data in staged.values()):
        fail('BOOTSTRAP_SOURCE_BLOB_MISSING')
    sha={relative:sha256(data).hexdigest() for relative,data in staged.items()}
    for relative,reference in original_bundle['files'].items():
        if sha[relative]!=reference['sha256']:
            fail('ORIGINAL_17_FILE_SOURCE_BUNDLE_CHANGED')
    trust={
        'schema_version':'1.0','action':'catalog-root-bootstrap-once-v1',
        'protected_source_sha':source_sha,
        'bootstrap_sha256':sha[SCRIPT],
        'transaction_sha256':sha[TRANSACTION],
        'plan_sha256':verified['install_plan_sha256'],
        'install_scope_sha256':verified['installation_scope_sha256'],
        'evidence_root':'/srv/jason/archive/engineering-evidence/catalog-scoped-root-install-20261117',
        'owner_verifier_sha256':sha256(owner_verifier).hexdigest(),
        'source_bundle_sha256':original_bundle['bundle_sha256'],
        'bootstrap_stage_files':sha,
    }
    packet={
        'schema_version':'1.0',
        'status':'SOURCE_ONLY_BOOTSTRAP_NOT_ROOT_INSTALLED',
        'protected_source_sha':source_sha,
        'install_plan_sha256':verified['install_plan_sha256'],
        'installation_scope_sha256':verified['installation_scope_sha256'],
        'root_bootstrap_trust_policy':trust,
        'bootstrap_staging_file_count':len(SOURCES),
        'stage_files':[
            {'source':rel,'destination':str(INSTALL_ROOT/rel),
             'sha256':sha[rel],'uid':'root','gid':'root',
             'mode':'0555' if rel==SCRIPT else '0644'}
            for rel in SOURCES
        ],
        'root_trust_policy_destination':str(POLICY),
        'signed_entra_owner_approval_recorded':False,
        'privileged_installation_executed':False,
        'automatic_root_elevation':False,
        'runtime_mcp_promotion':False,
        'provider_writes':False,
    }
    packet['packet_sha256']=sha256(canonical(packet)).hexdigest()
    return packet


def write_staged(repo:Path,source_sha:str,destination:Path,packet:Mapping[str,Any])->None:
    target=destination.expanduser().resolve(strict=False)
    if (target.exists() or target.is_symlink()
            or target==Path('/tmp') or Path('/tmp') not in target.parents):
        fail('STAGING_DESTINATION_MUST_BE_NEW_TEMP_DIRECTORY')
    if not target.parent.is_dir() or target.parent.is_symlink() or target.parent.stat().st_uid!=os.getuid():
        fail('STAGING_PARENT_NOT_CURRENT_OPERATOR')
    target.mkdir(mode=0o700)
    try:
        for entry in packet['stage_files']:
            rel=entry['source']
            blob=source_git(repo,'show',source_sha+':'+rel)
            if sha256(blob).hexdigest()!=entry['sha256']:
                fail('STAGED_SOURCE_CHANGED_BETWEEN_READS')
            file=target/rel
            file.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o400)
            try:
                with os.fdopen(fd,'wb',closefd=False) as stream:
                    stream.write(blob);stream.flush();os.fsync(stream.fileno())
            finally:os.close(fd)
        trust=target/'ROOT_BOOTSTRAP_TRUST_POLICY.json'
        trust.write_bytes(canonical(packet['root_bootstrap_trust_policy'])+b'\n')
        trust.chmod(0o400)
        metadata=target/'SOURCE_ONLY_BOOTSTRAP_PACKET.json'
        metadata.write_text(json.dumps(packet,sort_keys=True,indent=2)+'\n')
        metadata.chmod(0o400)
        shell=target/'ROOT_STAGE_AND_AUTHENTICATE_ONCE.sh'
        shell.write_text(stage_script(packet,target),encoding='utf-8')
        shell.chmod(0o400)
    except BaseException:
        # No production paths are touched even if staging is interrupted.
        raise


def stage_script(packet:Mapping[str,Any],staged:Path)->str:
    """Create a reviewable fixed-action root script; never invoke sudo here."""
    if (not isinstance(packet,Mapping) or packet.get('status')!='SOURCE_ONLY_BOOTSTRAP_NOT_ROOT_INSTALLED'
            or packet.get('privileged_installation_executed') is not False
            or packet.get('signed_entra_owner_approval_recorded') is not False
            or not staged.is_absolute() or Path('/tmp') not in staged.parents):
        fail('ROOT_STAGE_SCRIPT_SCOPE_INVALID')
    raw=dict(packet)
    claimed=raw.pop('packet_sha256',None)
    if not isinstance(claimed,str) or sha256(canonical(raw)).hexdigest()!=claimed:
        fail('ROOT_STAGE_SCRIPT_PACKET_HASH_MISMATCH')
    trust=packet['root_bootstrap_trust_policy']
    entries=packet['stage_files']
    if (not isinstance(trust,Mapping) or trust.get('install_scope_sha256')!=packet['installation_scope_sha256']
            or trust.get('plan_sha256')!=packet['install_plan_sha256']
            or trust.get('protected_source_sha')!=packet['protected_source_sha']
            or not isinstance(entries,list) or len(entries)!=len(SOURCES)
            or {x.get('source') for x in entries if isinstance(x,dict)}!=set(SOURCES)):
        fail('ROOT_STAGE_SCRIPT_TRUST_SCOPE_MISMATCH')
    lines=['#!/bin/sh','set -eu','umask 077',
        '[ "$(id -u)" = 0 ] || { echo ROOT_AUTHENTICATION_REQUIRED; exit 1; }',
        'echo EXACT_ACTION=catalog-root-bootstrap-once-v1',
        'echo SOURCE_SHA='+shlex.quote(packet['protected_source_sha']),
        'echo ROOT_INSTALL_SCOPE_SHA256='+shlex.quote(packet['installation_scope_sha256']),
        'echo PLAN_SHA256='+shlex.quote(packet['install_plan_sha256']),
        'echo IMAGE_PROMOTION_APPROVED=false',
        'echo PROVIDER_WRITES_APPROVED=false',
    ]
    for entry in entries:
        dest=entry['destination'];src=str(staged/entry['source'])
        if (dest!=str(INSTALL_ROOT/entry['source'])
                or trust.get('bootstrap_stage_files',{}).get(entry['source'])!=entry['sha256']
                or entry['source'] not in SOURCES
                or entry['uid']!='root' or entry['gid']!='root'
                or entry['mode'] not in ('0555','0644')
                or not HEX.fullmatch(entry['sha256'])):
            fail('UNREVIEWED_ROOT_STAGE_DESTINATION')
        s,d=shlex.quote(src),shlex.quote(dest)
        lines.extend([
            '[ ! -L '+s+' ] && [ -f '+s+' ] || exit 1',
            '[ ! -e '+d+' ] && [ ! -L '+d+' ] || { echo ROOT_BOOTSTRAP_ALREADY_STAGED; exit 1; }',
            'echo '+shlex.quote(entry['sha256']+'  '+src)+' | sha256sum -c - >/dev/null',
            'install -D -o root -g root -m '+entry['mode']+' '+s+' '+d,
            'echo '+shlex.quote(entry['sha256']+'  '+dest)+' | sha256sum -c - >/dev/null',
        ])
    src_policy=staged/'ROOT_BOOTSTRAP_TRUST_POLICY.json'
    policy_bytes=canonical(trust)+b'\n'
    source_policy=str(src_policy);destination_policy=str(POLICY)
    lines.extend([
        '[ ! -L '+shlex.quote(source_policy)+' ] && [ -f '+shlex.quote(source_policy)+' ] || exit 1',
        '[ ! -e '+shlex.quote(destination_policy)+' ] && [ ! -L '+shlex.quote(destination_policy)+' ] || { echo BOOTSTRAP_TRUST_ALREADY_STAGED; exit 1; }',
        'echo '+shlex.quote(sha256(policy_bytes).hexdigest()+'  '+source_policy)+' | sha256sum -c - >/dev/null',
        'install -D -o root -g root -m 0600 '+shlex.quote(source_policy)+' '+shlex.quote(destination_policy),
        'echo '+shlex.quote(sha256(policy_bytes).hexdigest()+'  '+destination_policy)+' | sha256sum -c - >/dev/null',
        'python3 -I '+shlex.quote(str(INSTALL_ROOT/SCRIPT))+
            ' --check-only --exact-plan-sha256 '+shlex.quote(packet['install_plan_sha256']),
        'echo ROOT_STAGING_AND_READONLY_PREFLIGHT_PASSED',
        'echo BEGIN_FRESH_ENTRA_OWNER_AUTHENTICATION_FOR_EXACT_ROOT_INSTALL',
        'python3 -I '+shlex.quote(str(INSTALL_ROOT/SCRIPT))+
            ' --execute --exact-plan-sha256 '+shlex.quote(packet['install_plan_sha256']),
    ])
    return '\n'.join(lines)+'\n'


def main()->int:
    parse=argparse.ArgumentParser(description='Create exact immutable source-only root bootstrap packet')
    parse.add_argument('--repo',type=Path,required=True)
    parse.add_argument('--plan',type=Path,required=True)
    parse.add_argument('--bundle-manifest',type=Path,required=True)
    parse.add_argument('--output',type=Path,required=True)
    args=parse.parse_args()
    repo=args.repo.expanduser().resolve()
    main=p.repo_revision(repo)
    plan=json.loads(args.plan.read_text())
    bundle=json.loads(args.bundle_manifest.read_text())
    st=OWNER_VERIFIER.lstat()
    if (OWNER_VERIFIER.is_symlink() or st.st_uid!=0 or st.st_mode&0o022):
        fail('PINNED_OWNER_VERIFIER_UNTRUSTED')
    data=OWNER_VERIFIER.read_bytes()
    packet=exact_packet(repo,main,plan,bundle,data)
    write_staged(repo,main,args.output,packet)
    print(json.dumps({'status':packet['status'],
        'source_sha':main,'install_plan_sha256':plan['install_plan_sha256'],
        'bootstrap_stage_file_count':len(SOURCES),
        'packet_sha256':packet['packet_sha256'],
        'privileged_installation_executed':False},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
