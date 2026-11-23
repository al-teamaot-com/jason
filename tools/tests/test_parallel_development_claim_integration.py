"""Owner-queue admission examples grounded in 2026-11-23 live issue/PR readbacks.

All cases are source-only simulations. No production or provider mutation.
"""
import json
from pathlib import Path

from tools import dependency_conflict_service as admission
from tools import owner_approved_development_worker as worker

ROOT = Path(__file__).resolve().parents[2]


def issue(number):
    return {'id': f'DEV-{number}', 'issue_number': number,
            'approval_source': f'https://github.com/al-teamaot-com/jason/issues/{number}',
            'approved_by': 'al-teamaot-com'}


def scopes():
    return admission.load_claim_scopes(ROOT / 'config/development-concurrency-scopes.json')


def test_actual_existing_workstreams_block_overlapping_new_claims():
    state = {'items': {'DEV-1117': {'phase': 'pr_ready', 'pr_number': 1330},
                       'DEV-2294': {'phase': 'diagnosing'}}}
    selected = admission.plan_worker_claims(state, [issue(1470), issue(1545), issue(759), issue(1069)],
        scopes(), capacity=4, production_healthy=True)
    # QBO financial statements share the actively claimed SharePoint domain.
    assert state['dependency_admission']['queue']['DEV-1470']['state'] == 'blocked_by_dependency'
    # The independent Teams approval work can be admitted alongside SharePoint.
    assert 'DEV-1545' in selected
    # Procurement touches the shared Teams approval contract and must wait.
    assert state['dependency_admission']['queue']['DEV-759']['state'] == 'blocked_by_dependency'
    # This development-admission infrastructure has independent source scope.
    assert 'DEV-1069' in selected
    assert state['items']['DEV-1069']['dependency_claim_status'] == 'active'
    assert state['dependency_admission']['production_authority'] is False


def test_stale_merged_work_does_not_strand_independent_claims():
    # Ten of eleven historical PR-ready IDs from the live 2026-11-23 queue
    # were independently observed merged on GitHub; the only open PR is 1330.
    merged = {f'DEV-{n}' for n in (1129, 1176, 2309, 2311, 2314,
                                    2315, 2318, 2320, 2322, 950)}
    state = {'items': {name: {'phase': 'pr_ready'} for name in merged}}
    state['items']['DEV-1117'] = {'phase': 'pr_ready', 'pr_number': 1330}
    state['items']['DEV-2294'] = {'phase': 'diagnosing'}
    selected = admission.plan_worker_claims(state, [issue(1069)], scopes(), capacity=1,
                                             verified_merged_ids=merged)
    assert selected == ['DEV-1069']
    assert state['dependency_admission']['unclassified_active'] == []
    assert len(state['dependency_admission']['verified_merged_pr_work']) == 10


def test_unknown_active_development_blocks_new_claim_without_false_idle():
    state = {'items': {'DEV-8888': {'phase': 'implementing'}}}
    assert admission.plan_worker_claims(state, [issue(1069)], scopes(), capacity=1) == []
    hold = state['dependency_admission']['queue']['DEV-1069']
    assert hold['state'] == 'blocked_by_dependency'
    assert hold['conflicts'][0]['with'] == 'DEV-8888'
    assert state['dependency_admission']['unclassified_active'] == ['DEV-8888']


def test_production_health_not_inferred_from_existing_sources():
    state = {'items': {}}
    assert admission.plan_worker_claims(state, [issue(1545), issue(1069)], scopes(),
                                        capacity=2, production_healthy=False) == ['DEV-1069']
    assert state['dependency_admission']['queue']['DEV-1545']['reasons'] == ['production_health_unverified']


def test_verified_merge_receipt_requires_exact_pr_and_sha(monkeypatch, tmp_path):
    record = {'phase': 'pr_ready', 'pr_number': 123}
    state = {'items': {'DEV-42': record}}
    observed = []
    def readback(repo, number):
        observed.append(number)
        return {'mergedAt': '2026-11-23T15:00:00Z', 'mergeCommit': {'oid': 'a' * 40}}
    monkeypatch.setattr(worker.support, 'pr_view', readback)
    assert worker.verified_merged_claim_work(state, tmp_path, []) == {'DEV-42'}
    assert record['dependency_verified_merge']['merge_sha'] == 'a' * 40
    assert worker.verified_merged_claim_work(state, tmp_path, []) == {'DEV-42'}
    assert observed == [123]
    record['pr_number'] = 124
    assert worker.verified_merged_claim_work(state, tmp_path, []) == {'DEV-42'}
    assert observed == [123, 124]


def test_existing_worker_lease_does_not_admit_second_claim_owner(tmp_path):
    import os
    import fcntl
    first = worker.acquire_development_claim_lease(tmp_path)
    assert isinstance(first, int)
    try:
        assert worker.acquire_development_claim_lease(tmp_path) is None
    finally:
        fcntl.flock(first, fcntl.LOCK_UN)
        os.close(first)
    second = worker.acquire_development_claim_lease(tmp_path)
    assert isinstance(second, int)
    os.close(second)


