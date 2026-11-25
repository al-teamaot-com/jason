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
 keys=("files","components","contracts","providers","schemas","deployment_paths","authorization_paths","tenant_scopes")
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



# A claim is an engineering reservation, not authorization to change production.
WORKER_ACTIVE_PHASES = frozenset(('identified', 'diagnosing', 'implementing',
    'ci_repair_needed', 'ci_repairing', 'pr_validating', 'pr_monitoring', 'pr_ready'))


def load_claim_scopes(path: Path) -> dict[str, dict[str, Any]]:
    source = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(source, dict) or source.get('schema_version') != '1.0'
            or not isinstance(source.get('workstreams'), dict)):
        raise ValueError('invalid development concurrency scope registry')
    scopes = {}
    for work_id, value in source['workstreams'].items():
        if not isinstance(work_id, str) or not work_id.startswith('DEV-') or not isinstance(value, dict):
            raise ValueError('invalid development scope identifier')
        if value.get('kind') not in ('repair', 'infrastructure', 'feature'):
            raise ValueError('invalid development workstream kind')
        if any(key not in value for key in (*DOMAINS, 'depends_on')):
            raise ValueError('incomplete development scope')
        for key in (*DOMAINS, 'depends_on'):
            _tokens(value, key)
        if not any(value[key] for key in DOMAINS):
            raise ValueError('empty development scope')
        scopes[work_id] = {**value, 'id': work_id}
    return scopes


