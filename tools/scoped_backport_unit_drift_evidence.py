#!/usr/bin/env python3
"""Read-only immutable evidence for four scoped-backport installer units.

A valid report is NOT authorization to rewrite the protected root policy or
close the breaker. A separately signed, one-use root-governed transaction must
validate that exact baseline and re-run its native watchdog before promotion.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import subprocess
from typing import Mapping

SOURCE_SHA='6adc19744fc7464ef3ba34d1ce0b3b20e9e69684'
REVIEWED_SHA='6e25af09e90d5b3e6ff85453e3d0859ebe8db9ce'
ROOT_HANDLER_SHA='5ef9c84eadc9b2f78911c78c5198ddcbf6e6b37147693ad18d672ba87022cfa3'
UNITS={
 'jason-scoped-backport-recovery.service':'d91a129e3783554ecb87b72e076353c7c90cd64856a4b0187ee8c5a5ad9b1cde',
 'jason-scoped-backport-recovery.timer':'e15b3973791625a5d817a1892eaf11a6b1ac60cffe86f419cea33a930d56c4fd',
 'jason-scoped-backport-requests.path':'5ed31ef5b204a436a07ed9dfd268f82484242ae4656c813bc287bce0b9a8aa34',
 'jason-scoped-backport-requests.service':'f9cbc38b2612466dee9a603197ee9484d11f2468f744c31140f1ba5683c2a40d',
}
PUBLIC=Path('/etc/jason-owner-release/scoped-backport-public-attestation.json')
ROOT_HANDLER=Path('/usr/local/lib/jason/scoped-backport/tools/scoped_backport_native_root.py')
UNIT_DIR=Path('/etc/systemd/system')
DRIFT=Path('/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json')
FREEZE=Path('/var/lib/jason/openclaw/release-manager/production-deployment-freeze')

class DriftEvidenceDenied(PermissionError): pass

def need(condition,message):
 if not condition:raise DriftEvidenceDenied('SCOPED_UNIT_EVIDENCE_'+message)

def trusted_bytes(path:Path,*,uid=0,limit=32768):
 need(not path.is_symlink() and path.is_file(),'FILE_NOT_REGULAR_'+path.name)
 meta=path.lstat()
 need(meta.st_uid==uid and meta.st_nlink==1 and not(meta.st_mode&0o022) and meta.st_size<=limit,'FILE_OWNERSHIP_'+path.name)
 return path.read_bytes()

def validate(attestation:Mapping, hashes:Mapping[str,str], drift:Mapping, source_policy:Mapping)->dict:
 need(isinstance(attestation,Mapping) and attestation.get('profile')=='governed-scoped-backport-v1' and attestation.get('trusted_source_sha')==SOURCE_SHA and attestation.get('reviewed_ci_sha')==REVIEWED_SHA and attestation.get('root_handler_sha256')==ROOT_HANDLER_SHA and attestation.get('exact_signed_owner_approval_required') is True and attestation.get('native_root_control_supported') is True,'INSTALL_ATTESTATION_MISMATCH')
 need(isinstance(hashes,Mapping) and set(hashes)==set(UNITS)|{'root_handler'} and all(hashes.get(k)==v for k,v in UNITS.items()) and hashes.get('root_handler')==ROOT_HANDLER_SHA,'INSTALLED_UNIT_HASH_MISMATCH')
 need(isinstance(drift,Mapping) and drift.get('status')=='drift_detected' and isinstance(drift.get('problems'),list) and {(x.get('kind'),x.get('unit')) for x in drift['problems'] if isinstance(x,dict)}=={('undeclared_installed_system_unit',u) for u in UNITS} and len(drift['problems'])==4,'UNRELATED_DRIFT_PRESENT')
 need(isinstance(source_policy,Mapping) and source_policy.get('schema_version')=='1.0' and isinstance(source_policy.get('allowed_system_units'),list) and set(UNITS).issubset(source_policy['allowed_system_units']) and len(source_policy['allowed_system_units'])==len(set(source_policy['allowed_system_units'])),'SOURCE_DESIRED_STATE_NOT_EXACT')
 return {'status':'source_units_attested_root_policy_signature_pending','schema_version':'1.0','unit_sha256':dict(sorted(UNITS.items())),'unit_count':4,'trusted_install_source_sha':SOURCE_SHA,'trusted_root_handler_sha256':ROOT_HANDLER_SHA,'root_protected_policy_readback_verified':False,'signed_owner_action_consumed':False,'root_drift_policy_changed':False,'native_breaker_revalidated':False,'production_mutations':False}

def inspect_live():
 att=json.loads(trusted_bytes(PUBLIC).decode())
 hashes={'root_handler':sha256(trusted_bytes(ROOT_HANDLER)).hexdigest()}
 for name in UNITS:hashes[name]=sha256(trusted_bytes(UNIT_DIR/name)).hexdigest()
 drift=json.loads(trusted_bytes(DRIFT,uid=1000,limit=131072))
 policy=json.loads(Path(__file__).resolve().parents[1].joinpath('config/production-desired-state.json').read_text())
 evidence=validate(att,hashes,drift,policy)
 freeze=json.loads(trusted_bytes(FREEZE,uid=1000))
 need(freeze.get('status')=='active','PRODUCTION_FREEZE_CHANGED')
 return evidence

if __name__=='__main__':
 try:print(json.dumps(inspect_live(),sort_keys=True,indent=2))
 except Exception as e:
  print(type(e).__name__+':'+str(e))
  raise SystemExit(2)
