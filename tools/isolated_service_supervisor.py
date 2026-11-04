#!/usr/bin/env python3
"""Classify isolated-service health without controlling PMV3."""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso

BAD_STATUSES={'failed','unhealthy','not_ready','conflict','attention'}

def classify(ledger:dict[str,Any])->dict[str,Any]:
 problems=[]; warnings=[]
 for e in ledger.get('entries') or []:
  if not isinstance(e,dict): continue
  name=str(e.get('name') or 'unknown'); freshness=str(e.get('freshness') or 'missing'); status=str(e.get('service_status') or 'unknown')
  if bool(e.get('required')) and freshness!='fresh': problems.append({'service':name,'reason':freshness})
  elif freshness!='fresh': warnings.append({'service':name,'reason':freshness})
  if status in BAD_STATUSES: warnings.append({'service':name,'reason':status})
 return {'status':'blocked' if problems else ('degraded' if warnings else 'healthy'),'problems':problems,'warnings':warnings}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--ledger',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();ledger=load_json(a.ledger)
 result={'schema_version':'1.0','service':'isolated_service_supervisor','observed_at':now_iso(),**classify(ledger)};atomic_json(a.output,result);print(result['status']);return 0 if result['status']!='blocked' else 2
if __name__=='__main__': raise SystemExit(main())
