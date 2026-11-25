from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import pmv3_integration_queue as queue


class FakeApi:
    def __init__(self, *, main_sha: str, prs: list[dict], required=None):
        self._main = main_sha
        self.prs = {int(p['number']): dict(p) for p in prs}
        self.required = list(required or ['cap-001', 'runtime-service'])
        self.states = {str(p['headRefOid']): {name: 'success' for name in self.required} for p in prs}
        self.files = {int(p['number']): set(p.get('files') or {f"f-{p['number']}.txt"}) for p in prs}
        self.gates = []
        self.merges = []
        self.updates = []

    def main_sha(self):
        return self._main

    def open_pull_requests(self):
        return [dict(p) for p in self.prs.values() if p.get('state', 'open') == 'open']

    def pull_request(self, number):
        return dict(self.prs[number])

    def changed_files(self, number):
        return set(self.files[number])

    def required_contexts(self):
        return list(self.required)

    def context_states(self, sha):
        return dict(self.states.get(sha, {}))

    def set_gate(self, sha, state, description):
        self.gates.append((sha, state, description))

    def update_branch(self, number, sha):
        self.updates.append((number, sha))
        return True

    def merge_pull_request(self, number, sha):
        merged_sha = (hex(number)[2:] * 40)[:40]
        self.merges.append((number, sha, merged_sha))
        self.prs[number]['state'] = 'closed'
        self.prs[number]['merged'] = True
        self.prs[number]['mergeCommitSha'] = merged_sha
        self._main = merged_sha
        return merged_sha


def pr(number: int, sha: str, *, labels=None, files=None, merge_state='CLEAN', title=None):
    return {
        'number': number,
        'title': title or f'PR {number}',
        'isDraft': False,
        'headRefOid': sha,
        'headRefName': f'branch-{number}',
        'mergeable': 'MERGEABLE',
        'mergeStateStatus': merge_state,
        'createdAt': f'2026-11-03T00:{number % 60:02d}:00Z',
        'labels': [{'name': x} for x in (labels or [])],
        'state': 'open',
        'merged': False,
        'files': set(files or {f'f-{number}.txt'}),
    }


def write_lkg(root: Path, sha: str):
    path = root / 'protected-readback' / 'production-control-state.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        'last_known_good': {'manifest': {'revision': sha}}
    }))


def write_approved(spool: Path, *prs: int):
    spool.mkdir(parents=True, exist_ok=True)
    items = {}
    for i, number in enumerate(prs):
        items[f'DEV-{i}'] = {
            'pr_number': number,
            'phase': 'pr_ready',
            'approved_by': 'al-teamaot-com',
        }
    (spool / 'development-state.json').write_text(json.dumps({'items': items}))


def test_gh_api_open_pr_discovery_uses_paginated_rest(monkeypatch):
    api = queue.GhApi("al-teamaot-com/jason")
    calls = []
    pages = [[{
        "number": 2399,
        "title": "P0 recovery",
        "draft": False,
        "head": {"sha": "a" * 40, "ref": "feature/recovery"},
        "created_at": "2026-11-10T15:00:00Z",
        "labels": [{"name": queue.RECOVERY_LABEL}],
        "state": "open",
        "html_url": "https://github.com/al-teamaot-com/jason/pull/2399",
    }]]

    def fake_run(args, *, input_text=None):
        calls.append(list(args))
        return json.dumps(pages)

    monkeypatch.setattr(api, "_run", fake_run)
    result = api.open_pull_requests()
    assert calls == [[
        "api", "--paginate", "--slurp",
        "repos/al-teamaot-com/jason/pulls?state=open&base=main&per_page=100",
    ]]
    assert len(result) == 1
    assert result[0]["number"] == 2399
    assert result[0]["headRefOid"] == "a" * 40
    assert result[0]["mergeable"] == "UNKNOWN"
    assert result[0]["mergeStateStatus"] == "UNKNOWN"
    assert result[0]["labels"] == [{"name": queue.RECOVERY_LABEL}]


