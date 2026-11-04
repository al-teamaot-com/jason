#!/usr/bin/env python3
"""Build one authoritative read-only view of isolated service outputs.

The ledger copies no authority. Each entry is digest-bound to the service-owned
state file. Missing/stale services remain explicit and never become implicit PASS.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso,sha256_file
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso,sha256_file

def _parse(value:str)->datetime:
 return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)

def build(config:dict[str,Any],state_root:Path,now:datetime|None=None)->dict[str,Any]:
 current=now or datetime.now(timezone.utc); entries=[]; required_problem=False
 for spec in config.get('services') or []:
  if not isinstance(spec,dict): continue
  name=str(spec.get('name') or ''); file=str(spec.get('state_file') or ''); required=bool(spec.get('required')); max_age=int(spec.get('max_age_seconds') or 0)
  path=state_root/file
  if not name or not file or not path.is_file():
   health='missing'; observed=''; age=None; digest=''; service_status='unknown'
  else:
   payload=load_json(path); observed=str(payload.get('observed_at') or ''); service_status=str(payload.get('status') or 'unknown')
   try: age=max(0,int((current-_parse(observed)).total_seconds()))
   except ValueError: age=None
   health='fresh' if age is not None and (max_age<=0 or age<=max_age) else 'stale'; digest=sha256_file(path)
  if required and health!='fresh': required_problem=True
  entries.append({'name':name,'required':required,'state_file':file,'freshness':health,'age_seconds':age,'service_status':service_status,'observed_at':observed,'sha256':digest})
 return {'status':'degraded' if required_problem else 'available','entries':entries}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--state-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result={'schema_version':'1.0','service':'isolated_service_ledger','observed_at':now_iso(),**build(load_json(a.config),a.state_root)};atomic_json(a.output,result);print(result['status']);return 0 if result['status']=='available' else 2
if __name__=='__main__': raise SystemExit(main())
