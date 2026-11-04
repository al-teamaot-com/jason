#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso

def evaluate(checks:list[dict[str,Any]])->dict[str,Any]:
 failed=[]; unknown=[]
 for c in checks:
  name=str(c.get('name') or 'unnamed'); status=str(c.get('status') or 'unknown').lower()
  if status not in {'pass','passed','ok','healthy','succeeded'}:
   (unknown if status in {'','unknown','pending'} else failed).append(name)
 status='checks_reported_passing' if checks and not failed and not unknown else ('failed' if failed else 'pending')
 return {"status":status,"failed":failed,"unknown":unknown,"check_count":len(checks)}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();src=load_json(a.input)
 checks=src.get('checks') if isinstance(src.get('checks'),list) else []
 result={"schema_version":"1.0","service":"operational_acceptance","observed_at":now_iso(),**evaluate(checks)};atomic_json(a.output,result);print(result['status']);return 0 if result['status']=='accepted' else 2
if __name__=='__main__': raise SystemExit(main())