def test_worker_persists_claim_before_opening_worktree(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    repo, spool = tmp_path / 'repo', tmp_path / 'spool'
    (repo / 'config').mkdir(parents=True)
    (repo / 'config' / 'development-concurrency-scopes.json').write_text(
        (ROOT / 'config/development-concurrency-scopes.json').read_text())
    monkeypatch.setattr(sys, 'argv', ['worker.py', '--repo', str(repo), '--spool', str(spool)])
    monkeypatch.setattr(worker.support, 'run', lambda *args, **kw: '')
    monkeypatch.setattr(worker, 'owner_approved_issues', lambda *args, **kw: [issue(1069)])
    monkeypatch.setattr(worker, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(worker.support, 'open_prs', lambda _: [])
    monkeypatch.setattr(worker.support, 'load_gate', lambda _: SimpleNamespace(load_json=lambda _: {}))
    monkeypatch.setattr(worker, 'known_development_pr_is_merged', lambda *args: False)
    monkeypatch.setattr(worker, 'development_pr_for', lambda *args: None)
    monkeypatch.setattr(worker, 'sync_lifecycle_notification', lambda *args, **kwargs: None)
    for name in ('reconcile_issue_dependency_holds', 'reconcile_removed_approval',
                 'readmit_verified_ccc_owner_review', 'recycle_self_recoverable_blockers',
                 'queue_exhausted_recovery_diagnostics', 'reconcile_exhausted_recovery_diagnostics',
                 'reconcile_recovery_handoff_intake', 'raise_exhausted_repair_support_issues',
                 'readmit_verified_development_recoveries',
                 'readmit_source_context_after_verified_worker_upgrade',
                 'readmit_explicit_verified_dependencies',
                 'readmit_recovered_development_reasoning',
                 'readmit_development_after_verified_transport_recovery',
                 'readmit_development_after_verified_credit_replenishment',
                 'readmit_stale_clean_development_source',
                 'readmit_verified_cached_stale_response_replay',
                 'readmit_verified_exhausted_evidence_synthesis'):
        monkeypatch.setattr(worker, name, lambda *args, **kwargs: None)
    seen = []
    def inspect_worktree(*args):
        recorded = json.loads((spool / 'development-state.json').read_text())
        assert recorded['items']['DEV-1069']['dependency_claim_status'] == 'active'
        seen.append(True)
        raise RuntimeError('stop after durable claim observation')
    monkeypatch.setattr(worker, 'ensure_worktree', inspect_worktree)
    assert worker.main() == 0
    assert seen
    assert json.loads((spool / 'development-state.json').read_text())['items']['DEV-1069']['phase'] == 'blocked'


def test_recovered_blocked_claim_is_rechecked_before_source_execution():
    state = {'items': {'DEV-1545': {'phase': 'implementing'},
                       'DEV-759': {'phase': 'diagnosing'}}}
    selected = admission.plan_worker_claims(state, [issue(759)], scopes(),
        capacity=0, production_healthy=True, resumed_from_blocked={'DEV-759'})
    assert selected == []
    assert state['items']['DEV-759']['phase'] == 'blocked'
    assert state['items']['DEV-759']['dependency_admission_hold']['state'] == 'blocked_by_dependency'


def test_recovered_blocked_unrelated_claim_resumes_when_healthy():
    state = {'items': {'DEV-2294': {'phase': 'diagnosing'},
                       'DEV-1545': {'phase': 'diagnosing'}}}
    assert admission.plan_worker_claims(state, [issue(1545)], scopes(), capacity=0,
        production_healthy=True, resumed_from_blocked={'DEV-1545'}) == ['DEV-1545']
    assert state['items']['DEV-1545']['dependency_claim_status'] == 'active'


def test_legacy_sharepoint_editor_waits_for_open_pr_without_losing_its_place():
    state = {'items': {'DEV-1117': {'phase': 'pr_ready'},
                       'DEV-2294': {'phase': 'diagnosing', 'reasoning_request_id': 'kept'}}}
    selected = admission.plan_worker_claims(state, [issue(2294)], scopes(), capacity=0,
                                             production_healthy=False)
    assert selected == []
    assert state['dependency_admission']['active_editor_holds']['DEV-2294'][0]['with'] == 'DEV-1117'
    assert state['items']['DEV-2294']['reasoning_request_id'] == 'kept'
    assert state['items']['DEV-2294']['phase'] == 'diagnosing'
    # Exact verified upstream merge makes it eligible on the next pass.
    assert admission.plan_worker_claims(state, [issue(2294)], scopes(), capacity=0,
        verified_merged_ids={'DEV-1117'}) == ['DEV-2294']


def test_live_pr_files_enrich_semantic_scope_and_missing_readback_blocks(monkeypatch,tmp_path):
    state = {'items': {'DEV-1117': {'phase':'pr_ready','pr_number':1330}}}
    inventory = scopes()
    monkeypatch.setattr(worker.support,'pr_view',lambda *_: {
        'files':[{'path':'implementation/mcp_service/src/jason_mcp/server.py'}]})
    assert worker.verified_merged_claim_work(state,tmp_path,[{'number':1330}],inventory)==set()
    assert 'implementation/mcp_service/src/jason_mcp/server.py' in inventory['DEV-1117']['files']
    monkeypatch.setattr(worker.support,'pr_view',lambda *_: {'files':[]})
    inventory = scopes()
    assert worker.verified_merged_claim_work(state,tmp_path,[{'number':1330}],inventory)==set()
    assert 'DEV-1117' not in inventory