def test_approved_pr_numbers_uses_durable_development_and_todo(tmp_path):
    spool = tmp_path / 'spool'
    spool.mkdir()
    (spool / 'development-state.json').write_text(json.dumps({'items': {
        'a': {'pr_number': 10, 'phase': 'pr_ready', 'approved_by': 'al'},
        'b': {'pr_number': 11, 'phase': 'blocked', 'approved_by': 'al'},
        'c': {'pr_number': 12, 'phase': 'pr_ready', 'approved_by': ''},
    }}))
    (spool / 'todo-release-state.json').write_text(json.dumps({'items': {
        'x': {'development_pr': 13, 'phase': 'waiting_development_merge'},
        'y': {'development_pr': 14, 'phase': 'complete'},
    }}))
    assert queue.approved_pr_numbers(spool) == {10, 13}


def test_select_train_batches_non_overlapping_ready_prs(tmp_path):
    a = pr(1, 'a' * 40, files={'a.py'})
    b = pr(2, 'b' * 40, files={'b.py'})
    c = pr(3, 'c' * 40, files={'a.py'})
    api = FakeApi(main_sha='0' * 40, prs=[a, b, c])
    selected, waiting = queue.select_train(api, [a, b, c], {1, 2, 3}, batch_size=3)
    assert [x['number'] for x in selected] == [1, 2]
    assert [x['number'] for x in waiting] == [3]
    assert waiting[0]['queue_reason'] == 'overlaps_current_release_train'


def test_unapproved_pr_is_never_selected(tmp_path):
    a = pr(1, 'a' * 40)
    api = FakeApi(main_sha='0' * 40, prs=[a])
    selected, _ = queue.select_train(api, [a], set(), batch_size=3)
    assert selected == []


def test_explicit_integration_ready_label_admits_pr(tmp_path):
    a = pr(1, 'a' * 40, labels=[queue.INTEGRATION_READY_LABEL])
    api = FakeApi(main_sha='0' * 40, prs=[a])
    selected, _ = queue.select_train(api, [a], set(), batch_size=3)
    assert [x['number'] for x in selected] == [1]


def test_main_ahead_of_lkg_infers_release_lock_and_blocks_merges(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 1)
    write_lkg(release, '1' * 40)
    a = pr(1, 'a' * 40)
    api = FakeApi(main_sha='2' * 40, prs=[a])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, batch_size=3)
    assert state['status'] == 'release_locked'
    assert state['release_lock']['candidate_sha'] == '2' * 40
    assert api.merges == []
    assert any(x[1] == 'pending' for x in api.gates)


def test_release_lock_clears_when_candidate_becomes_lkg(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool)
    candidate = '2' * 40
    write_lkg(release, candidate)
    state_path = spool / 'pmv3-integration-queue-state.json'
    spool.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        **queue.empty_state(),
        'release_lock': {'active': True, 'candidate_sha': candidate, 'locked_at': queue.now()},
    }))
    api = FakeApi(main_sha=candidate, prs=[])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, state_path=state_path)
    assert state['release_lock'] is None
    assert state['status'] == 'idle'


def test_train_merges_first_ready_pr_then_keeps_train_open(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 1, 2)
    base = '0' * 40
    write_lkg(release, base)
    a, b = pr(1, 'a' * 40), pr(2, 'b' * 40)
    api = FakeApi(main_sha=base, prs=[a, b])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, batch_size=2)
    assert [x[0] for x in api.merges] == [1]
    merged_sha = api.merges[0][2]
    assert any(sha == merged_sha and status == 'success' for sha, status, _ in api.gates)
    assert state['status'] == 'integrating'
    assert state['train'] is not None
    assert state['train']['merged'] == [1]
    assert state['release_lock'] is None


def test_train_completion_locks_exact_final_main(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 1)
    base = '0' * 40
    write_lkg(release, base)
    a = pr(1, 'a' * 40)
    api = FakeApi(main_sha=base, prs=[a])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, batch_size=1)
    assert state['status'] == 'release_locked'
    assert state['train'] is None
    assert state['release_lock']['candidate_sha'] == api._main
    assert state['release_lock']['reason'] == 'release_train_complete_awaiting_production'
    # Source status must reflect the actual protected merge, not pre-merge main.
    assert state['main_sha'] == api._main
    assert state['production_lkg_sha'] == base


def test_selected_behind_pr_updates_branch_instead_of_merging(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 1)
    base = '0' * 40
    write_lkg(release, base)
    a = pr(1, 'a' * 40, merge_state='BEHIND')
    api = FakeApi(main_sha=base, prs=[a])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release)
    assert api.updates == [(1, 'a' * 40)]
    assert api.merges == []
    assert state['status'] == 'integrating'


