from pathlib import Path
import copy
import pytest
from test_owner_approved_development_worker import module as worker


def item(number=1440,body='- Development pull request: #1518'):
    return dict(id=f'DEV-{number}',issue_number=number,body=body,
        approval_source=f'https://github.com/org/repo/issues/{number}',approved_by='owner')


def payload(**changes):
    pr={'number':1518,'state':'open','draft':True,'merged_at':None,
        'head':{'sha':'a'*40,'ref':'feature/approved','repo':{'full_name':'org/repo'}},
        'base':{'ref':'main','repo':{'full_name':'org/repo'}}}
    pr.update(changes);return pr


def mocks(monkeypatch,pr):
    monkeypatch.setattr(worker,'repository_name',lambda repo:'org/repo')
    monkeypatch.setattr(worker.support,'gh_json',lambda args,**kw:pr)
    monkeypatch.setattr(worker.support,'pr_view',lambda *a:{'sha':'a'*40})
    monkeypatch.setattr(worker.support,'check_state',lambda fresh:('passed',[]))


def test_focus_allows_only_explicit_new_work_and_finishes_active_work():
    state={'items':{'DEV-8':{'phase':'implementing'},'DEV-9':{'phase':'blocked'}}}
    policy={'schema_version':'1.0','enabled':True,'issue_numbers':[1440,1493,1458]}
    assert [i['issue_number'] for i in worker.apply_owner_development_focus(state,[item(7),item(8),item(9),item(1440)],policy)]==[8,1440]


def test_adoption_retains_failed_request_and_retry_evidence(monkeypatch,tmp_path):
    mocks(monkeypatch,payload())
    original={'phase':'blocked','reason':'HTTP transport failed','reasoning_request_id':'b'*64,
              'attempts':2,'self_recovery_attempts':2}
    state={'items':{'DEV-1440':copy.deepcopy(original)}}
    assert worker.reconcile_owner_selected_pull_requests(tmp_path,state,[item()])==['DEV-1440']
    record=state['items']['DEV-1440']
    assert record['phase']=='pr_monitoring' and record['pr_number']==1518
    assert record['prior_stage_evidence']==original
    assert record['attempts']==2 and record['reasoning_request_id']=='b'*64


def test_unselected_pr_cannot_become_authority(monkeypatch,tmp_path):
    monkeypatch.setattr(worker.support,'gh_json',lambda *a,**kw:pytest.fail('must not query unselected PR'))
    state={'items':{}}
    assert worker.reconcile_owner_selected_pull_requests(tmp_path,state,[item(body='No PR selected')])==[]
    assert not state['items']


def test_cross_repository_pr_is_rejected(monkeypatch,tmp_path):
    pr=payload();pr['head']['repo']['full_name']='attacker/fork';mocks(monkeypatch,pr)
    with pytest.raises(worker.support.WorkerError,match='repository'):
        worker.reconcile_owner_selected_pull_requests(tmp_path,{'items':{}},[item()])


def test_green_source_moves_to_integration_not_false_production_completion(monkeypatch,tmp_path):
    mocks(monkeypatch,payload(draft=False))
    state={'items':{}}
    worker.reconcile_owner_selected_pull_requests(tmp_path,state,[item()])
    record=state['items']['DEV-1440']
    assert record['phase']=='pr_ready' and record['next_action']=='governed_integration'
    assert 'production' not in record['checks']


def test_live_implementation_is_not_seized(monkeypatch,tmp_path):
    mocks(monkeypatch,payload())
    record={'phase':'implementing','branch':'current-editor'}
    state={'items':{'DEV-1440':dict(record)}}
    assert worker.reconcile_owner_selected_pull_requests(tmp_path,state,[item()])==[]
    assert state['items']['DEV-1440']==record


def test_ambiguous_owner_selection_fails_closed(monkeypatch,tmp_path):
    mocks(monkeypatch,payload())
    with pytest.raises(worker.support.WorkerError,match='ambiguous'):
        worker.reconcile_owner_selected_pull_requests(tmp_path,{'items':{}},[item(body='- Development pull request: #1518\n- Development pull request: #1514')])


def test_canonical_owner_focus_admits_p0_recovery_without_opening_backlog():
    import json
    repo = Path(__file__).resolve().parents[2]
    policy = json.loads((repo / 'config' / 'owner-approved-development-focus.json').read_text())
    assert policy['schema_version'] == '1.0' and policy['enabled'] is True
    assert {1440, 1458, 1493, 1196}.issubset(set(policy['issue_numbers']))
    assert len(policy['issue_numbers']) == len(set(policy['issue_numbers']))
    assert 1500 not in policy['issue_numbers']
    selected = worker.apply_owner_development_focus(
        {'items': {'DEV-1196': {'phase': 'blocked'}, 'DEV-1500': {'phase': 'blocked'}}},
        [item(1196, body='owner-approved repair'), item(1500, body='unrelated P1')], policy,
    )
    assert [entry['issue_number'] for entry in selected] == [1196]
