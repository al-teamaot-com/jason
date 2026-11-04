#!/usr/bin/env python3
"""Classify advisory isolated-service health without controlling PMV3.

Unknown/missing/stale/pending/failed evidence must never be reported healthy.
Only explicitly required records are allowed to create a supervisor-level block.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso

GOOD_STATUSES=frozenset({
 'healthy','current','available','ready','reusable','accepted',
 'evidence_present','aligned','reported_passing','complete',
 'work_available','waiting','clear',
})

def classify(ledger:dict[str,Any])->dict[str,Any]:
 problems=[];warnings=[]
 entries=ledger.get('entries')
 if not isinstance(entries,list):
  return {'status':'blocked','problems':[{'service':'ledger','reason':'invalid_entries'}],'warnings':[]}
 for e in entries:
  if not isinstance(e,dict):
   problems.append({'service':'ledger','reason':'invalid_entry'})
   continue
  name=str(e.get('name') or 'unknown')
  freshness=str(e.get('freshness') or 'missing')
  status=str(e.get('service_status') or 'unknown')
  required=e.get('required') is True
  reasons=[]
  if freshness!='fresh': reasons.append('freshness_'+freshness)
  if status not in GOOD_STATUSES: reasons.append('status_'+status)
  for reason in reasons:
   entry={'service':name,'reason':reason}
   if required: problems.append(entry)
   else: warnings.append(entry)
 return {'status':'blocked' if problems else ('degraded' if warnings else 'healthy'),
         'problems':problems,'warnings':warnings,
         'service_count':len(entries),'advisory_only':True}

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--ledger',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 ledger=load_json(a.ledger)
 result={'schema_version':'1.0','service':'isolated_service_supervisor','observed_at':now_iso(),**classify(ledger)}
 atomic_json(a.output,result);print(result['status']);return 0 if result['status']!='blocked' else 2
if __name__=='__main__': raise SystemExit(main())
