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


def test_scoped_installed_worker_does_not_read_mutable_checkout_registry(monkeypatch, tmp_path):
    home = tmp_path / 'home'
    installed = home / '.local/lib/jason'
    installed.mkdir(parents=True)
    repo = tmp_path / 'accepted-source'
    (repo / 'config').mkdir(parents=True)
    checkout_registry = repo / 'config/development-concurrency-scopes.json'
    checkout_registry.write_text((ROOT / 'config/development-concurrency-scopes.json').read_text())
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(worker, '__file__', str(installed / 'owner_approved_development_worker.py'))
    path = worker.reviewed_claim_scope_path(repo)
    assert path == installed / 'development-concurrency-scopes.json'
    assert not path.exists()  # no fall back to the existing checkout policy
    state = {'items': {}}
    assert admission.plan_worker_claims(state, [issue(1069)], {}, capacity=1) == []
    path.write_bytes(checkout_registry.read_bytes())
    assert admission.plan_worker_claims({'items': {}}, [issue(1069)], admission.load_claim_scopes(path), capacity=1) == ['DEV-1069']
    # Normal source checkout testing continues to use the checked-out policy.
    monkeypatch.setattr(worker, '__file__', str(ROOT / 'tools/owner_approved_development_worker.py'))
    assert worker.reviewed_claim_scope_path(repo) == checkout_registry


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
        verified_merged_ids={'DEV-1117'}, production_healthy=True) == ['DEV-2294']


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


def test_pr_ready_counts_as_active_reservation_but_never_restarts_source_worker():
    state = {'items': {'DEV-1117': {'phase': 'pr_ready', 'pr_number': 1330},
                       'DEV-2294': {'phase': 'diagnosing'}}}
    selected = admission.plan_worker_claims(state, [issue(1117), issue(2294)],
                                            scopes(), capacity=0)
    assert 'DEV-1117' not in selected
    assert 'DEV-2294' not in selected
    assert state['dependency_admission']['active_editor_holds']['DEV-2294'][0]['with'] == 'DEV-1117'

def test_controller_block_rechecks_and_resumes_without_new_owner_approval():
    state = {'items': {'DEV-1117': {'phase': 'pr_ready'},
                       'DEV-2294': {'phase': 'blocked',
                                    'dependency_prior_phase': 'diagnosing',
                                    'blocker_class': 'blocked_by_dependency',
                                    'dependency_admission_hold': {
                                        'state': 'blocked_by_dependency',
                                        'conflicts': [{'with': 'DEV-1117', 'reasons': ['contracts']}]
                                    },
                                    'reasoning_request_id': 'still-original'}}}
    candidate = issue(2294)
    assert admission.plan_worker_claims(state, [candidate], scopes(), capacity=1, production_healthy=True) == []
    assert state['items']['DEV-2294']['phase'] == 'blocked'
    # Upstream PR merge no longer counts as active source edit. This does not
    # grant authority to deploy an unverified release to production.
    assert admission.plan_worker_claims(state, [candidate], scopes(), capacity=1,
        verified_merged_ids={'DEV-1117'}, production_healthy=True) == ['DEV-2294']
    assert state['items']['DEV-2294']['phase'] == 'diagnosing'
    assert state['items']['DEV-2294']['reasoning_request_id'] == 'still-original'
    assert state['items']['DEV-2294']['dependency_admission_hold'] is None
    assert state['items']['DEV-2294']['reason'].startswith('Re-admitted following verified')


def test_controller_block_waits_for_capacity_and_does_not_readmit_manual_holds():
    blocked = {'phase': 'blocked', 'blocker_class': 'blocked_by_dependency',
               'dependency_prior_phase': 'diagnosing',
               'dependency_admission_hold': {'state': 'blocked_by_dependency'}}
    state = {'items': {'DEV-1069': blocked.copy(), 'DEV-759': {
        **blocked, 'blocker_class': 'external_authority'}}}
    items = [issue(1069), issue(759)]
    assert admission.plan_worker_claims(state, items, scopes(), capacity=0) == []
    assert state['items']['DEV-1069']['phase'] == 'blocked'
    assert state['dependency_admission']['queue']['DEV-1069']['state'] == 'queued'
    assert admission.plan_worker_claims(state, items, scopes(), capacity=1) == ['DEV-1069']
    assert state['items']['DEV-759']['phase'] == 'blocked'


def test_controller_hold_does_not_resume_feature_without_verified_health():
    blocked = {'phase': 'blocked', 'blocker_class': 'blocked_by_dependency',
               'dependency_prior_phase': 'diagnosing',
               'dependency_admission_hold': {'state': 'blocked'}}
    state = {'items': {'DEV-1545': blocked}}
    assert admission.plan_worker_claims(state, [issue(1545)], scopes(), capacity=1,
                                        production_healthy=False) == []
    assert state['items']['DEV-1545']['phase'] == 'blocked'


