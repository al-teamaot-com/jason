from tools import documentation_source_reconciler as docs
from tools import todo_release_bridge as bridge


def test_superseded_snapshot_selection_keeps_newest():
    items = [
        {'number': 12, 'headRefName': 'automation/documentation-reconcile-aa'},
        {'number': 13, 'headRefName': 'feature/not-generated'},
        {'number': 15, 'headRefName': 'automation/documentation-reconcile-bb'},
    ]
    assert docs.superseded_generated_prs(items) == ['12']
    assert docs.superseded_generated_prs(items[:1]) == []


def test_prune_rejects_non_generated_path(monkeypatch):
    calls=[]
    monkeypatch.setattr(docs, 'gh_json', lambda *a: {'files':[{'path':'tools/unsafe.py'}]})
    monkeypatch.setattr(docs, 'run', lambda *a: calls.append(a))
    assert not docs.prune_superseded_generated_prs([
        {'number': 12, 'headRefName': 'automation/documentation-reconcile-aa'},
        {'number': 15, 'headRefName': 'automation/documentation-reconcile-bb'}])
    assert calls == []


def test_prune_one_verified_generated_snapshot(monkeypatch):
    calls=[]
    monkeypatch.setattr(docs,'gh_json',lambda *a:{'files':[{'path':'docs/control/AUTOMATED-CHANGE-STATE.json'}]})
    monkeypatch.setattr(docs,'run',lambda *a:calls.append(a))
    assert docs.prune_superseded_generated_prs([
        {'number': 12, 'headRefName': 'automation/documentation-reconcile-aa'},
        {'number': 15, 'headRefName': 'automation/documentation-reconcile-bb'}])
    assert len(calls)==1 and calls[0][2]=='close' and calls[0][3]=='12'


def test_issue_fingerprint_changes_with_authoritative_body(monkeypatch):
    def fake_gh(args, *, cwd):
        return [{'number':953,'title':'TODO','body':'- TODO item: TODO-OPS-003\nbody v1','url':'u'}]
    monkeypatch.setattr(bridge,'gh_json',fake_gh)
    from pathlib import Path
    v1=bridge.todo_issues(Path('.'))[0]['source_fingerprint']
    monkeypatch.setattr(bridge,'gh_json',lambda args,*,cwd:[{'number':953,'title':'TODO','body':'- TODO item: TODO-OPS-003\nbody v2','url':'u'}])
    v2=bridge.todo_issues(Path('.'))[0]['source_fingerprint']
    assert v1!=v2
