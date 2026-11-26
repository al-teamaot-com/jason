"""Read-only exact source and local Docker admission for Jason Owner MCP overlay.

Never grants Owner authority, creates a native release, mints signatures,
mutates provider state, changes the freeze or replaces production containers.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

SRC='ec891ae49428357ccae8fa3b990c021a124b41d9'
REVIEWED='61b9ce79316f6bf2eb9da9835ccf3f9015a6c71d'
ROLLBACK='d1b8c196dadd4b672ec8ba47075f27bb61c98d63'
FREEZE_SHA='bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f'
OWNER='bee80bdc-ffb0-4c50-b453-c09d4d411f5f'
TENANT='f7054323-d52b-4863-8c2f-1898f0b6077c'
MS_ADMIN='c848022d-e13b-4457-84b0-e2f5c00dcaf6'
EXPECTED_PATHS=frozenset({
 'config/jason-owner-authorization-profile.json',
 'implementation/mcp_service/src/jason_mcp/server.py',
 'implementation/mcp_service/tests/test_jason_licensed_owner_profile.py',
 'infrastructure/jason-mcp/production-deploy.sh',
 'tools/jason_owner_auth_profile.py',
 'tools/release_manager_host_runner.py',
 'tools/tests/test_admin_separated_deploy_contract.py',
 'tools/tests/test_jason_owner_auth_profile.py',
})
MANIFEST_FIELDS=frozenset({
 'schema_version','profile','candidate_sha','reviewed_owner_source_sha',
 'rollback_sha','owner_tenant_id','owner_object_id','microsoft_admin_object_id',
 'source_scope_files','source_file_sha256','candidate_server_sha256',
 'candidate_mcp_image_id','rollback_mcp_image_id','unchanged_runtime_image_id',
 'freeze_sha256','isolated_rollback_receipt_sha256','new_mcp_env',
 'rollback_mcp_env','mcp_container_only','runtime_replacement_authorized',
 'pmv4_core_replacement_authorized','provider_writes_authorized',
 'one_use_signed_owner_approval_required','native_production_release_authorized',
})
HASH=re.compile('^[0-9a-f]{64}$')
IMAGE=re.compile('^sha256:[0-9a-f]{64}$')

class ScopedOwnerDenied(PermissionError):pass

def need(condition,code):
 if not condition:raise ScopedOwnerDenied('OWNER_SCOPED_RELEASE_'+code)

def validate(manifest:Mapping[str,Any])->dict:
 need(isinstance(manifest,Mapping) and set(manifest)==MANIFEST_FIELDS,'SCHEMA')
 m=dict(manifest)
 need(m['schema_version']=='1.0' and m['profile']=='jason-owner-only-scoped-mcp-v1','PROFILE')
 need((m['candidate_sha'],m['rollback_sha'],m['reviewed_owner_source_sha'])==(SRC,ROLLBACK,REVIEWED),'SOURCE_REVISION')
 need((m['owner_tenant_id'],m['owner_object_id'],m['microsoft_admin_object_id'])==(TENANT,OWNER,MS_ADMIN),'EXACT_OWNER')
 need(m['source_scope_files']==sorted(EXPECTED_PATHS) and isinstance(m['source_file_sha256'],dict) and set(m['source_file_sha256'])==EXPECTED_PATHS,'CODE_FILES')
 need(all(type(v) is str and HASH.fullmatch(v) for v in m['source_file_sha256'].values()),'FILE_HASHES')
 need(m['candidate_server_sha256']==m['source_file_sha256']['implementation/mcp_service/src/jason_mcp/server.py'],'SERVER_DIGEST')
 need(all(type(m[k]) is str and IMAGE.fullmatch(m[k]) for k in ('candidate_mcp_image_id','rollback_mcp_image_id','unchanged_runtime_image_id')),'IMAGE_IDS')
 need(m['candidate_mcp_image_id']!=m['rollback_mcp_image_id'] and m['freeze_sha256']==FREEZE_SHA and type(m['isolated_rollback_receipt_sha256']) is str and HASH.fullmatch(m['isolated_rollback_receipt_sha256']),'ROLLBACK')
 need(m['new_mcp_env']=={'JASON_AOT_ADMIN_APPROVER_PROFILE':'jason-owner-v1'} and m['rollback_mcp_env']=={'JASON_AOT_ADMIN_APPROVER_PROFILE':''},'EXACT_ENV')
 need(all(type(m[k]) is bool and m[k] is False for k in ('runtime_replacement_authorized','pmv4_core_replacement_authorized','provider_writes_authorized','native_production_release_authorized')),'UNAUTHORIZED_PRODUCTION_SCOPE')
 need(m['mcp_container_only'] is True and m['one_use_signed_owner_approval_required'] is True,'EXACT_ONE_USE_BOUNDARY')
 return m

def git(repo:Path,*args:str)->str:
 p=subprocess.run(['git','-C',str(repo),*args],text=True,capture_output=True,check=False,timeout=40)
 need(p.returncode==0,'GIT_TRUST_EVIDENCE_MISSING');return p.stdout.strip()

def verify_source(repo:Path, m:Mapping[str,Any])->dict:
 m=validate(m)
 need(git(repo,'rev-parse',m['candidate_sha']+'^')==ROLLBACK,'CANDIDATE_NOT_LKG_DESCENDANT')
 names=set(git(repo,'diff','--name-only',ROLLBACK,m['candidate_sha']).splitlines())
 need(names==EXPECTED_PATHS|{'config/jason-owner-only-lkg-overlay.json','docs/operations/Jason-Owner-LKG-Scoped-Backport-20261119.md'},'UNREVIEWED_CODE_CHANGE')
 for file,expected in m['source_file_sha256'].items():
  data=subprocess.run(['git','-C',str(repo),'show',SRC+':'+file],capture_output=True,check=False,timeout=15)
  need(data.returncode==0 and sha256(data.stdout).hexdigest()==expected,'EXACT_SOURCE_BYTES_CHANGED')
 in_main=subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',REVIEWED,'origin/main'],check=False,capture_output=True)
 need(in_main.returncode==0,'REVIEWED_OWNER_NOT_MERGED')
 return {'status':'exact_lkg_descendant_source_verified','production_mutations':False,'candidate_sha':SRC,'rollback_sha':ROLLBACK,'code_file_count':len(EXPECTED_PATHS)}

def verify_host(repo:Path,m:Mapping[str,Any],private_receipt:Path)->dict:
 m=validate(m)
 src=verify_source(repo,m)
 need(private_receipt.exists() and not private_receipt.is_symlink() and sha256(private_receipt.read_bytes()).hexdigest()==m['isolated_rollback_receipt_sha256'],'ISOLATED_ROLLBACK_RECEIPT_MISSING_OR_CHANGED')
 receipt=json.loads(private_receipt.read_text())
 need(receipt.get('status')=='isolated_owner_mcp_rollback_verified' and receipt.get('live_protected_snapshot_unchanged') is True and receipt.get('candidate_image_id')==m['candidate_mcp_image_id'] and receipt.get('rollback_image_id')==m['rollback_mcp_image_id'],'ISOLATED_ROLLBACK_NOT_ACCEPTED')
 def inspect(*args):
  p=subprocess.run(['docker',*args],capture_output=True,text=True,check=False,timeout=35)
  need(p.returncode==0,'DOCKER_READ_UNAVAILABLE');return json.loads(p.stdout)
 image=inspect('image','inspect',m['candidate_mcp_image_id'])[0]
 need(image['Id']==m['candidate_mcp_image_id'] and image['Config']['Labels']['com.teamaot.jason.source_revision']==SRC,'CANDIDATE_IMAGE_SOURCE_DRIFT')
 active=inspect('inspect','jason-mcp-pilot','jason-runtime')
 by_name={x['Name'].lstrip('/'):x for x in active}
 need(by_name['jason-mcp-pilot']['Image']==m['rollback_mcp_image_id'] and by_name['jason-runtime']['Image']==m['unchanged_runtime_image_id'],'LIVE_BASELINE_DRIFT')
 freeze=Path('/var/lib/jason/openclaw/release-manager/production-deployment-freeze')
 need(freeze.is_file() and sha256(freeze.read_bytes()).hexdigest()==FREEZE_SHA,'PROTECTED_FREEZE_CHANGED')
 return {**src,'status':'owner_mcp_candidate_image_and_rollback_verified_NOT_RELEASE_AUTHORIZED','candidate_mcp_image_id':m['candidate_mcp_image_id'],'rollback_mcp_image_id':m['rollback_mcp_image_id'],'freeze_intact':True,'signed_owner_release_consumed':False,'native_release_admission':False,'provider_writes':False}

if __name__=='__main__':
 repo=Path(__file__).resolve().parents[1]
 m=json.loads((repo/'config/jason-owner-only-scoped-release.json').read_text())
 receipt=Path('/home/al/.local/share/jason/owner-only-release-20261119/isolated-rollback-receipt-pinned.json')
 print(json.dumps(verify_host(repo,m,receipt),sort_keys=True,indent=2))