def test_unclassified_existing_source_editor_cannot_keep_editing_unchecked():
    state = {'items': {'DEV-8888': {'phase': 'implementing'},
                       'DEV-2294': {'phase': 'diagnosing'}}}
    selected = admission.plan_worker_claims(state, [issue(2294)], scopes(),
                                            capacity=0)
    assert selected == []
    assert state['dependency_admission']['unclassified_active'] == ['DEV-8888']
    assert state['dependency_admission']['active_editor_holds']['DEV-2294'][0]['with'] == 'DEV-8888'
    assert state['items']['DEV-2294']['phase'] == 'diagnosing'


def test_cross_process_development_lease_is_exclusive(tmp_path):
    import os
    import select
    import subprocess
    import sys
    import fcntl
    root = Path(__file__).resolve().parents[2]
    code = """
import os,sys,fcntl
sys.path.insert(0,sys.argv[1])
from tools.owner_approved_development_worker import acquire_development_claim_lease
from pathlib import Path
fd=acquire_development_claim_lease(Path(sys.argv[2]))
assert isinstance(fd,int)
print('CHILD_OWNS_LEASE',flush=True)
sys.stdin.readline()
fcntl.flock(fd,fcntl.LOCK_UN)
os.close(fd)
"""
    p = subprocess.Popen([sys.executable, '-c', code, str(root), str(tmp_path)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        readable, _, _ = select.select([p.stdout], [], [], 8)
        assert readable, 'child failed to announce lock acquisition'
        assert p.stdout.readline().strip() == 'CHILD_OWNS_LEASE'
        assert worker.acquire_development_claim_lease(tmp_path) is None
        p.stdin.write('release\n')
        p.stdin.flush()
        assert p.wait(timeout=8) == 0
        new = worker.acquire_development_claim_lease(tmp_path)
        assert isinstance(new,int)
        fcntl.flock(new,fcntl.LOCK_UN)
        os.close(new)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=5)
        p.stdin.close()
        p.stdout.close()
        p.stderr.close()


def test_two_independent_claims_survive_simultaneous_processes_without_shared_source_mutation(tmp_path):
    """Real OS workers contend for one lease and admit independent work safely.

    This verifies *development-state* concurrency only. It does not simulate
    healthy production or grant permission to run provider operations.
    """
    import subprocess
    import sys
    import os
    from tools.isolated_service_common import load_json

    repo = Path(__file__).resolve().parents[2]
    spool = tmp_path / 'spool'
    spool.mkdir()
    immutable_desired = tmp_path / 'production-desired-state.json'
    immutable_desired.write_bytes(b'{"production_policy":"unchanged"}\n')
    approved_source = immutable_desired.read_bytes()
    script = r'''
import fcntl,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from tools import owner_approved_development_worker as worker
from tools import dependency_conflict_service as admission
from tools.isolated_service_common import atomic_json,load_json
spool=Path(sys.argv[2]); work_id=sys.argv[3]; registry=Path(sys.argv[4]); event=Path(sys.argv[5])
fd=None
for attempt in range(250):
    fd=worker.acquire_development_claim_lease(spool)
    if fd is not None:break
    time.sleep(.01)
if fd is None:raise SystemExit('LOCK_TIMEOUT')
try:
    state_path=spool/'development-state.json'
    state=load_json(state_path)
    state.setdefault('items',{})
    eligible=[{'id':work_id,'issue_number':int(work_id[4:]),'approval_source':'isolated-owner-fixture','approved_by':'fixture-owner'}]
    claimed=admission.plan_worker_claims(state,eligible,admission.load_claim_scopes(registry),capacity=2,production_healthy=True)
    atomic_json(state_path,state)
    print(json.dumps({'claimed':claimed,'production_authority':state['dependency_admission']['production_authority']}),flush=True)
    time.sleep(.04)
finally:
    fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
'''
    command = [sys.executable,'-B','-c',script,str(repo),str(spool),'',
               str(repo/'config/development-concurrency-scopes.json'),str(immutable_desired)]
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    processes=[]
    try:
        for name in ('DEV-1069','DEV-1545'):
            cmd=command.copy();cmd[6]=name
            processes.append(subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env))
        outcomes=[]
        for proc in processes:
            out,err=proc.communicate(timeout=15)
            assert proc.returncode==0,err
            outcomes.append(json.loads(out.strip()))
        assert {tuple(v['claimed']) for v in outcomes}=={('DEV-1069',),('DEV-1545',)}
        assert all(v['production_authority'] is False for v in outcomes)
        state=load_json(spool/'development-state.json')
        assert set(state['items'])=={'DEV-1069','DEV-1545'}
        assert all(row['dependency_claim_status']=='active' for row in state['items'].values())
        assert state['dependency_admission']['active_claims']==['DEV-1069','DEV-1545']
        # The third independent process requests a shared Teams approval
        # domain: it is blocked, preserving the earlier durable claims.
        cmd=command.copy();cmd[6]='DEV-759'
        third=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=15)
        assert third.returncode==0,third.stderr
        assert json.loads(third.stdout)['claimed']==[]
        final=load_json(spool/'development-state.json')
        assert set(final['items'])=={'DEV-1069','DEV-1545'}
        assert final['dependency_admission']['queue']['DEV-759']['state']=='blocked_by_dependency'
        assert immutable_desired.read_bytes()==approved_source
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill();proc.communicate(timeout=5)