def test_explicit_recovery_pr_can_advance_locked_candidate(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 9)
    lkg = '1' * 40
    locked = '2' * 40
    write_lkg(release, lkg)
    state_path = spool / 'pmv3-integration-queue-state.json'
    spool.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        **queue.empty_state(),
        'release_lock': {'active': True, 'candidate_sha': locked, 'locked_at': queue.now()},
    }))
    recovery = pr(9, '9' * 40, labels=[queue.RECOVERY_LABEL], title='P0 recovery: repair release gate')
    api = FakeApi(main_sha=locked, prs=[recovery])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, state_path=state_path)
    assert [x[0] for x in api.merges] == [9]
    merged_sha = api.merges[0][2]
    assert any(sha == merged_sha and status == 'success' for sha, status, _ in api.gates)
    assert state['release_lock']['candidate_sha'] == api._main
    assert state['release_lock']['reason'] == 'release_recovery_candidate_merged'
    assert state['main_sha'] == merged_sha
    assert state['queue'] == []
    assert state['metrics']['admitted_open'] == 0


def test_recovery_merge_checkpoints_locked_candidate_before_status_api_failure(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 9)
    locked = '2' * 40
    write_lkg(release, '1' * 40)
    state_path = spool / 'pmv3-integration-queue-state.json'
    state_path.write_text(json.dumps({
        **queue.empty_state(),
        'release_lock': {'active': True, 'candidate_sha': locked, 'locked_at': queue.now()},
    }))

    class InterruptAfterMerge(FakeApi):
        def set_gate(self, sha, status, description):
            if sha == self._main and self.merges:
                raise RuntimeError('simulated GitHub status API outage after successful merge')
            super().set_gate(sha, status, description)

    api = InterruptAfterMerge(
        main_sha=locked,
        prs=[pr(9, '9' * 40, labels=[queue.RECOVERY_LABEL])],
    )
    with pytest.raises(RuntimeError, match='status API outage'):
        queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release, state_path=state_path)
    assert len(api.merges) == 1
    checkpoint = queue.load_state(state_path)
    assert checkpoint['status'] == 'release_locked'
    assert checkpoint['main_sha'] == api._main
    assert checkpoint['release_lock']['candidate_sha'] == api._main
    assert checkpoint['queue'] == []


def test_checks_ready_excludes_gate_from_required_contexts():
    a = pr(1, 'a' * 40)
    api = FakeApi(main_sha='0' * 40, prs=[a], required=['cap-001'])
    api.states['a' * 40] = {'cap-001': 'success', queue.GATE_CONTEXT: 'pending'}
    assert queue.checks_ready(api, 'a' * 40) == (True, [])