def plan_worker_claims(state: dict[str, Any], eligible: list[dict[str, Any]],
                       scopes: dict[str, dict[str, Any]], *,
                       capacity: int, production_healthy: bool = False,
                       verified_merged_ids: set[str] | None = None,
                       resumed_from_blocked: set[str] | None = None) -> list[str]:
    """Plan and reserve new development claims in the existing worker state.

    Call under the worker's exclusive lease, and persist the state atomically
    before invoking a new task. Legacy active work is reconciled, never seized.
    Missing legacy scope and stale PR status refuse only *new* claims.
    """
    verified_merged_ids = verified_merged_ids or set()
    resumed_from_blocked = resumed_from_blocked or set()
    records = state.get('items')
    if not isinstance(records, dict):
        raise ValueError('missing authoritative development-state items')
    selected = []
    active = []
    unknown = []
    eligible_ids = {item['id'] for item in eligible}
    for work_id, record in records.items():
        if not isinstance(record, dict):
            raise ValueError('malformed existing development record')
        if (record.get('phase') not in WORKER_ACTIVE_PHASES
                or work_id in verified_merged_ids
                or work_id in resumed_from_blocked):
            continue
        # Keep PR-ready records as dependency reservations, but never send
        # them through the source-edit worker a second time. Existing
        # pr_validating/monitoring records still need read-only reconciliation.
        if work_id in eligible_ids and record['phase'] != 'pr_ready':
            selected.append(work_id)
        scope = scopes.get(work_id)
        if scope is None:
            unknown.append(work_id)
            continue
        active.append({**scope, 'state': 'ready_for_integration' if record['phase'] in
                       ('pr_ready', 'pr_validating', 'pr_monitoring') else 'active'})
    existing_conflicts = analyze(active)['conflicts']
    holds = {}
    limit = max(0, int(capacity))
    # A source/reasoning repair may independently reopen a formerly blocked
    # record in the same worker pass. Re-admission is NOT a free claim: it must
    # pass the same dependency gate before any resumed source edit.
    for item in eligible:
        work_id = item['id']
        if work_id not in resumed_from_blocked:
            continue
        record = records.get(work_id)
        if not isinstance(record, dict) or record.get('phase') not in WORKER_ACTIVE_PHASES:
            continue
        scope = scopes.get(work_id)
        if scope is None:
            decision = {'state': 'blocked', 'reasons': ['scope_declaration_missing']}
        elif unknown:
            decision = {'state': 'blocked_by_dependency',
                        'conflicts': [{'with': prior, 'reasons': ['unclassified_active_workstream']}
                                      for prior in sorted(unknown)]}
        else:
            decision = admission(scope, active, production_healthy=production_healthy)
        if decision['state'] != 'admitted':
            record.update({'phase': 'blocked', 'blocker_class': 'blocked_by_dependency',
                           'dependency_prior_phase': record['phase'],
                           'dependency_admission_hold': decision,
                           'reason': 'Re-admission held by current development dependency gate.',
                           'recovery_next_action': 'Recheck exact dependency and health evidence.',
                           'updated_at': now_iso()})
            holds[work_id] = decision
            continue
        record.update({'dependency_claim_status': 'active',
                       'dependency_scope': scope, 'dependency_admission_hold': None,
                       'updated_at': now_iso()})
        active.append({**scope, 'state': 'active'})
        selected.append(work_id)
    # Dependency holds caused by this controller are rechecked automatically
    # on every later approved worker pass. Manual/credential holds stay closed.
    # A source PR merge is never proof of Production Verified acceptance.
    for item in eligible:
        work_id = item['id']
        record = records.get(work_id)
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        prior = record.get('dependency_prior_phase')
        held = record.get('dependency_admission_hold')
        if (record.get('blocker_class') != 'blocked_by_dependency'
                or prior not in WORKER_ACTIVE_PHASES
                or not isinstance(held, dict)
                or held.get('state') not in ('blocked', 'blocked_by_dependency')):
            continue
        scope = scopes.get(work_id)
        if scope is None:
            decision = {'state': 'blocked', 'reasons': ['scope_declaration_missing']}
        elif unknown:
            decision = {'state': 'blocked_by_dependency',
                        'conflicts': [{'with': other,
                                       'reasons': ['unclassified_active_workstream']}
                                      for other in sorted(unknown)]}
        else:
            decision = admission(scope, active, production_healthy=production_healthy)
        if decision['state'] == 'admitted' and limit > 0:
            record.update({'phase': prior, 'dependency_claim_status': 'active',
                           'dependency_scope': scope, 'dependency_admission_hold': None,
                           'dependency_prior_phase': None, 'blocker_class': None,
                           'recovery_next_action': None,
                           'reason': 'Re-admitted following verified current dependency and capacity recheck.',
                           'updated_at': now_iso()})
            active.append({**scope, 'state': 'active'})
            selected.append(work_id)
            limit -= 1
            continue
        if decision['state'] == 'admitted':
            holds[work_id] = {'state': 'queued',
                              'reasons': ['engineering_capacity_unavailable']}
        else:
            record['dependency_admission_hold'] = decision
            holds[work_id] = decision
    for item in eligible:
        work_id = item['id']
        if work_id in records:
            continue  # Do not silently re-admit a blocked or completed record.
        if limit == 0:
            holds[work_id] = {'state': 'queued', 'reasons': ['engineering_capacity_unavailable']}
            continue
        scope = scopes.get(work_id)
        if scope is None:
            holds[work_id] = {'state': 'blocked', 'reasons': ['scope_declaration_missing']}
            continue
        if unknown:
            holds[work_id] = {'state': 'blocked_by_dependency',
                              'conflicts': [{'with': old, 'reasons': ['unclassified_active_workstream']}
                                            for old in sorted(unknown)]}
            continue
        decision = admission(scope, active, production_healthy=production_healthy)
        if decision['state'] != 'admitted':
            holds[work_id] = decision
            continue
        # Record a *durable* claim before the worker opens a worktree or queues AI.
        records[work_id] = {
            'phase': 'identified', 'attempts': 0, 'claimed_at': now_iso(),
            'approval_source': item['approval_source'],
            'approved_by': item['approved_by'],
            'issue_number': item['issue_number'],
            'worker': 'jason-owner-approved-development-worker',
            'dependency_scope': scope,
            'dependency_claim_status': 'active',
            'updated_at': now_iso(),
        }
        active.append({**scope, 'state': 'active'})
        selected.append(work_id)
        limit -= 1
    # Historical active work may predate the controller. Do not silently let
    # two existing editors evolve a shared dependency. Permit PR observation
    # but hold source edits until the upstream PR is verified merged, or the
    # earlier editor reaches a stable checkpoint.
    editor_phases = {'identified', 'diagnosing', 'implementing',
                     'ci_repair_needed', 'ci_repairing'}
    editor_holds = {}
    for conflict in existing_conflicts:
        left, right = conflict['a'], conflict['b']
        left_rec, right_rec = records.get(left, {}), records.get(right, {})
        left_edit = left_rec.get('phase') in editor_phases
        right_edit = right_rec.get('phase') in editor_phases
        if not (left_edit or right_edit):
            continue
        if left_edit and not right_edit:
            hold = left
        elif right_edit and not left_edit:
            hold = right
        else:
            # Stable deterministic fallback for precontroller legacy claims;
            # later claims are always denied before reaching this point.
            hold = max(left, right)
        other = right if hold == left else left
        editor_holds.setdefault(hold, []).append({'with': other, 'reasons': conflict['reasons']})
    if unknown:
        # A legacy editor without reviewed semantic scope could conflict with
        # any active editor. Continue read-only PR observations only; never
        # infer that the unmatched workstream is safe from an empty file list.
        for work_id in selected:
            if records[work_id].get('phase') not in editor_phases:
                continue
            competing = [wid for wid in sorted(unknown) if wid != work_id]
            if not competing:
                competing = [work_id]
            editor_holds.setdefault(work_id, []).extend(
                {'with': other,
                 'reasons': ['unclassified_active_workstream'
                             if other != work_id else 'scope_declaration_missing']}
                for other in competing
            )
    selected = [work_id for work_id in selected if work_id not in editor_holds]
    state['dependency_admission'] = {
        'schema_version': '1.0', 'observed_at': now_iso(),
        'active_editor_holds': editor_holds,
        'active_claims': sorted(i['id'] for i in active),
        'existing_conflicts': existing_conflicts,
        'unclassified_active': sorted(unknown),
        'verified_merged_pr_work': sorted(verified_merged_ids),
        'queue': holds,
        'production_health_verified_for_new_features': bool(production_healthy),
        'production_authority': False,
    }
    return selected


if __name__=='__main__': raise SystemExit(main())
