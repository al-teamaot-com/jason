#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso

def overlaps(a:dict[str,Any],b:dict[str,Any])->list[str]:
 keys=("files","components","contracts","providers","schemas","deployment_paths")
 out=[]
 for k in keys:
  av=set(a.get(k) or []); bv=set(b.get(k) or [])
  if av & bv: out.append(k)
 if a.get("id") in set(b.get("depends_on") or []) or b.get("id") in set(a.get("depends_on") or []): out.append("dependency")
 return out

def analyze(items:list[dict[str,Any]])->dict[str,Any]:
 conflicts=[]
 for i,a in enumerate(items):
  for b in items[i+1:]:
   why=overlaps(a,b)
   if why: conflicts.append({"a":a.get("id"),"b":b.get("id"),"reasons":why})
 return {"status":"conflict" if conflicts else "clear","conflicts":conflicts}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 src=load_json(a.input); items=src.get('items') if isinstance(src.get('items'),list) else []
 result={"schema_version":"1.0","service":"dependency_conflict","observed_at":now_iso(),**analyze(items)};atomic_json(a.output,result);print(result['status']);return 0
if __name__=='__main__': raise SystemExit(main())
