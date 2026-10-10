import json
import owner_approved_development_worker as worker


def test_verified_dependency_readmits_once(tmp_path, monkeypatch):
    issue = 'release-1234567890abcdef'
    spool = tmp_path / 'spool'
    spool.mkdir()
    (spool / 'todo-release-state.json').write_text(json.dumps({'items': {'TODO-OPS-003': {
        'issue_number': 953, 'phase': 'development_blocked',
        'retry_eligible': True, 'dependency_recheck': 'verified_for_governed_readmission_check',
        'governing_dependencies': [issue]}}}))
    monkeypatch.setattr(worker, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(worker.todo_bridge, 'dependency_state_for_item', lambda *_: {'retry_eligible': True})
    item = {'id': 'DEV-953', 'issue_number': 953, 'body': f'- Governing release dependencies: {issue}'}
    state = {'items': {'DEV-953': {'phase': 'blocked', 'blocker_class': 'blocked_by_dependency'}}}
    assert worker.readmit_explicit_verified_dependencies(state, [item], spool, max_active=2) == 1
    assert state['items']['DEV-953']['phase'] == 'diagnosing'
    state['items']['DEV-953']['phase'] = 'blocked'
    assert worker.readmit_explicit_verified_dependencies(state, [item], spool, max_active=2) == 0


def test_issue_hold_capacity_and_stale_evidence_fail_closed(tmp_path, monkeypatch):
    release = 'release-1234567890abcdef'
    spool = tmp_path / 'spool'
    spool.mkdir()
    (spool / 'todo-release-state.json').write_text(json.dumps({'items': {'TODO-OPS-003': {
        'issue_number': 953, 'phase': 'development_blocked', 'retry_eligible': True,
        'dependency_recheck': 'verified_for_governed_readmission_check',
        'governing_dependencies': [release]}}}))
    monkeypatch.setattr(worker, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(worker.todo_bridge, 'dependency_state_for_item', lambda *_: {'retry_eligible': False})
    item = {'id': 'DEV-953', 'issue_number': 953, 'body': f'- Governing release dependencies: {release}'}
    state = {'items': {'DEV-953': {'phase': 'blocked', 'blocker_class': 'blocked_by_dependency'}}}
    assert worker.readmit_explicit_verified_dependencies(state, [item], spool, max_active=2) == 0
    monkeypatch.setattr(worker.todo_bridge, 'dependency_state_for_item', lambda *_: {'retry_eligible': True})
    assert worker.readmit_explicit_verified_dependencies(state, [item], spool, max_active=0) == 0
    held = dict(item, body=item['body'] + '\n## Production-health gate hold\nBlocked by dependency')
    assert worker.readmit_explicit_verified_dependencies(state, [held], spool, max_active=2) == 0


def test_unrelated_authorization_blocker_cannot_readmit(tmp_path, monkeypatch):
    release = 'release-1234567890abcdef'
    spool = tmp_path / 'spool'
    spool.mkdir()
    (spool / 'todo-release-state.json').write_text(json.dumps({'items': {'TODO-OPS-003': {
        'issue_number': 953, 'phase': 'development_blocked', 'retry_eligible': True,
        'dependency_recheck': 'verified_for_governed_readmission_check',
        'governing_dependencies': [release]}}}))
    monkeypatch.setattr(worker, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(worker.todo_bridge, 'dependency_state_for_item', lambda *_: {'retry_eligible': True})
    item = {'id': 'DEV-953', 'issue_number': 953, 'body': f'- Governing release dependencies: {release}'}
    state = {'items': {'DEV-953': {'phase': 'blocked', 'reason': 'Missing provider credentials'}}}
    assert worker.readmit_explicit_verified_dependencies(state, [item], spool, max_active=2) == 0
