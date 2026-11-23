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
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate',type=Path);p.add_argument('--production-healthy',action='store_true');a=p.parse_args()
 src=load_json(a.input); items=src.get('items') if isinstance(src.get('items'),list) else []
 if a.candidate:
  candidate=load_json(a.candidate)
  result={"schema_version":"1.1","service":"dependency_admission","observed_at":now_iso(),**admission(candidate,items,production_healthy=a.production_healthy)}
  atomic_json(a.output,result);print(result['state']);return 0 if result['state']=='admitted' else 2
 result={"schema_version":"1.0","service":"dependency_conflict","observed_at":now_iso(),**analyze(items)};atomic_json(a.output,result);print(result['status']);return 0

# Admission decisions are independent of production releases.  Existing
# analyze() remains an advisory compatibility interface for shadow consumers.
DOMAINS = ('files', 'components', 'contracts', 'providers', 'schemas',
           'deployment_paths', 'authorization_paths', 'tenant_scopes')
ACTIVE_STATES = frozenset(('active', 'ready_for_integration'))
FINAL_STATES = frozenset(('production_verified', 'cancelled'))


def _tokens(item: dict[str, Any], key: str) -> set[str]:
    values = item.get(key)
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f'{key} must be a list of nonempty strings')
    return {v.strip().casefold() for v in values}


def admission(candidate: dict[str, Any], existing: list[dict[str, Any]],
              *, production_healthy: bool = False) -> dict[str, Any]:
    """Fail-closed, deterministic non-mutating development admission decision.

    Production-health gating applies to new features, not authorized repair.
    Owner approval and production release authorization remain separate.
    """
    cid = candidate.get('id')
    if not isinstance(cid, str) or not cid.strip():
        return {'state': 'blocked', 'reasons': ['missing_workstream_id']}
    if candidate.get('kind') not in ('repair', 'infrastructure', 'feature'):
        return {'state': 'blocked', 'reasons': ['unknown_workstream_kind']}
    if candidate['kind'] == 'feature' and not production_healthy:
        return {'state': 'blocked', 'reasons': ['production_health_unverified']}
    try:
        for key in DOMAINS:
            _tokens(candidate, key)
        deps = _tokens(candidate, 'depends_on')
        if not any(_tokens(candidate, key) for key in DOMAINS):
            return {'state': 'blocked', 'reasons': ['no_declared_scope']}
        if cid.casefold() in deps:
            return {'state': 'blocked', 'reasons': ['self_dependency']}
        conflicts = []
        by_id = {}
        for work in existing:
            wid = work.get('id')
            if not isinstance(wid, str) or not wid.strip() or wid in by_id or wid == cid:
                return {'state': 'blocked', 'reasons': ['invalid_existing_inventory']}
            by_id[wid] = work
            if work.get('state') not in ACTIVE_STATES | FINAL_STATES | frozenset(('queued', 'blocked_by_dependency')):
                return {'state': 'blocked', 'reasons': ['unknown_existing_state']}
            for key in DOMAINS:
                _tokens(work, key)
            _tokens(work, 'depends_on')
        for dep in sorted(deps):
            matching = [v for k, v in by_id.items() if k.casefold() == dep]
            if len(matching) != 1 or matching[0]['state'] != 'production_verified':
                conflicts.append({'with': dep, 'reasons': ['dependency_not_verified']})
        for work in existing:
            if work['state'] not in ACTIVE_STATES:
                continue
            reasons = []
            for key in DOMAINS:
                if _tokens(candidate, key) & _tokens(work, key):
                    reasons.append(key)
            if cid.casefold() in _tokens(work, 'depends_on') or work['id'].casefold() in deps:
                reasons.append('dependency')
            if reasons:
                conflicts.append({'with': work['id'], 'reasons': sorted(set(reasons))})
    except (TypeError, ValueError, AttributeError):
        return {'state': 'blocked', 'reasons': ['invalid_scope_metadata']}
    if conflicts:
        return {'state': 'blocked_by_dependency', 'conflicts': conflicts}
    return {'state': 'admitted', 'conflicts': [], 'production_authority': False}

if __name__=='__main__': raise SystemExit(main())
