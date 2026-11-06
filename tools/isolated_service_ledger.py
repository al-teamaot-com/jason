#!/usr/bin/env python3
"""Read-only view of independently produced service evidence.

Entries are digest-bound to exact regular files. This is an advisory index, not
a work queue, approval store, or alternative release authority.
"""
from __future__ import annotations
import argparse
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso,sha256_file
 from isolated_service_live_sources import bounded_json,source_age
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso,sha256_file
 from tools.isolated_service_live_sources import bounded_json,source_age

MAX_SERVICES=32
SAFE_NAME=re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
SAFE_FILENAME=re.compile(r"[a-z][a-z0-9-]{1,80}\.json\Z")


def build(config:dict[str,Any],state_root:Path,now:datetime|None=None)->dict[str,Any]:
 current=now or datetime.now(timezone.utc)
 if current.tzinfo is None: raise ValueError('now must be timezone-aware')
 specs=config.get('services')
 if not isinstance(specs,list) or not 1<=len(specs)<=MAX_SERVICES:
  raise ValueError('invalid service registry')
 entries=[];required_problem=False;seen=set()
 for spec in specs:
  if not isinstance(spec,dict): raise ValueError('invalid service entry')
  name,file=spec.get('name'),spec.get('state_file')
  if not isinstance(name,str) or not SAFE_NAME.fullmatch(name) or name in seen:
   raise ValueError('duplicate or invalid service name')
  seen.add(name)
  if not isinstance(file,str) or not SAFE_FILENAME.fullmatch(file):
   raise ValueError('invalid service state filename')
  required=spec.get('required')
  max_age=spec.get('max_age_seconds')
  if type(required) is not bool or type(max_age) is not int or not 1<=max_age<=604800:
   raise ValueError('invalid service freshness policy')
  path=state_root/file
  observed='';age=None;digest='';service_status='unknown';reason=''
  try:
   payload,digest=bounded_json(path)
  except FileNotFoundError:
   freshness='missing';reason='evidence_missing'
  except (OSError,ValueError,TypeError) as exc:
   freshness='invalid';reason='evidence_unreadable_or_invalid'
  else:
   observed=payload.get('observed_at') or ''
   service_status=str(payload.get('status') or 'unknown')
   age,fresh=source_age(observed,current,max_age)
   if payload.get('service') not in {name,('isolated_service_'+name)} or payload.get('schema_version')!='1.0':
    freshness='invalid';reason='service_schema_or_identity_mismatch'
   elif fresh:
    freshness='fresh';reason='verified_read_only_snapshot'
   else:
    freshness='stale';reason='evidence_stale_or_future'
  if required and freshness!='fresh': required_problem=True
  entries.append({'name':name,'required':required,'state_file':file,'freshness':freshness,'reason':reason,'age_seconds':age,'service_status':service_status,'observed_at':observed,'sha256':digest})
 return {'status':'degraded' if required_problem else 'available','entries':entries,'advisory_only':True}


def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--state-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result={'schema_version':'1.0','service':'isolated_service_ledger','observed_at':now_iso(),**build(load_json(a.config),a.state_root)}
 atomic_json(a.output,result);print(result['status']);return 0 if result['status']=='available' else 2
if __name__=='__main__': raise SystemExit(main())