def test_unknown_lkg_fails_closed_and_does_not_start_train(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    write_approved(spool, 1)
    a = pr(1, 'a' * 40)
    api = FakeApi(main_sha='2' * 40, prs=[a])
    state = queue.reconcile(independent_source=False, api=api, spool=spool, release_state=release)
    assert state['status'] == 'release_locked'
    assert state['release_lock']['reason'] == 'verified_production_revision_unknown'
    assert api.merges == []


def test_read_only_status_refreshes_live_revision_without_mutating_queue(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    spool.mkdir()
    merged = 'a' * 40
    prior = '0' * 40
    stored = {
        **queue.empty_state(),
        'status': 'release_locked',
        'main_sha': prior,
        'production_lkg_sha': prior,
        'release_lock': queue._release_lock(
            merged, None, reason='release_train_complete_awaiting_production',
        ),
    }
    path = spool / 'pmv3-integration-queue-state.json'
    path.write_text(json.dumps(stored))
    original = path.read_bytes()
    write_lkg(release, merged)
    api = FakeApi(main_sha=merged, prs=[])

    result = queue.current_status(independent_source=False, api=api, spool=spool, release_state=release)
    assert result['main_sha'] == merged
    assert result['production_lkg_sha'] == merged
    assert result['stored_main_sha'] == prior
    assert result['stored_production_lkg_sha'] == prior
    assert result['queue_state_stale'] is True
    assert result['status'] == 'release_complete_pending_queue_refresh'
    assert result['release_lock_reconciliation_pending'] is True
    assert result['release_lock_active'] is True  # Stored lock remains enforceable.
    assert result['release_candidate_sha'] == merged
    assert path.read_bytes() == original
    assert not api.merges and not api.gates


def test_read_only_status_keeps_main_ahead_of_production_locked(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    spool.mkdir()
    candidate, prior = 'b' * 40, 'a' * 40
    stored = {**queue.empty_state(), 'status': 'idle',
              'main_sha': prior, 'production_lkg_sha': prior}
    path = spool / 'pmv3-integration-queue-state.json'
    path.write_text(json.dumps(stored))
    original = path.read_bytes()
    write_lkg(release, prior)
    api = FakeApi(main_sha=candidate, prs=[])

    result = queue.current_status(independent_source=False, api=api, spool=spool, release_state=release)
    assert result['main_sha'] == candidate
    assert result['production_lkg_sha'] == prior
    assert result['status'] == 'release_locked'
    assert result['release_lock_reconciliation_pending'] is False
    assert result['queue_state_stale'] is True
    assert path.read_bytes() == original
    assert not api.merges and not api.gates


def test_read_only_status_unknown_production_is_fail_closed(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    spool.mkdir()
    api = FakeApi(main_sha='c' * 40, prs=[])
    result = queue.current_status(independent_source=False, api=api, spool=spool, release_state=release)
    assert result['status'] == 'release_locked'
    assert result['production_lkg_sha'] == ''
    assert result['release_lock_reconciliation_pending'] is False
    assert not (spool / 'pmv3-integration-queue-state.json').exists()
    assert not api.merges and not api.gates


def test_read_only_status_rejects_unverifiable_protected_main(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    spool.mkdir()
    write_lkg(release, 'a' * 40)
    ledger = spool / 'pmv3-integration-queue-state.json'
    ledger.write_text(json.dumps(queue.empty_state()))
    before = ledger.read_bytes()
    api = FakeApi(main_sha='unavailable', prs=[])
    with pytest.raises(ValueError, match='protected main SHA is unavailable'):
        queue.current_status(independent_source=False, api=api, spool=spool, release_state=release)
    assert ledger.read_bytes() == before
    assert not api.gates and not api.merges


def test_read_only_status_does_not_clear_unrelated_release_lock(tmp_path):
    spool, release = tmp_path / 'spool', tmp_path / 'release'
    spool.mkdir()
    accepted, unrelated = 'a' * 40, 'b' * 40
    write_lkg(release, accepted)
    ledger = spool / 'pmv3-integration-queue-state.json'
    ledger.write_text(json.dumps({
        **queue.empty_state(), 'status': 'release_locked',
        'release_lock': queue._release_lock(
            unrelated, None, reason='release_train_complete_awaiting_production',
        ),
    }))
    before = ledger.read_bytes()
    api = FakeApi(main_sha=accepted, prs=[])
    result = queue.current_status(independent_source=False, api=api, spool=spool, release_state=release)
    assert result['status'] == 'release_locked'
    assert result['release_lock_active'] is True
    assert result['release_lock_reconciliation_pending'] is False
    assert result['release_candidate_sha'] == unrelated
    assert ledger.read_bytes() == before
    assert not api.gates and not api.merges



def test_retired_required_integration_check_is_never_reinstalled():
    # The source and mock API intentionally provide no branch-protection
    # writer. A future attempt to resurrect the old call will fail existing
    # controller/regression tests rather than quietly rewriting GitHub rules.
    assert not hasattr(queue.GhApi, "ensure_gate_required")
    assert not hasattr(FakeApi, "ensure_gate_required")


def independent_fixture(tmp_path, *numbers):
    spool, release = tmp_path / "spool", tmp_path / "release"
    write_approved(spool, *numbers)
    write_lkg(release, "f" * 40)
    lock = release / "production-transaction.lock"
    lock.touch(mode=0o660)
    lock.chmod(0o660)
    entries = [pr(n, hex(n+10)[2:] * 40) for n in numbers]
    for row in entries:
        row["baseRefName"] = "main"
    api = FakeApi(main_sha="2" * 40, prs=entries)
    api.source_ready = lambda n, head, main, files, body=None: (
        api.main_sha() == main and api.prs[n]["headRefOid"] == head and api.files[n] == files)
    return spool, release, api


def test_independent_trains_advance_without_production_promotion(tmp_path):
    spool, release, api = independent_fixture(tmp_path, 1, 2)
    path = spool / "pmv3-integration-queue-state.json"
    old = queue._release_lock("2"*40, None, reason="main_ahead_of_verified_production")
    path.write_text(json.dumps({**queue.empty_state(), "release_lock": old}))
    native = release / "protected-readback" / "production-control-state.json"
    before = native.read_bytes()
    lock_inode = (release / "production-transaction.lock").stat().st_ino
    for _ in range(2):
        state = queue.reconcile(api=api, spool=spool, release_state=release, batch_size=1)
        assert state["status"] == "source_backlog"
        assert state["release_lock"] is None
        assert state["legacy_release_locks"] == [old]
        assert state["source_backlog"]["pending_production_review"] is True
        assert state["source_backlog"]["production_authority"] is False
    assert [x[0] for x in api.merges] == [1,2]
    assert native.read_bytes() == before
    assert (release / "production-transaction.lock").stat().st_ino == lock_inode
    old_bytes = path.read_bytes()
    status = queue.current_status(api=api,spool=spool,release_state=release)
    assert status["status"] == "source_backlog"
    assert status["source_backlog"]["main_sha"] == api.main_sha()
    assert path.read_bytes() == old_bytes


def test_independent_mutex_blocks_actual_production_lock_and_second_queue(tmp_path):
    import fcntl
    spool, release, api = independent_fixture(tmp_path, 1)
    for path in (release / "production-transaction.lock", spool / ".pmv3-source-integration.lock"):
        with path.open("a+") as handle:
            path.chmod(0o600)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = queue.reconcile(api=api, spool=spool, release_state=release)
            assert result["status"] == "source_integration_deferred"
    assert not api.merges and not api.gates and not api.updates
    assert not (spool / "pmv3-integration-queue-state.json").exists()


def test_independent_mutex_remains_held_during_merge(tmp_path):
    import fcntl
    spool, release, api = independent_fixture(tmp_path, 1)
    merge = api.merge_pull_request
    def guarded(n,sha):
        with (release / "production-transaction.lock").open("r") as f:
            with pytest.raises(BlockingIOError):
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return merge(n,sha)
    api.merge_pull_request=guarded
    queue.reconcile(api=api,spool=spool,release_state=release)
    assert len(api.merges)==1


@pytest.mark.parametrize("defect",["missing","symlink","untrusted"])
def test_independent_mutex_denies_missing_or_untrusted_lock(tmp_path,defect):
    spool,release,api=independent_fixture(tmp_path,1)
    path=release/"production-transaction.lock"
    if defect=="untrusted":path.chmod(0o666)
    else:
        path.unlink()
        if defect=="symlink":
            target=release/"other"
            target.touch()
            path.symlink_to(target)
    with pytest.raises((OSError,PermissionError)):
        queue.reconcile(api=api,spool=spool,release_state=release)
    assert not api.merges and not api.gates and not api.updates


def test_independent_unknown_lkg_blocks_even_recovery_pr(tmp_path):
    spool,release,api=independent_fixture(tmp_path,1)
    (release/"protected-readback/production-control-state.json").unlink()
    api.prs[1]["labels"]=[{"name":queue.RECOVERY_LABEL}]
    state=queue.reconcile(api=api,spool=spool,release_state=release)
    assert state["status"]=="release_locked"
    assert not api.merges and not api.updates


@pytest.mark.parametrize("defect",["draft","revoked","base","changed_files","pause","lock_replaced","main_moved","body","checks"])
def test_independent_rechecks_exact_source_at_mutation(tmp_path,defect):
    spool,release,api=independent_fixture(tmp_path,1)
    def stale(*args):
        if defect=="draft":api.prs[1]["isDraft"]=True
        elif defect=="revoked":write_approved(spool)
        elif defect=="base":api.prs[1]["baseRefName"]="other"
        elif defect=="changed_files":api.files[1].add("unreviewed")
        elif defect=="pause":(spool/"pmv3-engineering-owner-pause.json").touch()
        elif defect=="lock_replaced":
            path=release/"production-transaction.lock"
            path.rename(release/"old-lock")
            path.touch(mode=0o600)
        elif defect=="main_moved":api._main="3"*40
        elif defect=="body":api.prs[1]["body"]="changed review"
        elif defect=="checks":api.states[api.prs[1]["headRefOid"]]["runtime-service"]="pending"
        return True
    api.source_ready=stale
    try:queue.reconcile(api=api,spool=spool,release_state=release)
    except PermissionError:pass
    assert not api.merges and not api.updates


def test_independent_required_checks_and_exact_review_are_mandatory(tmp_path):
    spool,release,api=independent_fixture(tmp_path,1)
    api.source_ready=lambda *a:False
    queue.reconcile(api=api,spool=spool,release_state=release)
    assert not api.merges
    api.source_ready=lambda *a:True
    api.states[api.prs[1]["headRefOid"]]["runtime-service"]="failure"
    queue.reconcile(api=api,spool=spool,release_state=release)
    assert not api.merges


def test_independent_merge_checkpoint_survives_advisory_status_error(tmp_path):
    spool,release,api=independent_fixture(tmp_path,1)
    set_gate=api.set_gate
    def fail(sha,state,desc):
        if "integrated selected" in desc:raise RuntimeError("status network failure")
        set_gate(sha,state,desc)
    api.set_gate=fail
    with pytest.raises(RuntimeError,match="status network failure"):
        queue.reconcile(api=api,spool=spool,release_state=release)
    saved=queue.load_state(spool/"pmv3-integration-queue-state.json")
    assert saved["train"]["merged"]==[1]
    assert saved["source_backlog"]["main_sha"]==api.main_sha()
    api.set_gate=set_gate
    queue.reconcile(api=api,spool=spool,release_state=release)
    assert len(api.merges)==1


def test_source_ready_requires_strict_current_base_and_fresh_overlap_review(monkeypatch):
    api=queue.GhApi()
    main,head="1"*40,"2"*40
    files={"tools/example.py"}
    prefix="repos/al-teamaot-com/jason/"
    answers={
        prefix+"branches/main":{"protected":True,"commit":{"sha":main}},
        prefix+"branches/main/protection/required_status_checks":{"strict":True,"contexts":["repository-hygiene"]},
        prefix+f"compare/{main}...{head}":{"status":"ahead","merge_base_commit":{"sha":main}},
    }
    monkeypatch.setattr(api,"_api_json",lambda path:answers[path])
    monkeypatch.setattr(api,"pull_request",lambda n:{"state":"open","isDraft":False,"baseRefName":"main","baseRefOid":main,"headRefOid":head,"changedFileCount":1,"body":""})
    monkeypatch.setattr(api,"changed_files",lambda n:files)
    monkeypatch.setattr(api,"_run",lambda args:json.dumps([[]]))
    assert api.source_ready(1,head,main,files)
    answers[prefix+"branches/main/protection/required_status_checks"]["strict"]=False
    assert not api.source_ready(1,head,main,files)
    answers[prefix+"branches/main/protection/required_status_checks"]["strict"]=True
    answers[prefix+f"compare/{main}...{head}"]["merge_base_commit"]["sha"]="3"*40
    assert not api.source_ready(1,head,main,files)
    answers[prefix+f"compare/{main}...{head}"]["merge_base_commit"]["sha"]=main
    from datetime import datetime,timezone
    def overlap(args):
        if "/pulls?" in args[-1]:
            return json.dumps([[{"number":2,"updated_at":datetime.now(timezone.utc).isoformat()}]])
        return json.dumps([[{"filename":"tools/example.py"}]])
    monkeypatch.setattr(api,"_run",overlap)
    assert not api.source_ready(1,head,main,files)


def test_long_source_review_does_not_hold_production_mutex(tmp_path):
    import fcntl
    spool,release,api=independent_fixture(tmp_path,1)
    handle=(release/"production-transaction.lock").open("r")
    def concurrent_release(*args):
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return True
    api.source_ready=concurrent_release
    try:
        state=queue.reconcile(api=api,spool=spool,release_state=release)
        assert state["status"]=="source_integration_deferred"
        assert not api.merges and not api.updates
    finally:handle.close()
    api.source_ready=lambda *args:True
    queue.reconcile(api=api,spool=spool,release_state=release)
    assert len(api.merges)==1
