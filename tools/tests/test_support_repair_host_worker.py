import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'support_repair_host_worker.py'
SPEC = importlib.util.spec_from_file_location('support_repair_host_worker', MODULE)
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(worker)


def test_parse_support_prioritizes_open_items_and_keeps_acceptance():
    text = '''| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |\n| --- | --- | --- | --- | --- | --- |\n| SUPPORT-OPS-200 | P2 | Open | Later | evidence 2 | acceptance 2 |\n| SUPPORT-OPS-100 | P1 | Open | First | evidence 1 | acceptance 1 |\n| SUPPORT-OPS-050 | P1 | Closed 2026-09-29 | Closed | e | a |\n'''
    parsed = worker.parse_support(text)
    assert [item['id'] for item in parsed] == ['SUPPORT-OPS-100', 'SUPPORT-OPS-200']
    assert parsed[0]['acceptance'] == 'acceptance 1'


def test_repair_pr_requires_support_metadata():
    prs = [
        {'number': 10, 'body': '- Support item: SUPPORT-OPS-100\n- Release class: autonomous-repair-candidate'},
        {'number': 11, 'body': 'mentions SUPPORT-OPS-200 without repair metadata'},
    ]
    assert worker.repair_pr_for('SUPPORT-OPS-100', prs)['number'] == 10
    assert worker.repair_pr_for('SUPPORT-OPS-200', prs) is None


def test_request_id_binds_context():
    payload = {
        'kind': 'search_plan', 'support_item': 'SUPPORT-OPS-100', 'title': 'x',
        'evidence': 'e', 'acceptance': 'a', 'context': {},
    }
    first = worker.request_id(payload)
    payload['context'] = {'changed': True}
    assert worker.request_id(payload) != first


class Gate:
    @staticmethod
    def path_denial_reason(path, policy):
        return 'denied' if path.startswith('implementation/connectors/') else None

    @staticmethod
    def is_test_path(path, policy):
        return '/tests/' in path or Path(path).name.startswith('test_')


def test_apply_edits_rejects_denied_path(tmp_path):
    target = tmp_path / 'implementation/connectors/example.py'
    target.parent.mkdir(parents=True)
    target.write_text('old', encoding='utf-8')
    try:
        worker.apply_edits(
            tmp_path,
            [{'path': 'implementation/connectors/example.py', 'old_text': 'old', 'new_text': 'new'}],
            Gate(),
            {'max_changed_lines': 800, 'max_changed_files': 25},
        )
    except worker.WorkerError as exc:
        assert 'denied' in str(exc)
    else:
        raise AssertionError('denied path was accepted')


def test_apply_edits_requires_exact_single_anchor(tmp_path):
    target = tmp_path / 'implementation/example.py'
    target.parent.mkdir(parents=True)
    target.write_text('old\nold\n', encoding='utf-8')
    try:
        worker.apply_edits(
            tmp_path,
            [{'path': 'implementation/example.py', 'old_text': 'old', 'new_text': 'new'}],
            Gate(),
            {'max_changed_lines': 800, 'max_changed_files': 25},
        )
    except worker.WorkerError as exc:
        assert 'occur once' in str(exc)
    else:
        raise AssertionError('ambiguous anchor was accepted')


def test_blocked_item_does_not_consume_active_slot():
    state = {
        'items': {
            'SUPPORT-OPS-001': {'phase': 'blocked'},
            'SUPPORT-OPS-002': {'phase': 'production_verifying'},
        }
    }
    support = [
        {'id': 'SUPPORT-OPS-001'},
        {'id': 'SUPPORT-OPS-002'},
        {'id': 'SUPPORT-OPS-003'},
        {'id': 'SUPPORT-OPS-004'},
        {'id': 'SUPPORT-OPS-005'},
    ]
    selected = worker.select_reconcile_ids(state, support, 2)
    assert 'SUPPORT-OPS-001' not in selected
    assert 'SUPPORT-OPS-002' in selected
    assert 'SUPPORT-OPS-003' in selected
    assert 'SUPPORT-OPS-004' in selected
    assert 'SUPPORT-OPS-005' not in selected
