import importlib.util
import json
import pytest
import subprocess
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'support_repair_host_worker.py'
SPEC = importlib.util.spec_from_file_location('support_repair_host_worker', MODULE)
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(worker)


def test_emit_lifecycle_event_is_deterministic_and_bounded(tmp_path):
    root = tmp_path / 'events'
    first = worker.emit_lifecycle_event(
        event_type='work_started',
        work_id='SUPPORT-OPS-100',
        work_title='Example repair',
        summary='Autonomous support repair has started.',
        event_root=root,
    )
    second = worker.emit_lifecycle_event(
        event_type='work_started',
        work_id='SUPPORT-OPS-100',
        work_title='Example repair',
        summary='Autonomous support repair has started.',
        event_root=root,
    )
    assert first == second
    paths = list(root.glob('*.json'))
    assert len(paths) == 1
    payload = worker.json.loads(paths[0].read_text())
    assert payload['work_id'] == 'SUPPORT-OPS-100'
    assert payload['event_type'] == 'work_started'


def test_sync_support_lifecycle_writes_start_and_explicit_owner_blocker(tmp_path):
    record = {'phase': 'blocked', 'reason': 'controlled blocker',
              'notification_class': 'owner_action_required',
              'owner_action': 'Approve protected core release'}
    item = {'id': 'SUPPORT-OPS-100', 'title': 'Example repair'}
    root = tmp_path / 'events'
    worker.sync_support_lifecycle_notification(record, item, event_root=root)
    assert record['lifecycle_started_fingerprint']
    assert record['lifecycle_blocked_fingerprint']
    payloads = [worker.json.loads(p.read_text()) for p in root.glob('*.json')]
    assert {p['event_type'] for p in payloads} == {'work_started', 'work_blocked'}


def test_sync_support_lifecycle_writes_verified_completion(tmp_path):
    record = {'phase': 'complete'}
    item = {'id': 'SUPPORT-OPS-100', 'title': 'Example repair'}
    root = tmp_path / 'events'
    worker.sync_support_lifecycle_notification(record, item, event_root=root)
    assert record['lifecycle_completed_fingerprint']
    payloads = [worker.json.loads(p.read_text()) for p in root.glob('*.json')]
    assert {p['event_type'] for p in payloads} == {'work_started', 'work_completed'}


def test_parse_support_prioritizes_open_items_and_keeps_acceptance():
    text = '''| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |\n| --- | --- | --- | --- | --- | --- |\n| SUPPORT-OPS-200 | P2 | Open | Later | evidence 2 | acceptance 2 |\n| SUPPORT-OPS-100 | P1 | Open | First | evidence 1 | acceptance 1 |\n| SUPPORT-OPS-050 | P1 | Closed 2026-09-29 | Closed | e | a |\n'''
    parsed = worker.parse_support(text)
    assert [item['id'] for item in parsed] == ['SUPPORT-OPS-100', 'SUPPORT-OPS-200']
    assert parsed[0]['acceptance'] == 'acceptance 1'


def test_distinct_rollback_and_toner_support_identities_in_canonical_source():
    source = (MODULE.parents[1] / 'SUPPORT.md').read_text(encoding='utf-8')
    rows = worker.parse_support(source)
    rollback = [row for row in rows if row['id'] == 'SUPPORT-OPS-058']
    assert len(rollback) == 1
    assert 'issue #1101' in rollback[0]['status']
    assert 'rollback' in rollback[0]['title'].lower()
    assert not any(row['id'] == 'SUPPORT-OPS-051' for row in rows)
    assert 'Closed 2026-10-07 — issue #1091' in source


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


def test_gh_json_retries_transient_command_failure(tmp_path, monkeypatch):
    attempts = []

    def fake_run(args, *, cwd=None, **kwargs):
        attempts.append(list(args))
        if len(attempts) == 1:
            raise worker.WorkerError('HTTP 504')
        return '[{"number": 1}]'

    monkeypatch.setattr(worker, 'run', fake_run)
    monkeypatch.setattr(worker.time, 'sleep', lambda _: None)
    assert worker.gh_json(['pr', 'list'], cwd=tmp_path) == [{'number': 1}]
    assert len(attempts) == 2


def test_gh_json_retries_malformed_json(tmp_path, monkeypatch):
    responses = iter(['[{', '[]'])
    monkeypatch.setattr(worker, 'run', lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(worker.time, 'sleep', lambda _: None)
    assert worker.gh_json(['pr', 'list'], cwd=tmp_path) == []


def test_gh_json_fails_closed_after_three_attempts(tmp_path, monkeypatch):
    attempts = []

    def fake_run(args, *, cwd=None, **kwargs):
        attempts.append(list(args))
        raise worker.WorkerError('provider unavailable')

    monkeypatch.setattr(worker, 'run', fake_run)
    monkeypatch.setattr(worker.time, 'sleep', lambda _: None)
    try:
        worker.gh_json(['pr', 'list'], cwd=tmp_path)
    except worker.WorkerError as exc:
        assert 'after 3 bounded attempts' in str(exc)
    else:
        raise AssertionError('persistent GitHub failure did not fail closed')
    assert len(attempts) == 3


class Gate:
    @staticmethod
    def path_denial_reason(path, policy):
        return 'denied' if path.startswith('implementation/connectors/') else None

    @staticmethod
    def is_test_path(path, policy):
        return '/tests/' in path or Path(path).name.startswith('test_')




def test_safe_search_prefers_source_over_docs(tmp_path, monkeypatch):
    for rel in [
        'README.md',
        'docs/architecture/example.md',
        'config/example.json',
        'tools/example.py',
        'implementation/kernel/capability_registry.py',
    ]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('capability lifecycle', encoding='utf-8')

    def fake_run(args, **kwargs):
        if args[-1] in {'capability lifecycle', 'capability', 'lifecycle'}:
            return '\n'.join([
                'README.md',
                'docs/architecture/example.md',
                'config/example.json',
                'tools/example.py',
                'implementation/kernel/capability_registry.py',
            ])
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['capability lifecycle'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    paths = [entry['path'] for entry in excerpts]
    assert paths[0] == 'implementation/kernel/capability_registry.py'
    assert paths.index('tools/example.py') < paths.index('docs/architecture/example.md')


def test_safe_search_prefers_concept_subject_owned_source_path(tmp_path, monkeypatch):
    capability = tmp_path / 'implementation' / 'kernel' / 'capabilities' / 'service.py'
    lifecycle = tmp_path / 'implementation' / 'kernel' / 'system_registry' / 'lifecycle_registry.py'
    capability.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    capability.write_text('capability lifecycle registry\n', encoding='utf-8')
    lifecycle.write_text('lifecycle registry retirement\n', encoding='utf-8')

    def fake_run(args, **kwargs):
        term = args[-1]
        if term == 'capability':
            return capability.relative_to(tmp_path).as_posix()
        if term in {'lifecycle', 'registry'}:
            return '\n'.join([
                capability.relative_to(tmp_path).as_posix(),
                lifecycle.relative_to(tmp_path).as_posix(),
            ])
        if term == 'retirement':
            return lifecycle.relative_to(tmp_path).as_posix()
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['capability lifecycle registry retirement'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    assert excerpts[0]['path'] == capability.relative_to(tmp_path).as_posix()


def test_safe_search_preserves_distinct_reasoning_concept_coverage(tmp_path, monkeypatch):
    first = tmp_path / 'implementation' / 'kernel' / 'capabilities' / 'service.py'
    second = tmp_path / 'implementation' / 'kernel' / 'system_registry' / 'contracts.py'
    first.parent.mkdir(parents=True, exist_ok=True)
    second.parent.mkdir(parents=True, exist_ok=True)
    first.write_text('capability lifecycle retirement\n', encoding='utf-8')
    second.write_text('dependency graph consumers\n', encoding='utf-8')

    def fake_run(args, **kwargs):
        term = args[-1]
        if term in {'capability', 'lifecycle', 'retirement'}:
            return first.relative_to(tmp_path).as_posix()
        if term in {'dependency', 'graph', 'consumers'}:
            return second.relative_to(tmp_path).as_posix()
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['capability lifecycle retirement', 'dependency graph consumers'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    paths = [entry['path'] for entry in excerpts]
    assert first.relative_to(tmp_path).as_posix() in paths
    assert second.relative_to(tmp_path).as_posix() in paths


def test_companion_source_paths_maps_package_level_registry_test():
    companions = worker.companion_source_paths(
        'implementation/kernel/tests/test_capabilities.py'
    )
    assert 'implementation/kernel/capabilities/service.py' in companions
    assert 'implementation/kernel/capabilities/contracts.py' in companions
    assert 'implementation/kernel/capabilities/repository.py' in companions


def test_safe_search_does_not_let_generic_term_exhaust_later_concepts(tmp_path, monkeypatch):
    generic_paths = []
    for index in range(505):
        target = tmp_path / 'implementation' / f'generic_{index:03d}.py'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('capability\n', encoding='utf-8')
        generic_paths.append(target.relative_to(tmp_path).as_posix())
    lifecycle = tmp_path / 'implementation' / 'kernel' / 'capabilities' / 'service.py'
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text('capability retirement\n', encoding='utf-8')
    lifecycle_path = lifecycle.relative_to(tmp_path).as_posix()

    def fake_run(args, **kwargs):
        term = args[-1]
        if term == 'capability':
            return '\n'.join(generic_paths + [lifecycle_path])
        if term == 'retirement':
            return lifecycle_path
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['capability retirement'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    assert excerpts[0]['path'] == lifecycle_path


def test_safe_search_prefers_multi_concept_match_over_alphabetical_source(tmp_path, monkeypatch):
    generic = tmp_path / 'implementation' / 'aaa_generic.py'
    lifecycle = tmp_path / 'implementation' / 'kernel' / 'capabilities' / 'service.py'
    generic.parent.mkdir(parents=True)
    lifecycle.parent.mkdir(parents=True)
    generic.write_text('capability only\n', encoding='utf-8')
    lifecycle.write_text('capability lifecycle registry retirement\n', encoding='utf-8')

    def fake_run(args, **kwargs):
        term = args[-1]
        if term == 'capability':
            return 'implementation/aaa_generic.py\nimplementation/kernel/capabilities/service.py'
        if term in {'lifecycle', 'registry', 'retirement'}:
            return 'implementation/kernel/capabilities/service.py'
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['capability lifecycle registry retirement'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    assert excerpts[0]['path'] == 'implementation/kernel/capabilities/service.py'


def test_safe_search_expands_model_phrase_and_pairs_test_with_source(tmp_path, monkeypatch):
    source = tmp_path / 'tools' / 'jason_self_heal_watchdog.py'
    test = tmp_path / 'tools' / 'tests' / 'test_jason_self_heal_watchdog.py'
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    source.write_text('selected_gt_active_slots = True\n', encoding='utf-8')
    test.write_text('def test_selected_gt_active_slots(): pass\n', encoding='utf-8')

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[-1] == 'selected_gt_active_slots':
            return 'tools/tests/test_jason_self_heal_watchdog.py'
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['autonomy invariant selected_gt_active_slots repair worker slot selection'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )

    paths = [entry['path'] for entry in excerpts]
    assert 'tools/tests/test_jason_self_heal_watchdog.py' in paths
    assert 'tools/jason_self_heal_watchdog.py' in paths
    assert any(call[-1] == 'selected_gt_active_slots' for call in calls)


def test_safe_search_pairs_src_package_source_with_project_level_test(tmp_path, monkeypatch):
    source = tmp_path / 'implementation' / 'runtime_service' / 'src' / 'jason_runtime' / 'capability_lifecycle.py'
    test = tmp_path / 'implementation' / 'runtime_service' / 'tests' / 'test_capability_lifecycle.py'
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    source.write_text('def retirement_eligible(): return True\n', encoding='utf-8')
    test.write_text('def test_retirement_eligible(): pass\n', encoding='utf-8')

    def fake_run(args, **kwargs):
        if args[-1] == 'retirement_eligible':
            return source.relative_to(tmp_path).as_posix()
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['retirement_eligible'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    paths = [entry['path'] for entry in excerpts]
    assert source.relative_to(tmp_path).as_posix() in paths
    assert test.relative_to(tmp_path).as_posix() in paths


def test_safe_search_pairs_same_directory_source_and_test(tmp_path, monkeypatch):
    source = tmp_path / 'implementation' / 'autonomous_remediation' / 'autonomous_principal.py'
    test = tmp_path / 'implementation' / 'autonomous_remediation' / 'test_autonomous_principal.py'
    source.parent.mkdir(parents=True)
    source.write_text('def retirement_evidence(): return True\n', encoding='utf-8')
    test.write_text('def test_retirement_evidence(): pass\n', encoding='utf-8')

    def fake_run(args, **kwargs):
        if args[-1] == 'retirement_evidence':
            return source.relative_to(tmp_path).as_posix()
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['retirement_evidence'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    paths = [entry['path'] for entry in excerpts]
    assert source.relative_to(tmp_path).as_posix() in paths
    assert test.relative_to(tmp_path).as_posix() in paths


def test_companion_source_paths_maps_project_level_test_layout():
    companions = worker.companion_source_paths(
        'implementation/runtime_service/src/jason_runtime/capability_lifecycle.py'
    )
    assert (
        'implementation/runtime_service/tests/test_capability_lifecycle.py'
        in companions
    )


def test_expanded_search_terms_are_bounded_and_preserve_identifiers():
    terms = ['selected_gt_active_slots selected_gt_eligible repair worker slot selection'] * 8
    expanded = worker.expanded_search_terms(terms)
    assert 'selected_gt_active_slots' in expanded
    assert 'selected_gt_eligible' in expanded
    assert len(expanded) <= 40

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


def test_apply_edits_can_create_bounded_new_file(tmp_path):
    touched = worker.apply_edits(
        tmp_path,
        [
            {
                'path': 'implementation/kernel/capabilities/retirement.py',
                'old_text': '',
                'new_text': '"""Capability retirement helpers."""\n',
            }
        ],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    target = tmp_path / 'implementation/kernel/capabilities/retirement.py'
    assert touched == ['implementation/kernel/capabilities/retirement.py']
    assert target.read_text(encoding='utf-8') == '"""Capability retirement helpers."""\n'


def test_apply_edits_rejects_new_file_over_existing_path(tmp_path):
    target = tmp_path / 'implementation/example.py'
    target.parent.mkdir(parents=True)
    target.write_text('existing\n', encoding='utf-8')
    try:
        worker.apply_edits(
            tmp_path,
            [{'path': 'implementation/example.py', 'old_text': '', 'new_text': 'replacement\n'}],
            Gate(),
            {'max_changed_lines': 800, 'max_changed_files': 25},
        )
    except worker.WorkerError as exc:
        assert 'already exists' in str(exc)
    else:
        raise AssertionError('new-file edit overwrote an existing file')


def test_identified_items_are_queued_and_do_not_bypass_active_limit():
    state = {
        'items': {
            'SUPPORT-OPS-001': {'phase': 'identified'},
            'SUPPORT-OPS-002': {'phase': 'identified'},
            'SUPPORT-OPS-003': {'phase': 'identified'},
        }
    }
    support = [
        {'id': 'SUPPORT-OPS-001'},
        {'id': 'SUPPORT-OPS-002'},
        {'id': 'SUPPORT-OPS-003'},
    ]
    selected = worker.select_reconcile_ids(state, support, 2)
    assert selected == ['SUPPORT-OPS-001', 'SUPPORT-OPS-002']


def test_existing_active_work_consumes_slot_before_identified_queue():
    state = {
        'items': {
            'SUPPORT-OPS-001': {'phase': 'diagnosing'},
            'SUPPORT-OPS-002': {'phase': 'identified'},
            'SUPPORT-OPS-003': {'phase': 'identified'},
        }
    }
    support = [
        {'id': 'SUPPORT-OPS-001'},
        {'id': 'SUPPORT-OPS-002'},
        {'id': 'SUPPORT-OPS-003'},
    ]
    selected = worker.select_reconcile_ids(state, support, 2)
    assert selected == ['SUPPORT-OPS-001', 'SUPPORT-OPS-002']


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


def test_support_issue_intersection_fails_closed_on_stale_rows():
    items = [
        {'id': 'SUPPORT-OPS-023'},
        {'id': 'SUPPORT-OPS-025'},
        {'id': 'SUPPORT-OPS-028'},
    ]
    selected = worker.eligible_support_items(
        items,
        {'SUPPORT-OPS-025', 'SUPPORT-OPS-028'},
    )
    assert [item['id'] for item in selected] == ['SUPPORT-OPS-025', 'SUPPORT-OPS-028']


def test_support_id_from_title_is_exact_and_case_normalized():
    assert worker.support_id_from_title('SUPPORT-OPS-028 — active status') == 'SUPPORT-OPS-028'
    assert worker.support_id_from_title('unrelated issue') is None


def test_load_self_heal_incidents_returns_repair_required_items(tmp_path):
    root = tmp_path / 'self-heal'
    incidents = root / 'incidents'
    incidents.mkdir(parents=True)
    (incidents / 'abc.json').write_text(
        '{"state":"repair_required","support_item":"SUPPORT-AUTO-ABCDEF123456","priority":"P1","title":"degraded","evidence":"failed","acceptance":"restore"}',
        encoding='utf-8',
    )
    items = worker.load_self_heal_incidents(root)
    assert len(items) == 1
    assert items[0]['id'] == 'SUPPORT-AUTO-ABCDEF123456'
    assert items[0]['acceptance'] == 'restore'


def test_source_excerpts_for_paths_is_bounded_and_policy_filtered(tmp_path):
    allowed = tmp_path / 'implementation' / 'kernel' / 'capabilities' / 'service.py'
    allowed.parent.mkdir(parents=True, exist_ok=True)
    allowed.write_text('service-body', encoding='utf-8')
    missing = 'implementation/kernel/capabilities/missing.py'
    excerpts = worker.source_excerpts_for_paths(
        tmp_path,
        [allowed.relative_to(tmp_path).as_posix(), missing],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
        limit=1,
    )
    assert [item['path'] for item in excerpts] == [allowed.relative_to(tmp_path).as_posix()]


def test_source_excerpts_for_paths_keeps_full_identified_file_up_to_24k(tmp_path):
    allowed = tmp_path / 'implementation' / 'decision_memory' / 'resolution_service.py'
    allowed.parent.mkdir(parents=True, exist_ok=True)
    body = 'header\n' + ('x' * 12000) + '\nexact-lifecycle-method\n'
    allowed.write_text(body, encoding='utf-8')
    excerpts = worker.source_excerpts_for_paths(
        tmp_path,
        [allowed.relative_to(tmp_path).as_posix()],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
        terms=['exact-lifecycle-method'],
    )
    assert excerpts[0]['content'] == body


def test_source_excerpts_for_paths_centers_large_file_on_search_term(tmp_path):
    allowed = tmp_path / 'implementation' / 'orchestrator' / 'provider_read_capability_catalog.py'
    allowed.parent.mkdir(parents=True, exist_ok=True)
    body = 'prefix\n' + ('x' * 28000) + '\nidentity-investigation-read\n' + ('y' * 28000)
    allowed.write_text(body, encoding='utf-8')
    excerpts = worker.source_excerpts_for_paths(
        tmp_path,
        [allowed.relative_to(tmp_path).as_posix()],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
        terms=['identity-investigation-read'],
    )
    assert 'identity-investigation-read' in excerpts[0]['content']
    assert len(excerpts[0]['content']) <= 24000


def test_merge_source_excerpts_keeps_prior_context_and_adds_new():
    prior = [
        {'path': 'implementation/kernel/capabilities/repository.py', 'content': 'repo'},
        {'path': 'implementation/kernel/capabilities/service.py', 'content': 'service'},
    ]
    current = [
        {'path': 'implementation/kernel/capabilities/service.py', 'content': 'new-service'},
        {'path': 'implementation/kernel/system_registry/contracts.py', 'content': 'system'},
    ]
    merged = worker.merge_source_excerpts(prior, current, max_total=3)
    assert [item['path'] for item in merged] == [
        'implementation/kernel/capabilities/repository.py',
        'implementation/kernel/capabilities/service.py',
        'implementation/kernel/system_registry/contracts.py',
    ]
    assert merged[1]['content'] == 'service'


def test_load_correlated_self_heal_incident_includes_root_invariant_and_verification(tmp_path):
    root = tmp_path / 'self-heal'
    incidents = root / 'incidents'
    incidents.mkdir(parents=True)
    payload = {
        'state': 'repair_required',
        'support_item': 'SUPPORT-AUTO-123456ABCDEF',
        'priority': 'P0',
        'title': 'Production convergence incomplete',
        'evidence': 'artifact drift',
        'acceptance': 'restore and verify',
        'root_invariant': 'runtime = mcp = host = workers',
        'repair_level': 2,
        'repair_class': 'bounded_autonomous_repair',
        'occurrence_count': 2,
        'verification_contract': {'required_checks': ['rerun production convergence detector']},
    }
    (incidents / 'correlated.json').write_text(json.dumps(payload), encoding='utf-8')
    items = worker.load_self_heal_incidents(root)
    assert len(items) == 1
    assert items[0]['priority'] == 'P0'
    assert 'root invariant: runtime = mcp = host = workers' in items[0]['evidence']
    assert 'repair level: L2 bounded_autonomous_repair' in items[0]['evidence']
    assert 'occurrence: 2' in items[0]['evidence']
    assert 'rerun production convergence detector' in items[0]['acceptance']


def test_self_heal_post_production_verification_requires_related_family_clear(tmp_path, monkeypatch):
    root = tmp_path / 'self-heal'
    incidents = root / 'incidents'
    incidents.mkdir(parents=True)
    payload = {
        'state': 'repair_required',
        'support_item': 'SUPPORT-AUTO-AAAABBBBCCCC',
        'family': 'production_convergence',
        'verification_contract': {
            'related_families_must_be_healthy': [
                'production_convergence', 'runtime_health', 'service_health'
            ]
        },
    }
    (incidents / 'incident.json').write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setattr(
        worker,
        'run',
        lambda *args, **kwargs: json.dumps({
            'failures': ['production_convergence_current_release_drift'],
            'families': ['production_convergence'],
        }),
    )
    verified, reason, evidence = worker.self_heal_post_production_verification(
        tmp_path, 'SUPPORT-AUTO-AAAABBBBCCCC', root
    )
    assert verified is False
    assert 'production_convergence' in reason
    assert evidence['families'] == ['production_convergence']


def test_self_heal_post_production_verification_allows_unrelated_degradation(tmp_path, monkeypatch):
    root = tmp_path / 'self-heal'
    incidents = root / 'incidents'
    incidents.mkdir(parents=True)
    payload = {
        'state': 'repair_required',
        'support_item': 'SUPPORT-AUTO-DDDDEEEEFFFF',
        'family': 'production_convergence',
        'verification_contract': {
            'related_families_must_be_healthy': [
                'production_convergence', 'runtime_health', 'service_health'
            ]
        },
    }
    (incidents / 'incident.json').write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setattr(
        worker,
        'run',
        lambda *args, **kwargs: json.dumps({
            'failures': ['provider_canary_report_stale'],
            'families': ['provider_health'],
        }),
    )
    verified, reason, evidence = worker.self_heal_post_production_verification(
        tmp_path, 'SUPPORT-AUTO-DDDDEEEEFFFF', root
    )
    assert verified is True
    assert 'healthy' in reason
    assert evidence['families'] == ['provider_health']


def test_bounded_relevant_excerpt_includes_match_beyond_file_prefix():
    text = 'header\n' + ('x' * 18000) + '\ndef target_selection_logic():\n    return True\n'
    excerpt = worker.bounded_relevant_excerpt(
        text, ['target_selection_logic'], content_limit=6000
    )
    assert 'header' in excerpt
    assert 'target_selection_logic' in excerpt
    assert len(excerpt) <= 6000


def test_proposed_test_edits_requires_actual_declared_test_edit():
    policy = {'max_changed_lines': 800, 'max_changed_files': 25}
    edits = [
        {'path': 'implementation/example.py', 'old_text': 'a', 'new_text': 'b'},
    ]
    assert worker.proposed_test_edits(
        edits, ['implementation/tests/test_example.py'], Gate(), policy
    ) == []

    edits.append({
        'path': 'implementation/tests/test_example.py',
        'old_text': 'old test',
        'new_text': 'new test',
    })
    assert worker.proposed_test_edits(
        edits, ['implementation/tests/test_example.py'], Gate(), policy
    ) == ['implementation/tests/test_example.py']


def test_safe_search_centers_long_file_excerpt_on_match(tmp_path, monkeypatch):
    target = tmp_path / 'implementation' / 'runtime_service' / 'src' / 'jason_runtime' / 'long_module.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('A' * 16000 + '\nself_heal_escalation = True\n' + 'B' * 16000, encoding='utf-8')

    def fake_run(args, **kwargs):
        if args[-1] in {'self_heal_escalation', 'self', 'heal', 'escalation'}:
            return target.relative_to(tmp_path).as_posix()
        return ''

    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(
        tmp_path,
        ['self_heal_escalation'],
        Gate(),
        {'max_changed_lines': 800, 'max_changed_files': 25},
    )
    assert excerpts
    assert 'self_heal_escalation = True' in excerpts[0]['content']
    assert len(excerpts[0]['content']) <= 14000


def test_transient_github_pr_listing_deferred_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(__import__('sys'), 'argv', ['support_repair_host_worker.py', '--repo', str(tmp_path), '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(worker, 'run', lambda *a, **k: '')
    monkeypatch.setattr(worker, 'parse_support', lambda _: [])
    monkeypatch.setattr(worker, 'load_self_heal_incidents', lambda: [])
    monkeypatch.setattr(worker, 'open_support_issue_records', lambda _: {})
    monkeypatch.setattr(worker, 'open_prs', lambda _: (_ for _ in ()).throw(worker.WorkerError('HTTP 504: gateway timeout')))
    assert worker.main() == 0
    state = worker.load_state(tmp_path / 'spool' / 'state.json')
    assert state['upstream_deferred']['reason'] == 'transient_gateway_error'
    assert state['items'] == {}


def test_nongateway_github_pr_listing_failure_remains_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(__import__('sys'), 'argv', ['support_repair_host_worker.py', '--repo', str(tmp_path), '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(worker, 'run', lambda *a, **k: '')
    monkeypatch.setattr(worker, 'parse_support', lambda _: [])
    monkeypatch.setattr(worker, 'load_self_heal_incidents', lambda: [])
    monkeypatch.setattr(worker, 'open_support_issue_records', lambda _: {})
    monkeypatch.setattr(worker, 'open_prs', lambda _: (_ for _ in ()).throw(worker.WorkerError('HTTP 403: forbidden')))
    try:
        worker.main()
    except worker.WorkerError as exc:
        assert 'HTTP 403' in str(exc)
    else:
        raise AssertionError('Authorization failure must not be deferred')


def test_development_recovery_feed_admits_only_matched_handoffs(tmp_path):
    import support_repair_host_worker as worker
    state = {'items': {
      'DEV-950': {'phase': 'blocked', 'issue_number': 950,
       'recovery_handoff_id': 'abc', 'recovery_support_issue_raised': 'SUPPORT-DEV-950',
       'recovery_handoff_intake': {'status': 'awaiting_governed_repair', 'handoff_id': 'abc'}},
      'DEV-952': {'phase': 'blocked', 'issue_number': 952,
       'recovery_support_issue_raised': 'SUPPORT-DEV-952',
       'recovery_handoff_intake': {'status': 'not_verified', 'handoff_id': 'def'}},
    }}
    worker.save_state(tmp_path / 'development-state.json', state)
    incidents = worker.load_development_recovery_incidents(tmp_path)
    assert [item['id'] for item in incidents] == ['SUPPORT-DEV-950']
    assert incidents[0]['priority'] == 'P0'


def test_dynamic_development_recovery_closure_is_supported_in_source():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'support_repair_host_worker.py').read_text()
    assert "item['id'].startswith(('SUPPORT-AUTO-', 'SUPPORT-DEV-'))" in source


def test_support_recoverable_blocker_silent_and_explicit_owner_action(monkeypatch, tmp_path):
    import support_repair_host_worker as worker
    seen = []
    monkeypatch.setattr(worker, 'emit_lifecycle_event', lambda **kw: (seen.append(kw), 'fp')[1])
    item = {'id': 'SUPPORT-DEV-950', 'title': 'Repair'}
    record = {'phase': 'blocked', 'reason': 'retryable'}
    worker.sync_support_lifecycle_notification(record, item, event_root=tmp_path)
    assert not any(x['event_type'] == 'work_blocked' for x in seen)
    record.update({'notification_class': 'owner_action_required', 'owner_action': 'Approve release'})
    worker.sync_support_lifecycle_notification(record, item, event_root=tmp_path)
    worker.sync_support_lifecycle_notification(record, item, event_root=tmp_path)
    assert len([x for x in seen if x['event_type'] == 'work_blocked']) == 1


def test_support_issue_discovery_includes_later_development_recovery(monkeypatch, tmp_path):
    import support_repair_host_worker as worker
    def fake_gh(args, *, cwd):
        assert args[args.index('--limit') + 1] == '1000'
        return [{'title': f'SUPPORT-OPS-{n:03d}', 'number': n} for n in range(1, 150)] + [
            {'title': 'SUPPORT-DEV-950: Exhausted recovery', 'number': 150}]
    monkeypatch.setattr(worker, 'gh_json', fake_gh)
    assert 'SUPPORT-DEV-950' in worker.open_support_issue_ids(tmp_path)


def test_open_prs_discovers_all_101_without_loading_bulk_ci(monkeypatch, tmp_path):
    calls = []

    def fake_gh_json(args, *, cwd):
        calls.append(list(args))
        return [
            {'number': i, 'title': f'PR {i}', 'body': '',
             'headRefName': f'branch-{i}', 'url': f'https://example.test/{i}', 'isDraft': False}
            for i in range(1, 102)
        ]

    monkeypatch.setattr(worker, 'gh_json', fake_gh_json)
    prs = worker.open_prs(tmp_path)
    assert len(prs) == 101
    assert prs[-1]['number'] == 101
    assert calls[0][calls[0].index('--limit') + 1] == '1000'
    fields = calls[0][calls[0].index('--json') + 1]
    assert 'body' in fields
    assert 'statusCheckRollup' not in fields
    assert worker.check_state({'statusCheckRollup': [
        {'name': 'validation', 'status': 'COMPLETED', 'conclusion': 'FAILURE'}
    ]})[0] == 'failed'


def test_open_prs_rejects_incomplete_and_invalid_listing(monkeypatch, tmp_path):
    import pytest

    for result in (None, {'number': 1}, [
        {'number': i, 'headRefName': f'b{i}', 'body': ''} for i in range(1000)
    ], [
        {'number': 1, 'headRefName': 'a', 'body': ''},
        {'number': 1, 'headRefName': 'a', 'body': ''},
    ]):
        monkeypatch.setattr(worker, 'gh_json', lambda *a, **kw: result)
        with pytest.raises(worker.WorkerError):
            worker.open_prs(tmp_path)


def test_transient_github_listing_error_is_deferred_without_permission_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr(__import__('sys'), 'argv',
        ['support_repair_host_worker.py', '--repo', str(tmp_path), '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(worker, 'run', lambda *a, **k: '')
    monkeypatch.setattr(worker, 'parse_support', lambda _: [])
    monkeypatch.setattr(worker, 'load_self_heal_incidents', lambda: [])
    monkeypatch.setattr(worker, 'open_support_issue_records', lambda _: {})
    monkeypatch.setattr(worker, 'open_prs', lambda _: (_ for _ in ()).throw(
        worker.WorkerError('GitHub JSON command failed after 3 bounded attempts: command failed (gh): unexpected end of JSON input')))
    assert worker.main() == 0
    state = worker.load_state(tmp_path / 'spool' / 'state.json')
    assert state['upstream_deferred']['provider'] == 'github'
    assert state['items'] == {}
    assert not worker.transient_github_listing_failure(worker.WorkerError('HTTP 403: forbidden'))


def test_transient_pr_listing_classifier_preserves_authority_boundary():
    retryable = (
        'HTTP 502: bad gateway', 'HTTP 503: unavailable',
        'HTTP 504: gateway timeout',
        'GitHub JSON command failed: unexpected end of JSON input',
    )
    for error in retryable:
        assert worker.transient_github_listing_failure(worker.WorkerError(error))
    for error in ('HTTP 403: forbidden', 'HTTP 401: unauthorized',
                  'approval required', 'invalid JSON record'):
        assert not worker.transient_github_listing_failure(worker.WorkerError(error))


def test_bounded_full_approved_test_source(tmp_path):
    import types, pytest
    f=tmp_path/'tools/tests/test_large.py'
    f.parent.mkdir(parents=True)
    body='def test_large():\n    assert True\n'+'# source\n'*7000
    f.write_text(body)
    g=types.SimpleNamespace(path_denial_reason=lambda path,policy:'')
    p='tools/tests/test_large.py'
    v=worker.source_excerpts_for_paths(tmp_path,[p],g,{},terms=['test_large'],content_limit=96000,full_file_paths=[p])
    assert v[0]['content']==body
    with pytest.raises(worker.WorkerError,match='required complete source exceeds'):
        worker.source_excerpts_for_paths(tmp_path,[p],g,{},terms=['test_large'],content_limit=56000,full_file_paths=[p])
    denied=types.SimpleNamespace(path_denial_reason=lambda path,policy:'denied')
    assert worker.source_excerpts_for_paths(tmp_path,[p],denied,{},content_limit=96000,full_file_paths=[p])==[]



def test_symbol_context_preamble_does_not_truncate_unrelated_function():
    import ast
    preamble = 'import json\n' + ''.join(
        f'CONFIG_{i} = {i}\n' for i in range(82)
    )
    text = (preamble
            + 'def unrelated():\n'
            + '    one = 1\n'
            + '    two = 2\n'
            + '    return one + two\n'
            + 'def requested_target():\n'
            + '    return json.dumps({"ok": True})\n')
    # The former raw 1,300-character prefix ends within a Python definition.
    import pytest
    with pytest.raises(SyntaxError):
        ast.parse(text[:1300])
    excerpt = worker.bounded_symbol_excerpt(
        text, ['requested_target'], content_limit=9000
    )
    assert excerpt is not None
    prefix, _, definition = excerpt.partition('\n# Complete definition')
    ast.parse(prefix)
    assert 'def requested_target' in definition
    assert 'return json.dumps' in definition
    assert 'def unrelated():\n    one = 1\n    two = 2\n    return one + two' in prefix or 'def unrelated' not in prefix



def test_validate_patch_runs_isolated_worktree_tests_with_local_tools_import(monkeypatch, tmp_path):
    import subprocess
    import types
    repo = tmp_path / 'isolated'
    source = repo / 'tools' / 'local_validation_module.py'
    test = repo / 'tools' / 'tests' / 'test_local_validation_module.py'
    test.parent.mkdir(parents=True)
    source.write_text('VALUE = 1\n')
    test.write_text('from local_validation_module import VALUE\n\ndef test_value():\n    assert VALUE == 1\n')
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo, check=True)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-qm', 'initial'], cwd=repo, check=True)
    source.write_text('VALUE = 2\n')
    test.write_text('from local_validation_module import VALUE\n\ndef test_value():\n    assert VALUE == 2\n')
    monkeypatch.setenv('PYTHONPATH', str(tmp_path / 'unrelated'))
    gate = types.SimpleNamespace(
        path_denial_reason=lambda path, policy: '',
        is_test_path=lambda path, policy: path.startswith('tools/tests/test_')
    )
    selected = worker.validate_patch(
        repo, ['tools/tests/test_local_validation_module.py'], gate, {}
    )
    assert selected == ['tools/tests/test_local_validation_module.py']



def test_safe_search_discovers_named_provider_source_not_just_tests(tmp_path):
    import subprocess
    import types
    repo = tmp_path / 'repo'
    base = repo / 'implementation/connectors/it_glue'
    base.mkdir(parents=True)
    (base / 'live_read.py').write_text('class DocumentReader:\n    pass\n')
    (base / 'operations.py').write_text('class Operations:\n    pass\n')
    other = repo / 'implementation/connectors/tests/test_it_glue_live_read.py'
    other.parent.mkdir(parents=True)
    other.write_text('def test_it_glue_document_search_read():\n    assert True\n')
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    excerpts = worker.safe_search(
        repo, ['IT Glue document search read implementation',
               'IT Glue provider adapter search read attachment'],
        gate, {}
    )
    result = {entry['path'] for entry in excerpts}
    assert 'implementation/connectors/it_glue/live_read.py' in result
    assert 'implementation/connectors/it_glue/operations.py' in result
    assert all(entry['content'] for entry in excerpts)


def test_missing_p0_support_issue_is_visible_and_emits_blocker(tmp_path):
    state = {}
    issues = {
        'SUPPORT-OPS-500': {'title': 'P0 SUPPORT-OPS-500: missing row', 'priority': 'P0'},
        'SUPPORT-OPS-501': {'title': 'P1 SUPPORT-OPS-501: missing row', 'priority': 'unknown'},
        'SUPPORT-OPS-502': {'title': 'P0 SUPPORT-OPS-502: admitted', 'priority': 'P0'},
    }
    known = [{'id': 'SUPPORT-OPS-502'}]
    missing = worker.audit_support_admission(issues, known, state, event_root=tmp_path)
    assert missing == ['SUPPORT-OPS-500']
    assert state['admission_audit']['status'] == 'degraded'
    assert state['admission_audit']['unadmitted_p0'] == ['SUPPORT-OPS-500']
    payloads = [worker.json.loads(p.read_text()) for p in tmp_path.glob('*.json')]
    assert len(payloads) == 1
    assert payloads[0]['event_type'] == 'work_blocked'
    assert payloads[0]['work_id'] == 'SUPPORT-OPS-500'
    assert payloads[0]['owner_action'].startswith('Reconcile issue')
    worker.audit_support_admission(issues, known, state, event_root=tmp_path)
    assert len(list(tmp_path.glob('*.json'))) == 1  # duplicate-suppressed


def test_open_issue_listing_fails_closed_on_incomplete_page(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: [
        {'number': i, 'title': f'P0 SUPPORT-OPS-{i}: incident'} for i in range(1000)
    ])
    import pytest
    with pytest.raises(worker.WorkerError, match='incomplete'):
        worker.open_support_issue_records(tmp_path)


def test_missing_non_p0_does_not_escalate_owner(tmp_path):
    state = {}
    issues = {'SUPPORT-OPS-600': {'title': 'P1 SUPPORT-OPS-600: review', 'priority': 'unknown'}}
    assert worker.audit_support_admission(issues, [], state, event_root=tmp_path) == []
    assert state['admission_audit']['status'] == 'healthy'
    assert not list(tmp_path.glob('*.json'))


def test_reassess_model_only_block_once_under_existing_active_cap(tmp_path):
    item = {'id': 'SUPPORT-OPS-056', 'title': 'Release record defect',
            'evidence': 'Missing release_manifest', 'acceptance': 'Test pass', 'priority': 'P0'}
    previous = 'The defect inherently requires new authority because of root-governed rollback.'
    rid = worker.queue_reasoning(tmp_path, kind='search_plan', item=item, context={})
    response_path = tmp_path / 'reasoning' / 'responses' / (rid + '.json')
    response_path.parent.mkdir(parents=True)
    response_path.write_text(worker.json.dumps({
        'status': 'succeeded', 'result': {'diagnosis': 'root',
        'search_terms': ['release_manifest'], 'blocked_reason': previous}}))
    record = {'phase': 'blocked', 'reason': previous, 'reasoning_request_id': rid}
    state = {'items': {item['id']: record}}
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 2) == [item['id']]
    assert record['phase'] == 'diagnosing'
    assert record['scope_review_attempted'] is True
    assert record['reasoning_request_id'] != rid
    request = worker.json.loads((tmp_path / 'reasoning' / 'requests' / (record['reasoning_request_id'] + '.json')).read_text())
    assert request['context']['scope_review'] == 'source_diagnosis_only'
    assert request['context']['prior_blocked_reason'] == previous
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 2) == []
    record.update({'phase': 'blocked', 'reason': 'Actually needs privilege'})
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 2) == []


def test_reassess_does_not_override_host_denial_transport_or_capacity(tmp_path):
    item = {'id': 'SUPPORT-OPS-057', 'title': 'Defect',
            'evidence': 'e', 'acceptance': 'a', 'priority': 'P0'}
    rid = worker.queue_reasoning(tmp_path, kind='search_plan', item=item, context={})
    response_path = tmp_path / 'reasoning' / 'responses' / (rid + '.json')
    response_path.parent.mkdir(parents=True)
    response_path.write_text(worker.json.dumps({'status': 'succeeded', 'result': {'blocked_reason': 'model scope denied'}}))
    record = {'phase': 'blocked', 'reason': 'model scope denied', 'reasoning_request_id': rid}
    state = {'items': {item['id']: record, 'SUPPORT-OPS-099': {'phase': 'implementing'}}}
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 1) == []
    assert record['phase'] == 'blocked'
    state['items'].pop('SUPPORT-OPS-099')
    record['reason'] = 'repair path denied by J-CHANGE-002'
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 2) == []
    record['reason'] = 'model scope denied'
    response_path.write_text(worker.json.dumps({'status': 'failed', 'error': 'HTTP transport failed'}))
    assert worker.reassess_model_scope_blocks(state, [item], tmp_path, 2) == []
    assert record['phase'] == 'blocked'


def test_scope_review_chooses_one_p0_before_lower_priority(tmp_path):
    priority = [
        {'id': 'SUPPORT-OPS-400', 'title': 'P0 control failure', 'evidence': 'e', 'acceptance': 'a', 'priority': 'P0'},
        {'id': 'SUPPORT-OPS-401', 'title': 'P1 report', 'evidence': 'e', 'acceptance': 'a', 'priority': 'P1'},
    ]
    items = {}
    for item in priority:
        rid = worker.queue_reasoning(tmp_path, kind='search_plan', item=item, context={})
        result_dir = tmp_path / 'reasoning' / 'responses'
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / (rid + '.json')).write_text(worker.json.dumps({
            'status': 'succeeded', 'result': {'blocked_reason': 'model scope denied'}}))
        items[item['id']] = {'phase': 'blocked', 'reason': 'model scope denied', 'reasoning_request_id': rid}
    state = {'items': items}
    assert worker.reassess_model_scope_blocks(state, priority, tmp_path, 1) == ['SUPPORT-OPS-400']
    assert items['SUPPORT-OPS-400']['phase'] == 'diagnosing'
    assert items['SUPPORT-OPS-401']['phase'] == 'blocked'
    assert worker.reassess_model_scope_blocks(state, priority, tmp_path, 1) == []


def test_recovered_edit_reasoning_readmits_only_verified_exact_request(tmp_path):
    import json
    rid = 'a' * 64
    response_dir = tmp_path / 'reasoning' / 'responses'
    response_dir.mkdir(parents=True)
    (response_dir / f'{rid}.json').write_text(json.dumps({
        'status': 'succeeded', 'request_id': rid, 'kind': 'edit_plan',
        'support_item': 'SUPPORT-OPS-123', 'result': {'edits': []},
    }))
    record = {'phase': 'blocked', 'reason': 'edit reasoning failed: HTTP transport failed with status 400',
              'reasoning_request_id': rid}
    state = {'items': {'SUPPORT-OPS-123': record}}
    eligible = [{'id': 'SUPPORT-OPS-123'}]
    assert worker.readmit_recovered_reasoning(state, eligible, tmp_path, max_active=2) == ['SUPPORT-OPS-123']
    assert record['phase'] == 'implementing'
    assert worker.readmit_recovered_reasoning(state, eligible, tmp_path, max_active=2) == []


def test_recovery_rejects_mismatched_reasoning_reply(tmp_path):
    import json
    rid = 'b' * 64
    response_dir = tmp_path / 'reasoning' / 'responses'
    response_dir.mkdir(parents=True)
    (response_dir / f'{rid}.json').write_text(json.dumps({
        'status': 'succeeded', 'request_id': rid, 'kind': 'edit_plan',
        'support_item': 'SUPPORT-OPS-OTHER', 'result': {},
    }))
    state = {'items': {'SUPPORT-OPS-123': {'phase': 'blocked',
        'reason': 'edit reasoning failed: HTTP transport failed with status 400',
        'reasoning_request_id': rid}}}
    assert worker.readmit_recovered_reasoning(state, [{'id': 'SUPPORT-OPS-123'}], tmp_path,
                                                max_active=2) == []


def test_recovered_reasoning_respects_existing_active_worker_capacity(tmp_path):
    import json
    root = tmp_path / 'reasoning' / 'responses'
    root.mkdir(parents=True)
    state = {'items': {'SUPPORT-OPS-1': {'phase': 'diagnosing'}}}
    eligible = []
    for index, letter in enumerate('abc', start=2):
        rid = letter * 64
        item_id = f'SUPPORT-OPS-{index}'
        (root / f'{rid}.json').write_text(json.dumps({
            'status': 'succeeded', 'request_id': rid, 'kind': 'edit_plan',
            'support_item': item_id, 'result': {'edits': []},
        }))
        state['items'][item_id] = {
            'phase': 'blocked', 'reason': 'edit reasoning failed: HTTP transport failed with status 400',
            'reasoning_request_id': rid,
        }
        eligible.append({'id': item_id})
    resumed = worker.readmit_recovered_reasoning(state, eligible, tmp_path, max_active=2)
    assert resumed == ['SUPPORT-OPS-2']
    assert state['items']['SUPPORT-OPS-3']['phase'] == 'blocked'
    assert state['items']['SUPPORT-OPS-4']['phase'] == 'blocked'

def _transport_recovery_fixture(tmp_path, *, error='HTTP transport failed with status 400',
                                bigger_proof=True, proof_kind='edit_plan', billing=False):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    target = {'id':'SUPPORT-OPS-054', 'priority':'P0', 'title':'Fix support intake',
              'evidence':'e', 'acceptance':'a'}
    proof = {'id':'SUPPORT-DEV-1196', 'priority':'P0', 'title':'Other verified response',
             'evidence':'e', 'acceptance':'a'}
    failed = worker.queue_reasoning(
        tmp_path, kind='edit_plan', item=target,
        context={'source_excerpts': ['X' * 3000]},
    )
    good = worker.queue_reasoning(
        tmp_path, kind=proof_kind, item=proof,
        context={'source_excerpts': ['Y' * (4000 if bigger_proof else 50)]},
    )
    out = tmp_path / 'reasoning' / 'responses'
    out.mkdir(parents=True, exist_ok=True)
    failure = {'request_id': failed, 'status':'failed',
               'error_type':'ConnectorTransportError', 'error':error,
               'completed_at':(now-timedelta(hours=2)).isoformat()}
    if billing:
        failure['provider_error_code'] = 'credit_balance_exhausted'
    (out / (failed+'.json')).write_text(worker.json.dumps(failure))
    (out / (good+'.json')).write_text(worker.json.dumps({
        'request_id':good, 'kind':proof_kind, 'support_item':proof['id'],
        'status':'succeeded', 'completed_at':(now-timedelta(minutes=2)).isoformat(),
        'result': {'summary':'verified non-executing result', 'edits':[]},
    }))
    record = {'phase':'blocked','reason':'edit reasoning failed: '+error,
              'reasoning_request_id':failed,'self_recovery_attempts':2}
    return target, failed, good, record


def test_verified_newer_larger_edit_response_allows_one_distinct_p0_readmission(tmp_path):
    target, failed, proof, record = _transport_recovery_fixture(tmp_path)
    state={'items':{target['id']:record}}
    assert worker.readmit_after_verified_transport_recovery(state,[target],tmp_path,max_active=2)==[target['id']]
    assert record['phase']=='implementing'
    assert record['provider_recovery_original_failure_id']==failed
    assert record['provider_recovery_proof_id']==proof
    assert record['reasoning_request_id'] != failed
    assert record['self_recovery_attempts']==2
    new = worker.json.loads((tmp_path/'reasoning'/'requests'/(record['reasoning_request_id']+'.json')).read_text())
    assert new['context']['verified_transport_recovery']['retry_limit']==1
    assert worker.reasoning_response(tmp_path,failed)['status']=='failed'
    # Even if a later response fails, the one-shot evidence cannot re-admit again.
    record['phase']='blocked'
    record['reason']='edit reasoning failed: HTTP transport failed with status 400'
    assert worker.readmit_after_verified_transport_recovery(state,[target],tmp_path,max_active=2)==[]


def test_transport_recovery_rejects_smaller_proof_and_known_billing(tmp_path):
    for name, kw in [('small',{'bigger_proof':False}),('billing',{'billing':True})]:
        root=tmp_path/name
        target, failed, _, record = _transport_recovery_fixture(root,**kw)
        state={'items':{target['id']:record}}
        assert worker.verified_later_reasoning_success(root,failed_rid=failed,
                         item_id=target['id'],kind='edit_plan') is None
        assert worker.readmit_after_verified_transport_recovery(state,[target],root,max_active=2)==[]
        assert record['phase']=='blocked'


def test_transport_recovery_rejects_wrong_kind_closed_priority_and_full_capacity(tmp_path):
    target,failed,_,record=_transport_recovery_fixture(tmp_path,proof_kind='search_plan')
    assert worker.verified_later_reasoning_success(tmp_path,failed_rid=failed,
                   item_id=target['id'],kind='edit_plan') is None
    assert worker.readmit_after_verified_transport_recovery(
        {'items':{target['id']:record}},[target],tmp_path,max_active=2)==[]
    target2,_,_,record2=_transport_recovery_fixture(tmp_path/'second')
    target2['priority']='P1'
    assert worker.readmit_after_verified_transport_recovery(
        {'items':{target2['id']:record2}},[target2],tmp_path/'second',max_active=2)==[]
    target2['priority']='P0'
    assert worker.readmit_after_verified_transport_recovery(
        {'items':{target2['id']:record2,'SUPPORT-OPS-1':{'phase':'diagnosing'}}},
        [target2],tmp_path/'second',max_active=1)==[]


def test_transport_recovery_rejects_untrusted_mismatch_and_pending_governed_repair(tmp_path):
    target,failed,_,record=_transport_recovery_fixture(tmp_path)
    record['recovery_handoff_intake']={'status':'awaiting_governed_repair'}
    assert worker.readmit_after_verified_transport_recovery(
        {'items':{target['id']:record}},[target],tmp_path,max_active=2)==[]
    del record['recovery_handoff_intake']
    source=tmp_path/'reasoning'/'requests'/(failed+'.json')
    mutated=worker.json.loads(source.read_text());mutated['context']['source_excerpts']=['tampered']
    source.write_text(worker.json.dumps(mutated))
    assert worker.verified_later_reasoning_success(tmp_path,failed_rid=failed,
                   item_id=target['id'],kind='edit_plan') is None


def test_apply_edits_validates_all_anchors_before_any_writes(tmp_path):
    first = tmp_path / 'implementation' / 'example.py'
    second = tmp_path / 'implementation' / 'tests' / 'test_example.py'
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text('source-old\n', encoding='utf-8')
    second.write_text('test-old\n', encoding='utf-8')
    try:
        worker.apply_edits(tmp_path, [
            {'path':'implementation/example.py', 'old_text':'source-old', 'new_text':'source-new'},
            {'path':'implementation/tests/test_example.py', 'old_text':'missing-test-anchor', 'new_text':'test-new'},
        ], Gate(), {'max_changed_lines':800,'max_changed_files':25})
    except worker.WorkerError as exc:
        assert 'occur once' in str(exc)
    else:
        raise AssertionError('missing later anchor was accepted')
    assert first.read_text(encoding='utf-8') == 'source-old\n'
    assert second.read_text(encoding='utf-8') == 'test-old\n'


def test_apply_edits_preserves_sequential_same_file_replacements(tmp_path):
    target = tmp_path / 'implementation' / 'example.py'
    target.parent.mkdir(parents=True)
    target.write_text('start\n', encoding='utf-8')
    changed = worker.apply_edits(tmp_path, [
        {'path':'implementation/example.py', 'old_text':'start', 'new_text':'middle'},
        {'path':'implementation/example.py', 'old_text':'middle', 'new_text':'finish'},
    ], Gate(), {'max_changed_lines':800,'max_changed_files':25})
    assert changed == ['implementation/example.py']
    assert target.read_text(encoding='utf-8') == 'finish\n'


def test_bounded_anchor_retry_queues_feedback_only_on_clean_owned_worktree(monkeypatch, tmp_path):
    requests = []
    monkeypatch.setattr(worker, 'run', lambda args, **kw: '' if args == ['git','status','--porcelain'] else 'unexpected')
    monkeypatch.setattr(worker, 'source_excerpts_for_paths', lambda *args, **kw: [{'path':'implementation/example.py','content':'source'}])
    monkeypatch.setattr(worker, 'queue_reasoning', lambda spool, **kw: requests.append(kw) or 'new-request-1')
    item = {'id':'SUPPORT-DEV-1196','title':'bounded repair','evidence':'approved','acceptance':'tests'}
    record = {'phase':'implementing','reasoning_request_id':'previous','attempts':0,'proposal_retries':0}
    edits = [{'path':'implementation/example.py','old_text':'not-there','new_text':'fix'}]
    failure = worker.WorkerError('exact repair anchor must occur once in implementation/example.py; found 0')
    assert worker.queue_bounded_anchor_correction(tmp_path,tmp_path,item,record,edits,['implementation/tests/test_example.py'],failure,Gate(),{}) is True
    assert len(requests) == 1
    assert requests[0]['kind'] == 'edit_plan'
    assert requests[0]['context']['retry_number'] == 1
    assert 'exact-text anchor' in requests[0]['context']['validation_feedback']
    assert record['phase'] == 'implementing'
    assert record['reasoning_request_id'] == 'new-request-1'
    assert record['proposal_retries'] == 1 and record['attempts'] == 0


def test_bounded_anchor_retry_fails_closed_on_dirty_or_exhausted_input(monkeypatch,tmp_path):
    requests = []
    monkeypatch.setattr(worker, 'run', lambda args, **kw: ' M implementation/example.py')
    monkeypatch.setattr(worker, 'queue_reasoning', lambda *args, **kw: requests.append(True))
    item = {'id':'SUPPORT-DEV-1196'}
    record = {'proposal_retries':0,'reasoning_request_id':'original','phase':'implementing'}
    failure = worker.WorkerError('exact repair anchor must occur once in implementation/example.py; found 0')
    assert worker.queue_bounded_anchor_correction(tmp_path,tmp_path,item,record,[],[],failure,Gate(),{}) is False
    record['proposal_retries'] = 2
    assert worker.queue_bounded_anchor_correction(tmp_path,tmp_path,item,record,[],[],failure,Gate(),{}) is False
    assert worker.queue_bounded_anchor_correction(tmp_path,tmp_path,item,record,[],[],worker.WorkerError('repair path denied by J-CHANGE-002'),Gate(),{}) is False
    assert not requests
    assert record['phase'] == 'implementing' and record['reasoning_request_id'] == 'original'


def test_apply_edits_late_denied_path_has_no_side_effects(tmp_path):
    first = tmp_path / 'implementation' / 'example.py'
    first.parent.mkdir(parents=True)
    first.write_text('original\n', encoding='utf-8')
    try:
        worker.apply_edits(tmp_path, [
            {'path':'implementation/example.py', 'old_text':'original', 'new_text':'changed'},
            {'path':'implementation/connectors/secret.py', 'old_text':'', 'new_text':'denied'},
        ], Gate(), {'max_changed_lines':800,'max_changed_files':25})
    except worker.WorkerError as exc:
        assert 'denied' in str(exc)
    else:
        raise AssertionError('late denied path accepted')
    assert first.read_text(encoding='utf-8') == 'original\n'
    assert not (tmp_path / 'implementation/connectors/secret.py').exists()


def test_apply_edits_late_change_budget_rejection_has_no_side_effects(tmp_path):
    first = tmp_path / 'implementation' / 'example.py'
    first.parent.mkdir(parents=True)
    first.write_text('original\n', encoding='utf-8')
    try:
        worker.apply_edits(tmp_path, [
            {'path':'implementation/example.py', 'old_text':'original', 'new_text':'changed'},
            {'path':'implementation/tests/test_example.py', 'old_text':'', 'new_text':'one\ntwo\nthree'},
        ], Gate(), {'max_changed_lines':4,'max_changed_files':25})
    except worker.WorkerError as exc:
        assert 'changed-line boundary' in str(exc)
    else:
        raise AssertionError('late over-budget change accepted')
    assert first.read_text(encoding='utf-8') == 'original\n'
    assert not (tmp_path / 'implementation/tests/test_example.py').exists()


def _legacy_partial_anchor_fixture(tmp_path):
    import subprocess
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args, cwd=repo):
        return subprocess.run(['git', *args], cwd=cwd, check=True,
                              text=True, capture_output=True).stdout.strip()
    git('init', '-q')
    git('config', 'user.email', 'tests@example.invalid')
    git('config', 'user.name', 'Test')
    path = repo / 'implementation' / 'example.py'
    path.parent.mkdir(parents=True)
    path.write_text('existing = True\n', encoding='utf-8')
    test = repo / 'implementation' / 'tests' / 'test_example.py'
    test.parent.mkdir(parents=True)
    test.write_text('def test_original():\n    assert True\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'baseline')
    git('branch', '-M', 'main')
    git('branch', 'origin/main', 'main')
    original = tmp_path / 'original'
    rid = 'b' * 64
    item_id = 'SUPPORT-DEV-1196'
    original_branch = worker.branch_name(item_id)
    retry_branch = original_branch + '-anchor-' + rid[:12]
    git('worktree', 'add', '-q', '-b', original_branch, str(original), 'main')
    (original / 'implementation/example.py').write_text('existing = False\n', encoding='utf-8')
    clean = tmp_path / 'clean'
    git('worktree', 'add', '-q', '-b', retry_branch, str(clean), 'main')
    spool = tmp_path / 'spool'
    dest = spool / 'reasoning' / 'responses'
    dest.mkdir(parents=True)
    (dest / (rid + '.json')).write_text(json.dumps({
        'request_id': rid, 'kind': 'edit_plan', 'support_item': item_id,
        'status': 'succeeded', 'result': {
            'blocked_reason': None,
            'edits': [{'path':'implementation/example.py',
                       'old_text':'existing = True', 'new_text':'existing = False'},
                      {'path':'implementation/tests/test_example.py',
                       'old_text':'unavailable anchor', 'new_text':'test change'}],
            'test_paths': ['implementation/tests/test_example.py'],
        },
    }), encoding='utf-8')
    record = {
        'phase': 'blocked', 'branch': original_branch, 'proposal_retries': 0,
        'reasoning_request_id': rid,
        'reason': ('WorkerError: exact repair anchor must occur once in '
                   'implementation/tests/test_example.py; found 0'),
    }
    return repo, original, clean, spool, rid, retry_branch, {'items': {item_id: record}}


def test_preserve_legacy_partial_anchor_worktree_and_resume_clean(monkeypatch, tmp_path):
    repo, old, clean, spool, rid, retry_branch, state = _legacy_partial_anchor_fixture(tmp_path)
    record = state['items']['SUPPORT-DEV-1196']
    path = lambda item, branch=None: clean if branch == retry_branch else old
    monkeypatch.setattr(worker, 'support_worktree_path', path)
    monkeypatch.setattr(worker, 'ensure_worktree', lambda repo, item, branch=None: clean)
    monkeypatch.setattr(worker, 'source_excerpts_for_paths',
                        lambda *a, **k: [{'path':'implementation/example.py',
                                          'content':'existing = True'}])
    requests = []
    monkeypatch.setattr(worker, 'queue_reasoning',
                        lambda spool, **kw: requests.append(kw) or 'c'*64)
    supported = [{'id':'SUPPORT-DEV-1196', 'title':'Recovery',
                  'evidence':'approved', 'acceptance':'tested'}]
    original_content = (old / 'implementation/example.py').read_text()
    resumed = worker.readmit_preserved_anchor_failure(
        state, supported, repo, spool, Gate(), {}, max_active=2)
    assert resumed == ['SUPPORT-DEV-1196']
    assert (old / 'implementation/example.py').read_text() == original_content
    assert (clean / 'implementation/example.py').read_text() == 'existing = True\n'
    evidence = json.loads((spool / 'recovery-evidence' / (rid + '.json')).read_text())
    assert evidence['support_item'] == 'SUPPORT-DEV-1196'
    assert evidence['failed_reasoning_request_id'] == rid
    assert 'existing = False' in evidence['preserved_original_patch']
    assert record['preserved_anchor_patch_sha256'] == evidence['original_patch_sha256']
    assert record['phase'] == 'implementing'
    assert record['branch'] == retry_branch
    assert record['reasoning_request_id'] == 'c'*64
    assert record['proposal_retries'] == 1
    assert requests[0]['kind'] == 'edit_plan'
    assert 'SUPPORT-DEV' in requests[0]['context']['validation_feedback']
    assert worker.readmit_preserved_anchor_failure(
        state, supported, repo, spool, Gate(), {}, max_active=2) == []
    assert len(requests) == 1


def test_preserve_legacy_anchor_requires_original_proof(monkeypatch, tmp_path):
    repo, old, clean, spool, rid, retry_branch, state = _legacy_partial_anchor_fixture(tmp_path)
    record = state['items']['SUPPORT-DEV-1196']
    monkeypatch.setattr(worker, 'support_worktree_path',
                        lambda item, branch=None: old)
    calls = []
    monkeypatch.setattr(worker, 'ensure_worktree', lambda *a, **k: calls.append('worktree'))
    monkeypatch.setattr(worker, 'queue_reasoning', lambda *a, **k: calls.append('request'))
    eligible = [{'id':'SUPPORT-DEV-1196'}]
    record['reasoning_request_id'] = 'd'*64
    assert worker.readmit_preserved_anchor_failure(
        state, eligible, repo, spool, Gate(), {}, max_active=2) == []
    record['reasoning_request_id'] = rid
    record['branch'] = 'repair/custom-overridden'
    assert worker.readmit_preserved_anchor_failure(
        state, eligible, repo, spool, Gate(), {}, max_active=2) == []
    assert calls == []
    assert (old / 'implementation/example.py').read_text() == 'existing = False\n'


def test_preserve_legacy_anchor_fails_closed_for_unrelated_dirty_files(monkeypatch, tmp_path):
    repo, old, clean, spool, rid, retry_branch, state = _legacy_partial_anchor_fixture(tmp_path)
    target = old / 'implementation' / 'unknown.py'
    target.write_text('untracked = True\n', encoding='utf-8')
    monkeypatch.setattr(worker, 'support_worktree_path',
                        lambda item, branch=None: old)
    calls = []
    monkeypatch.setattr(worker, 'ensure_worktree', lambda *a, **k: calls.append('worktree'))
    monkeypatch.setattr(worker, 'queue_reasoning', lambda *a, **k: calls.append('request'))
    assert worker.readmit_preserved_anchor_failure(
        state, [{'id':'SUPPORT-DEV-1196'}], repo, spool, Gate(), {}, max_active=2) == []
    assert calls == []
    assert target.exists()
    assert not (spool / 'recovery-evidence').exists()


def test_recovery_worktree_path_requires_exact_item_and_branch_identity():
    item = 'SUPPORT-DEV-1196'
    branch = worker.branch_name(item) + '-anchor-' + 'f'*12
    assert worker.support_worktree_path(item, branch).name == 'support-dev-1196-anchor-' + 'f'*12
    assert worker.support_worktree_path(item).name == 'support-dev-1196'
    assert worker.support_worktree_path(item, 'repair/something-else').name == 'support-dev-1196'
    try:
        worker.support_worktree_path('../outside', branch)
    except worker.WorkerError as exc:
        assert 'identity' in str(exc)
    else:
        raise AssertionError('unsafe support item path was accepted')


def test_preserve_legacy_anchor_rejects_same_path_manual_tampering(monkeypatch, tmp_path):
    repo, old, clean, spool, rid, retry_branch, state = _legacy_partial_anchor_fixture(tmp_path)
    (old / 'implementation/example.py').write_text(
        'existing = False\nmanual_addition = 1\n', encoding='utf-8')
    monkeypatch.setattr(worker, 'support_worktree_path',
                        lambda item, branch=None: old)
    calls = []
    monkeypatch.setattr(worker, 'ensure_worktree', lambda *args, **kw: calls.append('created'))
    monkeypatch.setattr(worker, 'queue_reasoning', lambda *args, **kw: calls.append('queued'))
    record = state['items']['SUPPORT-DEV-1196']
    assert worker.readmit_preserved_anchor_failure(
        state, [{'id':'SUPPORT-DEV-1196'}], repo, spool, Gate(), {}, max_active=2) == []
    assert not calls
    assert record['phase'] == 'blocked'
    assert not (spool / 'recovery-evidence').exists()
    assert 'manual_addition' in (old / 'implementation/example.py').read_text()


def test_preserve_legacy_anchor_respects_capacity(monkeypatch, tmp_path):
    repo, old, clean, spool, rid, retry_branch, state = _legacy_partial_anchor_fixture(tmp_path)
    state['items']['SUPPORT-OPS-123'] = {'phase': 'diagnosing'}
    monkeypatch.setattr(worker, 'ensure_worktree',
                        lambda *args, **kw: (_ for _ in ()).throw(AssertionError('must not create')))
    assert worker.readmit_preserved_anchor_failure(
        state, [{'id':'SUPPORT-DEV-1196'}], repo, spool, Gate(), {}, max_active=1) == []
    assert state['items']['SUPPORT-DEV-1196']['phase'] == 'blocked'


def _gap_recovery_fixture(tmp_path, monkeypatch):
    class AllowRead:
        def path_denial_reason(self, path, policy):
            return None
    source = tmp_path / 'fresh'
    for path in (
        'tools/support_repair_host_worker.py',
        'tools/tests/test_support_repair_host_worker.py',
        'tools/engineering_pipeline.py',
        'tools/tests/test_engineering_pipeline.py',
    ):
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            'def audit_support_admission():\n    return "support issue admission"\n'
            'def eligible_support_items():\n    return True\n',
            encoding='utf-8',
        )
    item = {
        'id': 'SUPPORT-OPS-054', 'priority': 'P0',
        'title': 'GitHub P0 support issues excluded from admission',
        'evidence': 'Reconcile open SUPPORT issue state with canonical rows',
        'acceptance': 'Prove unmatched P0 support issues have dispositions',
    }
    reason = 'Missing exact source excerpt for support issue admission implementation.'
    rid = worker.queue_reasoning(
        tmp_path, kind='edit_plan', item=item,
        context={'diagnosis': 'original search omitted host source', 'source_excerpts': []},
    )
    responses = tmp_path / 'reasoning' / 'responses'
    responses.mkdir(parents=True, exist_ok=True)
    (responses / (rid + '.json')).write_text(worker.json.dumps({
        'request_id': rid, 'status': 'succeeded', 'kind': 'edit_plan',
        'support_item': item['id'], 'result': {'blocked_reason': reason},
    }))
    record = {
        'phase': 'blocked', 'reason': reason, 'reasoning_request_id': rid,
        'branch': worker.branch_name(item['id']), 'self_recovery_attempts': 2,
    }
    branch = worker.branch_name(item['id']) + '-context-' + rid[:12]
    sha = 'a' * 40
    monkeypatch.setattr(worker, 'ensure_worktree', lambda repo, item_id, requested: source)
    def fake_run(args, *, cwd=None, **kwargs):
        if args[:3] == ['git', 'branch', '--show-current']:
            return branch
        if args[:3] == ['git', 'status', '--porcelain']:
            return ''
        if args[:3] == ['git', 'rev-parse', 'HEAD']:
            return sha
        if args[:3] == ['git', 'rev-parse', 'origin/main']:
            return sha
        raise AssertionError(args)
    monkeypatch.setattr(worker, 'run', fake_run)
    return item, record, AllowRead(), sha, rid


def test_p0_source_gap_recovers_once_with_exact_code_and_test(tmp_path, monkeypatch):
    item, record, gate, sha, original = _gap_recovery_fixture(tmp_path, monkeypatch)
    state = {'items': {item['id']: record}}
    assert worker.readmit_missing_support_source_context(
        state, [item], tmp_path, tmp_path, gate, {}, max_active=2
    ) == [item['id']]
    assert record['phase'] == 'implementing'
    assert record['source_context_recovery_original_id'] == original
    assert record['source_context_recovery_revision'] == sha
    assert record['reasoning_request_id'] != original
    assert record['self_recovery_attempts'] == 2
    assert worker.support_worktree_path(item['id'], record['branch']).name.endswith(
        '-context-' + original[:12]
    )
    request_path = (tmp_path / 'reasoning' / 'requests' /
                    (record['reasoning_request_id'] + '.json'))
    request = worker.json.loads(request_path.read_text())
    assert request['context']['source_context_recovery']['retry_limit'] == 1
    assert request['context']['source_context_recovery']['previous_request_id'] == original
    assert [x['path'] for x in request['context']['source_excerpts']] == [
        'tools/support_repair_host_worker.py',
        'tools/tests/test_support_repair_host_worker.py',
        'tools/engineering_pipeline.py',
        'tools/tests/test_engineering_pipeline.py',
    ]
    assert 'audit_support_admission' in request['context']['source_excerpts'][0]['content']
    assert worker.reasoning_response(tmp_path, original)['status'] == 'succeeded'
    record['phase'] = 'blocked'
    assert worker.readmit_missing_support_source_context(
        state, [item], tmp_path, tmp_path, gate, {}, max_active=2
    ) == []


def test_p0_source_gap_rejects_wrong_response_identity(tmp_path, monkeypatch):
    item, record, gate, _, rid = _gap_recovery_fixture(tmp_path, monkeypatch)
    path = tmp_path / 'reasoning' / 'responses' / (rid + '.json')
    response = worker.json.loads(path.read_text())
    response['support_item'] = 'SUPPORT-OPS-OTHER'
    path.write_text(worker.json.dumps(response))
    assert worker.readmit_missing_support_source_context(
        {'items': {item['id']: record}}, [item], tmp_path, tmp_path,
        gate, {}, max_active=2
    ) == []
    assert record['phase'] == 'blocked'


def test_p0_source_gap_rejects_unapproved_or_full_capacity(tmp_path, monkeypatch):
    item, record, gate, _, _ = _gap_recovery_fixture(tmp_path, monkeypatch)
    state = {'items': {item['id']: record}}
    item['priority'] = 'P1'
    assert worker.readmit_missing_support_source_context(
        state, [item], tmp_path, tmp_path, gate, {}, max_active=2
    ) == []
    item['priority'] = 'P0'
    state['items']['OTHER'] = {'phase': 'implementing'}
    assert worker.readmit_missing_support_source_context(
        state, [item], tmp_path, tmp_path, gate, {}, max_active=1
    ) == []
    del state['items']['OTHER']
    item.update(title='Printer driver update', evidence='Printer offline',
                acceptance='Installed driver verified')
    assert worker.readmit_missing_support_source_context(
        state, [item], tmp_path, tmp_path, gate, {}, max_active=2
    ) == []
    assert record.get('source_context_recovery_request_id') is None


def test_p0_source_gap_rejects_dirty_worktree(tmp_path, monkeypatch):
    item, record, gate, _, _ = _gap_recovery_fixture(tmp_path, monkeypatch)
    prior = worker.run
    def dirty_run(args, **kwargs):
        if args[:3] == ['git', 'status', '--porcelain']:
            return ' M tools/support_repair_host_worker.py'
        return prior(args, **kwargs)
    monkeypatch.setattr(worker, 'run', dirty_run)
    assert worker.readmit_missing_support_source_context(
        {'items': {item['id']: record}}, [item], tmp_path, tmp_path,
        gate, {}, max_active=2
    ) == []
    assert record['phase'] == 'blocked'


def test_p0_source_gap_rejects_stale_branch_identity(tmp_path, monkeypatch):
    item, record, gate, _, _ = _gap_recovery_fixture(tmp_path, monkeypatch)
    original_run = worker.run
    def stale_run(args, **kwargs):
        if args[:3] == ['git', 'rev-parse', 'HEAD']:
            return 'b' * 40
        return original_run(args, **kwargs)
    monkeypatch.setattr(worker, 'run', stale_run)
    assert worker.readmit_missing_support_source_context(
        {'items': {item['id']: record}}, [item], tmp_path, tmp_path,
        gate, {}, max_active=2
    ) == []
    assert record['reason'].startswith('Missing exact source excerpt')
    assert record.get('source_context_recovery_request_id') is None


def test_p0_source_gap_rejects_disagreeing_original_reason(tmp_path, monkeypatch):
    item, record, gate, _, _ = _gap_recovery_fixture(tmp_path, monkeypatch)
    record['reason'] = 'Missing exact source excerpt for a different subsystem'
    assert worker.readmit_missing_support_source_context(
        {'items': {item['id']: record}}, [item], tmp_path, tmp_path,
        gate, {}, max_active=2
    ) == []
    assert record.get('source_context_recovery_request_id') is None


def _starved_evidence_fixture(tmp_path, monkeypatch, *, upgrade=True, miss_exact_read=True):
    import subprocess
    repo = tmp_path / 'repo'
    repo.mkdir(parents=True)
    paths = {
        'tools/support_repair_host_worker.py':
            'def audit_support_admission():\n    return "persist P0 unmatched"\n'
            'def open_support_issue_records():\n    return {"1301": "open"}\n',
        'tools/tests/test_support_repair_host_worker.py':
            'def test_p0_disposition():\n    assert True\n',
        'tools/engineering_evidence_tools.py':
            'def execute_tools():\n    return "broad_search_first"\n',
        'tools/unrelated.py': 'def unrelated():\n    return True\n',
    }
    for name, content in paths.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Tests')
    git('config', 'user.email', 'test@example.invalid')
    git('add', '.')
    git('commit', '-m', 'old evidence executor')
    old_revision = git('rev-parse', 'HEAD')
    if upgrade:
        tool = repo / 'tools/engineering_evidence_tools.py'
        tool.write_text('def execute_tools():\n    return "explicit_read_first"\n')
        git('add', '.')
        git('commit', '-m', 'new ordered evidence executor')
    current = git('rev-parse', 'HEAD')
    git('update-ref', 'refs/remotes/origin/main', current)

    item = {
        'id': 'SUPPORT-OPS-054', 'priority': 'P0',
        'title': 'GitHub P0 support issue admission reconciliation',
        'evidence': 'Persist dispositions for unmatched P0 SUPPORT issue',
        'acceptance': 'prove issue 1301 diagnosed or explicitly blocked',
    }
    spool = tmp_path / 'spool'
    def put(context, requests):
        rid = worker.queue_reasoning(spool, kind='edit_plan', item=item, context=context)
        target = spool / 'reasoning/responses' / (rid + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            'request_id': rid, 'status':'succeeded', 'kind':'edit_plan',
            'support_item':item['id'],
            'result': {'summary':'additional source required',
                       'edits':[], 'blocked_reason':None,
                       'evidence_requests':requests},
        }))
        return rid
    first = put(
        {'source_excerpts':[{'path':'tools/support_repair_host_worker.py','content':'old'}]},
        [{'tool':'read_source', 'path':'tools/support_repair_host_worker.py', 'query':None},
         {'tool':'search_source','query':'audit_support_admission open_support_issue_records','path':None}],
    )
    second = put(
        {'previous_reasoning_request_id':first,
         'source_excerpts':[{'path':('tools/unrelated.py' if miss_exact_read
                                   else 'tools/support_repair_host_worker.py'),
                             'content':'unrelated broad search'}]},
        [{'tool':'search_source','query':'open_support_issue_records worker admission','path':None}],
    )
    third = put(
        {'previous_reasoning_request_id':second,
         'source_excerpts':[{'path':'tools/unrelated.py','content':'unrelated broad search'}]},
        [{'tool':'read_source','query':None,'path':'tools/support_repair_host_worker.py'}],
    )
    branch = worker.branch_name(item['id']) + '-evidence-' + third[:12]
    git('checkout', '-b', branch)
    monkeypatch.setattr(worker, 'ensure_worktree',
                        lambda source, identity, requested: repo)
    record = {
        'phase':'blocked',
        'reason':'EvidenceToolError: source evidence turn budget exhausted',
        'reasoning_request_id':third,
        'branch':'repair/support-ops-054-context-original',
        'evidence_turn_count':2,
        'evidence_source_revision':old_revision,
        'self_recovery_attempts':2,
    }
    class AllowGate:
        def path_denial_reason(self, path, policy):
            return None
    return repo, spool, item, record, AllowGate(), first, third


def test_starved_exact_read_recovers_once_on_real_new_executor_revision(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last = _starved_evidence_fixture(
        tmp_path, monkeypatch)
    state = {'items':{item['id']:record}}
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        state,[item],repo,spool,gate,{},max_active=2) == [item['id']]
    assert record['phase'] == 'implementing'
    assert record['evidence_turn_count'] == 2
    assert record['self_recovery_attempts'] == 2
    assert record['reasoning_request_id'] != last
    assert record['evidence_upgrade_original_request_id'] == last
    assert record['branch'].endswith('-evidence-' + last[:12])
    assert worker.support_worktree_path(item['id'],record['branch']).name.endswith(
        '-evidence-' + last[:12])
    new = json.loads((spool/'reasoning/requests'/
                      (record['reasoning_request_id']+'.json')).read_text())
    assert new['context']['evidence_starvation_recovery']['retry_limit'] == 1
    assert new['context']['evidence_starvation_recovery']['previous_request_id'] == last
    assert new['context']['source_excerpts'][0]['path'] == 'tools/support_repair_host_worker.py'
    assert 'def audit_support_admission' in new['context']['source_excerpts'][0]['content']
    assert 'tools/tests/test_support_repair_host_worker.py' in [
        entry['path'] for entry in new['context']['source_excerpts']]
    assert worker.reasoning_response(spool,first)['status'] == 'succeeded'
    record['phase']='blocked'
    record['reason']='EvidenceToolError: source evidence turn budget exhausted'
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        state,[item],repo,spool,gate,{},max_active=2) == []


def test_no_worker_revision_upgrade_cannot_readmit_starved_source(tmp_path,monkeypatch):
    repo,spool,item,record,gate,_,_= _starved_evidence_fixture(
        tmp_path,monkeypatch,upgrade=False)
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record}},[item],repo,spool,gate,{},max_active=2)==[]
    assert record['phase']=='blocked'


def test_no_proof_of_a_starved_exact_read_prevents_replay(tmp_path,monkeypatch):
    repo,spool,item,record,gate,_,_= _starved_evidence_fixture(
        tmp_path,monkeypatch,miss_exact_read=False)
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record}},[item],repo,spool,gate,{},max_active=2)==[]
    assert not record.get('evidence_upgrade_recovery_request_id')


def test_starved_recovery_respects_p0_authority_and_worker_capacity(tmp_path,monkeypatch):
    repo,spool,item,record,gate,_,_= _starved_evidence_fixture(tmp_path,monkeypatch)
    item['priority']='P1'
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record}},[item],repo,spool,gate,{},max_active=2)==[]
    item['priority']='P0'
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record,'SUPPORT-OPS-012':{'phase':'diagnosing'}}},
        [item],repo,spool,gate,{},max_active=1)==[]
    assert not record.get('evidence_upgrade_recovery_request_id')


def test_tampered_prior_response_cannot_authorize_context_recovery(tmp_path,monkeypatch):
    repo,spool,item,record,gate,first,last=_starved_evidence_fixture(tmp_path,monkeypatch)
    response_path=spool/'reasoning/responses'/(first+'.json')
    response=json.loads(response_path.read_text())
    response['support_item']='SUPPORT-OPS-999'
    response_path.write_text(json.dumps(response))
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record}},[item],repo,spool,gate,{},max_active=2)==[]
    assert record['phase']=='blocked'


def test_starved_recovery_cannot_take_over_pending_governed_repair_handoff(tmp_path,monkeypatch):
    repo,spool,item,record,gate,_,_=_starved_evidence_fixture(tmp_path,monkeypatch)
    record['recovery_handoff_intake']={'status':'awaiting_governed_repair'}
    assert worker.readmit_verified_evidence_starvation_after_upgrade(
        {'items':{item['id']:record}},[item],repo,spool,gate,{},max_active=2)==[]
    assert record['phase']=='blocked'
    assert record.get('evidence_upgrade_recovery_request_id') is None


def _rollback_paused_recovery_fixture(tmp_path, monkeypatch):
    import subprocess
    repo, spool, item, record, gate, first, last = _starved_evidence_fixture(
        tmp_path, monkeypatch,
    )
    current_sha = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=repo,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    actual_branch = subprocess.run(
        ['git', 'branch', '--show-current'], cwd=repo,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    record.update({
        'phase': 'blocked',
        'reason': 'WorkerError: recovery worktree does not match its pinned branch',
        'branch': actual_branch,
        'evidence_upgrade_source_revision': current_sha,
        'evidence_upgrade_recovery_request_id': last,
        'evidence_upgrade_original_request_id': first,
    })
    new_branch = worker.branch_name(item['id']) + '-context-' + last[:12]
    fresh = tmp_path / new_branch.split('/')[-1]
    original_locator = worker.support_worktree_path
    def isolated_locator(item_id, branch=None):
        if branch == actual_branch:
            return repo
        if branch == new_branch:
            return fresh
        return original_locator(item_id, branch)
    monkeypatch.setattr(worker, 'support_worktree_path', isolated_locator)
    def add_fresh(repo_arg, item_id, branch):
        subprocess.run(
            ['git', 'worktree', 'add', '-b', branch, str(fresh), 'origin/main'],
            cwd=repo, check=True, text=True, capture_output=True,
        )
        return fresh
    monkeypatch.setattr(worker, 'ensure_worktree', add_fresh)
    return repo, spool, item, record, gate, first, last, fresh


def test_verified_rollback_interruption_recovers_once_from_fresh_compatible_branch(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last, fresh = (
        _rollback_paused_recovery_fixture(tmp_path, monkeypatch)
    )
    state = {'items': {item['id']: record}}
    original_branch = record['branch']
    original_turns = record['evidence_turn_count']
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        state, [item], repo, spool, gate, {}, max_active=2,
    ) == [item['id']]
    assert record['phase'] == 'implementing'
    assert record['branch'].endswith('-context-' + last[:12])
    assert record['branch'] != original_branch
    assert record['evidence_turn_count'] == original_turns
    assert record['reasoning_request_id'] != last
    assert record['interrupted_recovery_original_request_id'] == last
    assert worker.support_worktree_path(item['id'], record['branch']).name.endswith(
        '-context-' + last[:12])
    request = json.loads((spool / 'reasoning/requests' /
                          (record['reasoning_request_id'] + '.json')).read_text())
    assert request['context']['verified_rollback_interruption']['previous_request_id'] == last
    assert request['context']['verified_rollback_interruption']['retry_limit'] == 1
    assert request['context']['source_excerpts'][0]['path'] == 'tools/support_repair_host_worker.py'
    assert 'tools/tests/test_support_repair_host_worker.py' in [
        entry['path'] for entry in request['context']['source_excerpts']]
    assert worker.reasoning_response(spool, last)['status'] == 'succeeded'
    assert subprocess.run(['git','status','--porcelain'], cwd=repo,
                          check=True,capture_output=True,text=True).stdout.strip() == ''
    record['phase'] = 'blocked'
    record['reason'] = 'WorkerError: recovery worktree does not match its pinned branch'
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        state, [item], repo, spool, gate, {}, max_active=2,
    ) == []


def test_verified_rollback_interruption_denies_dirty_previous_worktree(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last, fresh = (
        _rollback_paused_recovery_fixture(tmp_path, monkeypatch)
    )
    (repo / 'tools' / 'untracked-dirty.txt').write_text('dirty')
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []
    assert record['phase'] == 'blocked'
    assert not fresh.exists()


def test_verified_rollback_interruption_denies_tampered_response(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last, fresh = (
        _rollback_paused_recovery_fixture(tmp_path, monkeypatch)
    )
    path = spool / 'reasoning/responses' / (last + '.json')
    data = json.loads(path.read_text())
    data['support_item'] = 'SUPPORT-OPS-999'
    path.write_text(json.dumps(data))
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []
    assert record.get('interrupted_recovery_request_id') is None


def test_verified_rollback_interruption_denies_unapproved_or_full_capacity(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last, fresh = (
        _rollback_paused_recovery_fixture(tmp_path, monkeypatch)
    )
    item['priority'] = 'P1'
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []
    item['priority'] = 'P0'
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record, 'SUPPORT-OPS-030': {'phase':'diagnosing'}}},
        [item], repo, spool, gate, {}, max_active=1,
    ) == []
    record['recovery_handoff_intake'] = {'status': 'awaiting_governed_repair'}
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []
    assert record.get('interrupted_recovery_request_id') is None


def test_verified_rollback_interruption_denies_wrong_branch_or_source_revision(tmp_path, monkeypatch):
    repo, spool, item, record, gate, first, last, fresh = (
        _rollback_paused_recovery_fixture(tmp_path, monkeypatch)
    )
    record['branch'] = worker.branch_name(item['id']) + '-context-' + last[:12]
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []
    record['branch'] = worker.branch_name(item['id']) + '-evidence-' + last[:12]
    record['evidence_upgrade_source_revision'] = 'a' * 40
    assert worker.resume_verified_recovery_interrupted_by_rollback(
        {'items': {item['id']: record}}, [item], repo, spool, gate, {}, max_active=2,
    ) == []


def _invalid_symbol_recovery_fixture(tmp_path, monkeypatch, *, upgrade=True):
    import sys
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir()
    src = Path(__file__).resolve().parents[2] / "config/engineering-supervisor-policy.json"
    (repo / "config/engineering-supervisor-policy.json").write_text(src.read_text())
    files = {
        "tools/support_repair_host_worker.py": (
            "def support_id_from_title():\n    return 'source admission logic'\n"
            "def sync_support_lifecycle_notification():\n    return 'source lifecycle logic'\n"
        ),
        "tools/tests/test_support_repair_host_worker.py":
            "def test_support_id():\n    assert True\n",
        "tools/engineering_evidence_tools.py":
            "def old_exact_selector():\n    return 'requires one symbol'\n",
    }
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", ".")
    git("commit", "-m", "old strict exact symbol parser")
    old_sha = git("rev-parse", "HEAD")
    original_id = "b" * 64
    item = {"id": "SUPPORT-OPS-054", "priority": "P0",
            "title": "Support P0 issue admission",
            "evidence": "GitHub support issue missing from registry",
            "acceptance": "issue admitted or explicit verified blocker"}
    old_branch = worker.branch_name(item["id"]) + "-context-" + original_id[:12]
    git("branch", old_branch)
    old_path = tmp_path / "old-verified"
    git("worktree", "add", str(old_path), old_branch)
    if upgrade:
        (repo / "tools/engineering_evidence_tools.py").write_text(
            "def exact_source_symbols():\n    return 'two bounded selectors'\n")
        git("add", ".")
        git("commit", "-m", "bounded source-symbol reader")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", head)
    spool = tmp_path / "spool"
    previous_id = worker.queue_reasoning(spool, kind="edit_plan", item=item, context={
        "verified_rollback_interruption": {
            "previous_request_id": original_id,
            "new_source_revision": old_sha,
            "retry_limit": 1,
        },
        "source_excerpts": [{"path": "tools/tests/test_support_repair_host_worker.py",
                             "content": "previous potentially stale test bytes"}],
    })
    response = spool / "reasoning/responses" / (previous_id + ".json")
    response.parent.mkdir(parents=True, exist_ok=True)
    response.write_text(json.dumps({
        "status": "succeeded", "request_id": previous_id,
        "kind": "edit_plan", "support_item": item["id"],
        "result": {
            "summary": "Need source symbols",
            "blocked_reason": None, "edits": [], "test_paths": [],
            "evidence_requests": [
                {"tool": "read_source", "path": "tools/support_repair_host_worker.py",
                 "query": "support_id_from_title, sync_support_lifecycle_notification, admission state reconciliation, and any "},
                {"tool": "search_source", "path": None,
                 "query": "SUPPORT issue admission persistence"},
            ],
        },
    }))
    record = {
        "phase": "blocked", "reason": "EvidenceToolError: invalid exact source symbol",
        "branch": old_branch, "reasoning_request_id": previous_id,
        "interrupted_recovery_original_request_id": original_id,
        "interrupted_recovery_request_id": previous_id,
        "interrupted_recovery_source_revision": old_sha, "evidence_turn_count": 2,
    }
    new_branch = worker.branch_name(item["id"]) + "-context-" + previous_id[:12]
    fresh = tmp_path / "fresh-verified"
    original_locator = worker.support_worktree_path
    def lookup(item_id, branch=None):
        if branch == old_branch:
            return old_path
        if branch == new_branch:
            return fresh
        return original_locator(item_id, branch)
    def make_worktree(source, item_id, branch):
        assert item_id == item["id"] and branch == new_branch
        if not fresh.is_dir():
            git("worktree", "add", "-b", branch, str(fresh), "origin/main")
        return fresh
    monkeypatch.setattr(worker, "ensure_worktree", make_worktree)
    monkeypatch.setattr(worker, "support_worktree_path", lookup)
    monkeypatch.setitem(worker.sys.modules, worker.__name__, worker)
    class Gate:
        def path_denial_reason(self, path, policy):
            return "denied" if "secrets" in path else None
    return repo, spool, item, record, Gate(), previous_id, old_path, fresh


def test_verified_bad_symbol_readmission_is_once_and_source_pinned(tmp_path, monkeypatch):
    repo, spool, item, record, gate, previous_id, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    state = {"items": {item["id"]: record}}
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=2
    ) == [item["id"]]
    assert record["phase"] == "implementing"
    assert record["evidence_turn_count"] == 3
    assert record["symbol_read_recovery_original_request_id"] == previous_id
    assert record["symbol_read_recovery_request_id"] == record["reasoning_request_id"]
    assert record["interrupted_recovery_request_id"] == previous_id
    req = json.loads((spool / "reasoning/requests" /
                      (record["reasoning_request_id"] + ".json")).read_text())
    assert req["context"]["previous_reasoning_request_id"] == previous_id
    assert req["context"]["pinned_source_revision"] == worker.run(
        ["git", "rev-parse", "origin/main"], cwd=repo)
    assert req["context"]["read_only_tool_receipts"]
    combined = json.dumps(req["context"]["source_excerpts"])
    assert "source admission logic" in combined
    assert "source lifecycle logic" in combined
    assert "previous potentially stale test bytes" not in combined
    assert not worker.run(["git", "status", "--porcelain"], cwd=old)
    assert not worker.run(["git", "status", "--porcelain"], cwd=fresh)
    record.update({"phase": "blocked",
                   "reason": "EvidenceToolError: invalid exact source symbol"})
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=2
    ) == []


def test_invalid_symbol_readmission_denies_modified_response(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    p = spool / "reasoning/responses" / (prior + ".json")
    data = json.loads(p.read_text())
    data["support_item"] = "SUPPORT-OPS-999"
    p.write_text(json.dumps(data))
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert not fresh.exists() and record["phase"] == "blocked"


def test_invalid_symbol_readmission_denies_dirty_old_worktree(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    (old / "tools" / "untracked-secret.txt").write_text("credentials")
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert not fresh.exists()


def test_invalid_symbol_readmission_denies_no_source_upgrade(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch, upgrade=False)
    )
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert not fresh.exists()


def test_invalid_symbol_readmission_honors_capacity_budget_authority(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    state = {"items": {item["id"]: record,
                       "SUPPORT-OPS-100": {"phase": "implementing"}}}
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=1
    ) == []
    record["evidence_turn_count"] = 4
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    record["evidence_turn_count"] = 2
    record["blocker_class"] = "external_authority"
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert not fresh.exists()


def test_invalid_symbol_readmission_denies_command_in_source_selector(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    p = spool / "reasoning/responses" / (prior + ".json")
    data = json.loads(p.read_text())
    data["result"]["evidence_requests"][0]["query"] = (
        "support_id_from_title, sync_support_lifecycle_notification, $(rm -rf /)"
    )
    p.write_text(json.dumps(data))
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert record.get("symbol_read_recovery_request_id") is None


def test_invalid_symbol_readmission_denies_changed_ancestry(tmp_path, monkeypatch):
    repo, spool, item, record, gate, prior, old, fresh = (
        _invalid_symbol_recovery_fixture(tmp_path, monkeypatch)
    )
    record["interrupted_recovery_original_request_id"] = "c" * 64
    assert worker.readmit_verified_malformed_source_symbol_after_upgrade(
        {"items": {item["id"]: record}}, [item], repo, spool, gate, {}, max_active=2
    ) == []
    assert not fresh.exists()


def test_legacy_invalid_symbol_phrase_is_downgraded_to_governed_search(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return worker.run(["git", *args], cwd=repo)
    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (repo / "tools").mkdir()
    (repo / "tools/support_repair_host_worker.py").write_text("def branch_name(x):\n    return x\n")
    (repo / "tools/release_manager_host_runner.py").write_text(
        "CONTROL = 'production-control-state'\n"
        "def load_control_state(root):\n    return {'schema_version':'1.0'}\n"
    )
    git("add", ".")
    git("commit", "-m", "base")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", head)
    item = {"id": "SUPPORT-OPS-061", "priority": "P0",
            "title": "Root-owned release state", "evidence": "readback",
            "acceptance": "safe controller readback"}
    spool = tmp_path / "spool"
    prior = worker.queue_reasoning(spool, kind="edit_plan", item=item, context={})
    response = spool / "reasoning/responses" / (prior + ".json")
    response.parent.mkdir(parents=True, exist_ok=True)
    response.write_text(json.dumps({
        "status": "succeeded", "request_id": prior, "kind": "edit_plan",
        "support_item": item["id"],
        "result": {
            "summary": "Need exact controller source", "blocked_reason": None,
            "edits": [], "test_paths": [],
            "evidence_requests": [{"tool": "read_source",
                "path": "tools/release_manager_host_runner.py",
                "query": "production-control-state"}],
        },
    }))
    record = {"phase": "blocked",
              "reason": "EvidenceToolError: invalid exact source symbol",
              "branch": worker.branch_name(item["id"]),
              "reasoning_request_id": prior}
    state = {"items": {item["id"]: record}}
    fresh = tmp_path / "fresh"
    def make_worktree(source, item_id, branch):
        assert item_id == item["id"]
        if not fresh.is_dir():
            worker.run(["git", "worktree", "add", "-b", branch, str(fresh), "origin/main"], cwd=repo)
        return fresh
    monkeypatch.setattr(worker, "ensure_worktree", make_worktree)
    monkeypatch.setattr(worker, "safe_search", lambda *args, **kwargs: [{
        "path": "tools/release_manager_host_runner.py",
        "content": "CONTROL = production-control-state",
    }])
    evidence_policy = {
        "enabled": True,
        "max_evidence_turns_per_item": 4,
        "max_tool_requests_per_turn": 3,
        "allowed_read_tools": ["search_source", "read_source"],
        "max_sources_per_turn": 3,
        "max_source_chars": 12000,
        "max_total_source_chars": 24000,
        "max_previous_sources": 2,
        "max_receipts": 5,
    }
    monkeypatch.setattr(worker.engineering_evidence_tools, "load_policy", lambda repo: evidence_policy)
    monkeypatch.setitem(sys.modules, worker.__name__, worker)
    class Gate:
        def path_denial_reason(self, path, policy):
            return None
    assert worker.readmit_legacy_malformed_source_selector_as_search(
        state, [item], repo, spool, Gate(), evidence_policy, max_active=2
    ) == [item["id"]]
    assert record["phase"] == "implementing"
    assert record["evidence_turn_count"] == 1
    assert record["legacy_symbol_search_recovery_original_request_id"] == prior
    assert record["reasoning_request_id"] != prior
    next_request = json.loads((spool / "reasoning/requests" /
                               (record["reasoning_request_id"] + ".json")).read_text())
    assert next_request["context"]["previous_reasoning_request_id"] == prior
    assert next_request["context"]["read_only_tool_receipts"]


def test_symbol_blocker_supervisor_classifies_native_verified_path():
    from engineering_supervisor import classify
    kind, next_action = classify(
        "blocked", "EvidenceToolError: invalid exact source symbol",
        lane="support",
    )
    assert kind == "recoverable_source"
    assert next_action == "native_worker_verify_symbol_parser_upgrade_or_escalate"


def test_support_listing_rechecks_transient_duplicate_number_without_dropping_issue(monkeypatch, tmp_path):
    rows = [
        {'number': 1344, 'title': 'SUPPORT-AUTO-0E1A433B5B0C - self-heal alert'},
        {'number': 1301, 'title': 'P0 SUPPORT-OPS-053: watchdog'},
    ]
    batches = iter([rows + [dict(rows[0])], list(reversed(rows)), rows])
    calls = []

    def fake_gh(args, *, cwd):
        calls.append(args)
        assert args[args.index('--search') + 1] == 'SUPPORT- in:title sort:created-asc'
        return next(batches)

    monkeypatch.setattr(worker, 'gh_json', fake_gh)
    inventory = worker.open_support_issue_records(tmp_path)
    assert len(calls) == 3
    assert inventory['SUPPORT-AUTO-0E1A433B5B0C']['issue_numbers'] == [1344]
    assert inventory['SUPPORT-AUTO-0E1A433B5B0C']['issue_count'] == 1
    assert inventory['SUPPORT-OPS-053']['issue_numbers'] == [1301]
    assert inventory['SUPPORT-OPS-053']['priority'] == 'P0'


def test_support_listing_healthy_snapshot_requires_only_one_read(monkeypatch, tmp_path):
    calls = []
    def fake_gh(args, *, cwd):
        calls.append(args)
        return [{'number': 1, 'title': 'SUPPORT-OPS-001: valid'}]
    monkeypatch.setattr(worker, 'gh_json', fake_gh)
    assert worker.open_support_issue_ids(tmp_path) == {'SUPPORT-OPS-001'}
    assert len(calls) == 1


def test_support_listing_persistent_duplicate_number_fails_closed(monkeypatch, tmp_path):
    import pytest
    record = {'number': 1344, 'title': 'SUPPORT-AUTO-0E1A433B5B0C - self-heal alert'}
    calls = []
    def fake_gh(args, *, cwd):
        calls.append(args)
        return [dict(record), dict(record)]
    monkeypatch.setattr(worker, 'gh_json', fake_gh)
    with pytest.raises(worker.WorkerError, match='number missing or repeated'):
        worker.open_support_issue_records(tmp_path)
    assert len(calls) == 2


def test_support_listing_recheck_must_confirm_same_full_identity_set(monkeypatch, tmp_path):
    import pytest
    a = {'number': 1344, 'title': 'SUPPORT-AUTO-0E1A433B5B0C - alert'}
    b = {'number': 1301, 'title': 'P0 SUPPORT-OPS-053: watchdog'}
    c = {'number': 1302, 'title': 'SUPPORT-OPS-054: admission'}
    batches = iter([[a, b, dict(a)], [a, b], [a, c]])
    calls = []
    def fake_gh(args, *, cwd):
        calls.append(args)
        return next(batches)
    monkeypatch.setattr(worker, 'gh_json', fake_gh)
    with pytest.raises(worker.WorkerError, match='inconsistent after bounded recheck'):
        worker.open_support_issue_records(tmp_path)
    assert len(calls) == 3


def test_support_listing_invalid_metadata_never_bypasses_authoritative_validation(monkeypatch, tmp_path):
    import pytest
    for invalid in (
        None,
        [{'number': True, 'title': 'SUPPORT-OPS-053: invalid bool'}],
        [{'number': 3, 'title': None}],
        [{'number': 3, 'title': 'SUPPORT-OPS-053: a'}, {'number': 3, 'title': 'SUPPORT-OPS-054: b'}],
    ):
        calls = []
        def fake_gh(args, *, cwd):
            calls.append(args)
            return invalid
        monkeypatch.setattr(worker, 'gh_json', fake_gh)
        with pytest.raises(worker.WorkerError):
            worker.open_support_issue_records(tmp_path)
        assert len(calls) == 1


def test_github_issue_identity_inventory_preserves_collisions(monkeypatch, tmp_path):
    records = [
        {'number': 1301, 'title': 'P0 SUPPORT-OPS-053: current watchdog'},
        {'number': 1102, 'title': 'SUPPORT-OPS-053: old controller bootstrap'},
        {'number': 1099, 'title': 'SUPPORT-OPS-053: old release bridge'},
        {'number': 1336, 'title': 'SUPPORT-AUTO-01215564E143 - alert'},
        {'number': 881, 'title': 'SUPPORT-AUTO-01215564E143 - alert'},
        {'number': 1095, 'title': 'SUPPORT-OPS-052: independent issue'},
    ]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: records)
    found = worker.open_support_issue_records(tmp_path)
    assert found['SUPPORT-OPS-053']['issue_numbers'] == [1099, 1102, 1301]
    assert found['SUPPORT-OPS-053']['identity_conflict'] is True
    assert found['SUPPORT-OPS-053']['priority'] == 'P0'
    assert found['SUPPORT-AUTO-01215564E143']['issue_numbers'] == [881, 1336]
    assert found['SUPPORT-AUTO-01215564E143']['identity_conflict'] is False
    assert found['SUPPORT-AUTO-01215564E143']['duplicate_issue_records'] is True
    assert found['SUPPORT-OPS-052']['identity_conflict'] is False


def test_issue_identity_conflict_blocks_unsafe_admission_and_is_audited(tmp_path):
    issues = {
        'SUPPORT-OPS-053': {'title': 'P0 SUPPORT-OPS-053', 'priority': 'P0',
                            'issue_numbers': [1102, 1301], 'issue_count': 2,
                            'identity_conflict': True, 'duplicate_issue_records': True},
        'SUPPORT-AUTO-01215564E143': {'title': 'SUPPORT-AUTO alert', 'priority': 'unknown',
                                       'issue_numbers': [881, 1336], 'issue_count': 2,
                                       'identity_conflict': False, 'duplicate_issue_records': True},
        'SUPPORT-OPS-052': {'title': 'SUPPORT-OPS-052', 'priority': 'unknown',
                            'issue_numbers': [1095], 'issue_count': 1,
                            'identity_conflict': False, 'duplicate_issue_records': False},
    }
    support = [{'id': 'SUPPORT-OPS-053', 'priority': 'P0'},
               {'id': 'SUPPORT-AUTO-01215564E143', 'priority': 'P0'},
               {'id': 'SUPPORT-OPS-052', 'priority': 'P0'}]
    state = {}
    missing = worker.audit_support_admission(issues, support, state, event_root=tmp_path)
    assert missing == ['SUPPORT-OPS-053']
    audit = state['admission_audit']
    assert audit['status'] == 'degraded'
    assert audit['open_issue_count'] == 5
    assert audit['logical_work_id_count'] == 3
    assert audit['identity_conflicts'] == {'SUPPORT-OPS-053': [1102, 1301]}
    assert len(audit['duplicate_issue_records']) == 2
    admissible = {key for key, record in issues.items() if not record.get('identity_conflict')}
    assert [item['id'] for item in worker.eligible_support_items(support, admissible)] == [
        'SUPPORT-AUTO-01215564E143', 'SUPPORT-OPS-052']
    events = [worker.json.loads(path.read_text()) for path in tmp_path.glob('*.json')]
    assert len(events) == 2
    assert any(event['work_id'] == 'SUPPORT-OPS-053' for event in events)
    assert any(event['work_id'] == 'SUPPORT-AUTO-IDENTITY-AUDIT' for event in events)
    worker.audit_support_admission(issues, support, state, event_root=tmp_path)
    assert len(list(tmp_path.glob('*.json'))) == 2


def test_manual_identity_collision_never_closes_arbitrary_github_issue(monkeypatch, tmp_path):
    import pytest
    issues = [
        {'number': 1301, 'title': 'P0 SUPPORT-OPS-053: current watchdog'},
        {'number': 1102, 'title': 'SUPPORT-OPS-053: older controller'},
    ]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: issues)
    monkeypatch.setattr(worker, 'run', lambda *args, **kwargs: pytest.fail('unexpected GitHub write'))
    with pytest.raises(worker.WorkerError, match='ambiguous GitHub issue identity'):
        worker.close_support_issue(tmp_path, 'SUPPORT-OPS-053', '0' * 40)


def test_unique_issue_closure_uses_exact_id_not_partial_prefix(monkeypatch, tmp_path):
    issues = [
        {'number': 1, 'title': 'SUPPORT-OPS-0530: different issue'},
        {'number': 2, 'title': 'SUPPORT-OPS-053: exact issue'},
    ]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: issues)
    calls = []
    monkeypatch.setattr(worker, 'run', lambda argv, **kwargs: calls.append(argv))
    worker.close_support_issue(tmp_path, 'SUPPORT-OPS-053', '0' * 40)
    assert len(calls) == 1
    assert calls[0][:4] == ['gh', 'issue', 'close', '2']


def test_github_issue_inventory_rejects_duplicate_numeric_identity(monkeypatch, tmp_path):
    import pytest
    issues = [
        {'number': 1301, 'title': 'SUPPORT-OPS-053: first'},
        {'number': 1301, 'title': 'SUPPORT-OPS-054: second'},
    ]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: issues)
    with pytest.raises(worker.WorkerError, match='number missing or repeated'):
        worker.open_support_issue_records(tmp_path)


def test_open_issue_id_helper_excludes_ambiguous_manual_id(monkeypatch, tmp_path):
    records = [
        {'number': 1102, 'title': 'SUPPORT-OPS-053: previous controller'},
        {'number': 1301, 'title': 'P0 SUPPORT-OPS-053: current watchdog'},
        {'number': 881, 'title': 'SUPPORT-AUTO-01215564E143 - incident'},
        {'number': 1336, 'title': 'SUPPORT-AUTO-01215564E143 - incident'},
        {'number': 1095, 'title': 'SUPPORT-OPS-052: unique incident'},
    ]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: records)
    assert worker.open_support_issue_ids(tmp_path) == {
        'SUPPORT-AUTO-01215564E143', 'SUPPORT-OPS-052'
    }

def test_duplicate_auto_issue_closure_needs_unique_identity(monkeypatch, tmp_path):
    import pytest
    records = [{'number': 881, 'title': 'SUPPORT-AUTO-01215564E143 - alert'},
               {'number': 1336, 'title': 'SUPPORT-AUTO-01215564E143 - alert'}]
    monkeypatch.setattr(worker, 'gh_json', lambda args, cwd: records)
    with pytest.raises(worker.WorkerError, match='ambiguous GitHub issue identity'):
        worker.close_support_issue(tmp_path, 'SUPPORT-AUTO-01215564E143', '0'*40)


def _search_shape_recovery_fixture(tmp_path, monkeypatch, *, upgrade=True):
    import sys
    repo = tmp_path / 'source'
    repo.mkdir()
    p = repo / 'config/engineering-supervisor-policy.json'
    p.parent.mkdir(parents=True)
    p.write_text((MODULE.parents[1] / p.relative_to(repo)).read_text())
    for name, content in {
        'tools/support_repair_host_worker.py': (
            "def support_id_from_title():\n    return 'source admission logic'\n"
            "def release_bridge_summary():\n    return 'source phase summary logic'\n"),
        'tools/engineering_evidence_tools.py': 'def evidence_reader():\n    return True\n',
        'tools/tests/test_support_repair_host_worker.py': 'def test_summary():\n    assert True\n',
    }.items():
        t = repo / name
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(content)

    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, check=True,
                              text=True, capture_output=True).stdout.strip()

    git('init', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    git('add', '.')
    git('commit', '-m', 'old source search worker')
    old_sha = git('rev-parse', 'HEAD')
    item = {'id': 'SUPPORT-OPS-059', 'priority': 'P0',
            'title': 'TODO release bridge',
            'evidence': 'waiting phases and summary',
            'acceptance': 'phase preservation with proof'}
    old_branch = worker.branch_name(item['id'])
    git('branch', old_branch)
    original = tmp_path / 'original'
    git('worktree', 'add', str(original), old_branch)
    if upgrade:
        updated = repo / 'tools/support_repair_host_worker.py'
        updated.write_text(updated.read_text() + '\ndef verified_shape_upgrade():\n    return True\n')
    else:
        updated = repo / 'tools/engineering_evidence_tools.py'
        updated.write_text(updated.read_text() + '\ndef unrelated_upgrade():\n    return True\n')
    git('add', '.')
    git('commit', '-m', 'one source upgrade')
    git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
    spool = tmp_path / 'spool'
    ancestor_id = worker.queue_reasoning(spool, kind='edit_plan', item=item,
                                        context={'source_excerpts': []})
    responses = spool / 'reasoning/responses'
    responses.mkdir(parents=True, exist_ok=True)
    (responses / (ancestor_id + '.json')).write_text(json.dumps({
        'status': 'succeeded', 'kind': 'edit_plan',
        'support_item': item['id'], 'request_id': ancestor_id,
        'result': {'blocked_reason': None, 'edits': []},
    }))
    previous_id = worker.queue_reasoning(spool, kind='edit_plan', item=item,
        context={'previous_reasoning_request_id': ancestor_id,
                 'pinned_source_revision': old_sha, 'evidence_turn': 1,
                 'source_excerpts': [{'path': 'tools/support_repair_host_worker.py',
                                     'content': 'old source bytes are not authoritative'}]})
    old_response = {
        'status': 'succeeded', 'request_id': previous_id,
        'kind': 'edit_plan', 'support_item': item['id'],
        'result': {
            'blocked_reason': None, 'edits': [], 'test_paths': [],
            'evidence_requests': [
                {'tool': 'search_source', 'query': 'support_id_from_title',
                 'path': 'implementation/orchestrator/dynamic_teams_flow_bridge.py'},
                {'tool': 'search_source', 'query': 'release_bridge_summary',
                 'path': None},
            ],
        },
    }
    (responses / (previous_id + '.json')).write_text(json.dumps(old_response))
    record = {
        'phase': 'blocked',
        'reason': 'EvidenceToolError: invalid source search',
        'branch': old_branch, 'reasoning_request_id': previous_id,
        'evidence_last_source_request': ancestor_id,
        'evidence_source_revision': old_sha,
        'evidence_turn_count': 1,
    }
    fresh = tmp_path / 'fresh'
    new_branch = old_branch + '-context-' + previous_id[:12]
    def worktree_path(item_id, branch=None):
        assert item_id == item['id']
        if branch == old_branch:
            return original
        if branch == new_branch:
            return fresh
        raise AssertionError('unexpected worker source path')
    def ensure(source, item_id, branch):
        assert source == repo and item_id == item['id'] and branch == new_branch
        if not fresh.exists():
            git('worktree', 'add', '-b', branch, str(fresh), 'origin/main')
        return fresh
    monkeypatch.setattr(worker, 'support_worktree_path', worktree_path)
    monkeypatch.setattr(worker, 'ensure_worktree', ensure)
    monkeypatch.setitem(sys.modules, worker.__name__, worker)
    class Gate:
        def path_denial_reason(self, path, policy):
            return 'denied' if 'secrets' in path else None
    return repo, spool, item, record, Gate(), previous_id, old_response, original, fresh


def test_verified_legacy_search_path_recovery_one_time_and_read_only(tmp_path, monkeypatch):
    repo, spool, item, record, gate, old_id, old_response, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch))
    state = {'items': {item['id']: record}}
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=2) == [item['id']]
    assert record['phase'] == 'implementing'
    assert record['evidence_turn_count'] == 2
    assert record['reasoning_request_id'] != old_id
    assert record['search_shape_recovery_original_request_id'] == old_id
    req = json.loads((spool / 'reasoning/requests' /
                      (record['reasoning_request_id'] + '.json')).read_text())
    ctx = req['context']
    assert ctx['verified_search_shape_recovery']['ignored_advisory_path_count'] == 1
    assert ctx['previous_reasoning_request_id'] == old_id
    assert ctx['read_only_tool_receipts']
    assert 'old source bytes are not authoritative' not in json.dumps(ctx['source_excerpts'])
    assert any(x['path'] == 'tools/support_repair_host_worker.py'
               for x in ctx['source_excerpts'])
    assert json.loads((spool / 'reasoning/responses' /
                       (old_id + '.json')).read_text()) == old_response
    record.update({'phase': 'blocked', 'reason': 'EvidenceToolError: invalid source search'})
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=2) == []


def test_verified_search_shape_denies_malicious_query_and_extras(tmp_path, monkeypatch):
    repo, spool, item, record, gate, old, _, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch))
    path = spool / 'reasoning/responses' / (old + '.json')
    for bad_query in ('$(rm -rf /)', 'x' * 101, 'abc\ncommand'):
        result = json.loads(path.read_text())
        result['result']['evidence_requests'][0]['query'] = bad_query
        path.write_text(json.dumps(result))
        assert worker.readmit_verified_legacy_search_shape_after_upgrade(
            {'items': {item['id']: record}},
            [item], repo, spool, gate, {}, max_active=2) == []
    assert not fresh.exists()


def test_verified_search_shape_denies_unauthorized_work_and_missing_source_upgrade(
        tmp_path, monkeypatch):
    repo, spool, item, record, gate, old, _, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch, upgrade=False))
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        {'items': {item['id']: record}}, [item],
        repo, spool, gate, {}, max_active=2) == []
    assert not fresh.exists()


def test_verified_search_shape_denies_exhausted_capacity_and_changed_ancestry(
        tmp_path, monkeypatch):
    repo, spool, item, record, gate, old, _, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch))
    state = {'items': {item['id']: record, 'SUPPORT-OPS-100': {'phase': 'implementing'}}}
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        state, [item], repo, spool, gate, {}, max_active=1) == []
    record['evidence_last_source_request'] = 'e' * 64
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        {'items': {item['id']: record}}, [item],
        repo, spool, gate, {}, max_active=2) == []
    assert not fresh.exists()


def test_source_search_blocker_supervisor_is_recoverable_only_through_worker():
    from engineering_supervisor import classify
    assert classify('blocked', 'EvidenceToolError: invalid source search', lane='support') == (
        'recoverable_source', 'native_worker_verify_search_shape_upgrade_or_escalate')


def test_verified_search_shape_rejects_path_traversal_and_unknown_parameters(
        tmp_path, monkeypatch):
    repo, spool, item, record, gate, old, _, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch))
    path = spool / 'reasoning/responses' / (old + '.json')
    original_response = json.loads(path.read_text())
    for malicious in (
            {'path': '../../private/secrets.txt'},
            {'path': 'tools/source.py', 'shell': 'echo unsafe'},
            {'path': '/etc/passwd'},
    ):
        response = json.loads(json.dumps(original_response))
        response['result']['evidence_requests'][0].update(malicious)
        path.write_text(json.dumps(response))
        assert worker.readmit_verified_legacy_search_shape_after_upgrade(
            {'items': {item['id']: record}}, [item],
            repo, spool, gate, {}, max_active=2) == []
    assert not fresh.exists()
    assert record['phase'] == 'blocked'


def test_verified_search_shape_denies_dirty_original_and_external_authority(
        tmp_path, monkeypatch):
    repo, spool, item, record, gate, old, _, original, fresh = (
        _search_shape_recovery_fixture(tmp_path, monkeypatch))
    record['blocker_class'] = 'external_authority'
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        {'items': {item['id']: record}}, [item],
        repo, spool, gate, {}, max_active=2) == []
    del record['blocker_class']
    (original / 'tools/untracked-secret.txt').write_text('confidential example')
    assert worker.readmit_verified_legacy_search_shape_after_upgrade(
        {'items': {item['id']: record}}, [item],
        repo, spool, gate, {}, max_active=2) == []
    assert not fresh.exists()


def _credit_reload_fixture(tmp_path, *, successful=True, overrides=None):
    """Independent provider credit test is metered, short, and later than failure."""
    import os
    import sqlite3
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    target = {
        'id': 'SUPPORT-OPS-059', 'priority': 'P0',
        'title': 'Release bridge must preserve blocked phases',
        'evidence': 'approved bounded regression',
        'acceptance': 'blocked and acceptance states must be preserved',
    }
    failed = worker.queue_reasoning(
        tmp_path, kind='edit_plan', item=target,
        context={'source_excerpts': ['bounded source evidence']},
    )
    response_path = tmp_path / 'reasoning' / 'responses' / (failed + '.json')
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(json.dumps({
        'status': 'failed', 'request_id': failed,
        'error_type': 'ConnectorTransportError',
        'primary_provider_error_code': 'credit_balance_exhausted',
        'primary_http_status': 429,
        'required_owner_action': 'restore_provider_credits',
        'retryable': False,
        'error': 'Hosted reasoning blocked: credit_balance_exhausted; Owner action: restore_provider_credits',
        'completed_at': (now - timedelta(hours=2)).isoformat(),
        'attempts': 1,
    }))
    ledger = tmp_path / 'usage.sqlite3'
    with sqlite3.connect(ledger) as db:
        db.execute('create table model_usage_entries (entry_id text, payload_json text)')
        if successful:
            proof = {
                'entry_id': 'provider-success-001',
                'provider': 'openai', 'model': 'gpt-5.4-mini',
                'outcome': 'completed',
                'usage_source': 'provider_reported',
                'completed_at': (now - timedelta(minutes=2)).isoformat(),
                'tokens': {'total_tokens': 86},
                'context': {
                    'workflow_id': 'provider-credit-verify',
                    'routing_profile': 'operator-authorized-diagnostic',
                },
            }
            proof.update(overrides or {})
            db.execute(
                'insert into model_usage_entries values (?, ?)',
                (proof['entry_id'], json.dumps(proof)),
            )
        db.commit()
    os.chmod(ledger, 0o600)
    record = {
        'phase': 'blocked',
        'reason': 'edit reasoning failed: Hosted reasoning blocked: credit_balance_exhausted; Owner action: restore_provider_credits',
        'reasoning_request_id': failed,
        'self_recovery_attempts': 2,
    }
    return target, failed, ledger, record


def test_verified_provider_credit_reload_allows_one_bounded_p0_request(tmp_path):
    item, failed, ledger, record = _credit_reload_fixture(tmp_path)
    state = {'items': {item['id']: record}}
    previous = worker.reasoning_response(tmp_path, failed)

    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == [item['id']]
    assert record['phase'] == 'implementing'
    assert record['self_recovery_attempts'] == 2
    assert record['provider_credit_original_failure_id'] == failed
    assert record['provider_credit_receipt_id'] == 'provider-success-001'
    new_id = record['reasoning_request_id']
    assert new_id != failed
    new_request = json.loads((tmp_path / 'reasoning' / 'requests' / (new_id + '.json')).read_text())
    assert new_request['context']['verified_credit_recovery'] == {
        'failed_request_id': failed,
        'metered_receipt_id': 'provider-success-001',
        'provider_model': 'gpt-5.4-mini',
        'verified_at': new_request['context']['verified_credit_recovery']['verified_at'],
        'retry_limit': 1,
    }
    assert worker.reasoning_response(tmp_path, failed) == previous
    # Repeated cadence and another 429 must not replay original credit failures.
    record['phase'] = 'blocked'
    record['reason'] = 'edit reasoning failed: Hosted reasoning blocked: credit_balance_exhausted'
    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == []


def test_credit_reload_requires_fresh_metered_provider_receipt_and_exact_failure(tmp_path):
    from datetime import datetime, timedelta, timezone
    wrong = [
        {'provider': 'other-provider'},
        {'outcome': 'failed'},
        {'usage_source': 'unknown'},
        {'tokens': {'total_tokens': 0}},
        {'context': {'workflow_id': 'unattributed-runtime', 'routing_profile': 'operator-authorized-diagnostic'}},
        {'completed_at': (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()},
    ]
    for i, overrides in enumerate(wrong):
        root = tmp_path / str(i)
        item, failed, ledger, record = _credit_reload_fixture(root, overrides=overrides)
        state = {'items': {item['id']: record}}
        assert worker.readmit_after_verified_credit_replenishment(
            state, [item], root, max_active=1, usage_ledger_path=ledger
        ) == []
        assert record['phase'] == 'blocked'
        assert record['reasoning_request_id'] == failed

    for i, field, value in [
        (1, 'primary_provider_error_code', 'insufficient_quota'),
        (2, 'primary_http_status', 400),
        (3, 'required_owner_action', 'unknown'),
        (4, 'retryable', True),
    ]:
        root = tmp_path / ('response-' + str(i))
        item, failed, ledger, record = _credit_reload_fixture(root)
        response_path = root / 'reasoning' / 'responses' / (failed + '.json')
        response = json.loads(response_path.read_text())
        response[field] = value
        response_path.write_text(json.dumps(response))
        assert worker.readmit_after_verified_credit_replenishment(
            {'items': {item['id']: record}}, [item], root,
            max_active=1, usage_ledger_path=ledger
        ) == []


def test_credit_reload_preserves_authority_handoff_and_engineering_capacity(tmp_path):
    item, _, ledger, record = _credit_reload_fixture(tmp_path)
    item['priority'] = 'P1'
    state = {'items': {item['id']: record}}
    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == []

    item['priority'] = 'P0'
    record['recovery_handoff_intake'] = {'status': 'awaiting_governed_repair'}
    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == []
    del record['recovery_handoff_intake']
    state['items']['SUPPORT-OPS-OTHER'] = {'phase': 'implementing'}
    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == []

    state['items'].pop('SUPPORT-OPS-OTHER')
    ledger.unlink()
    assert worker.readmit_after_verified_credit_replenishment(
        state, [item], tmp_path, max_active=1, usage_ledger_path=ledger
    ) == []


def _stale_clean_worktree_recovery_case(tmp_path, monkeypatch):
    """Exercise the recovery contract without touching a real repository or provider."""
    # Patch the exact module instance imported by this worker.
    evidence = worker.engineering_evidence_tools

    item_id = 'SUPPORT-OPS-100'
    item = {'id': item_id, 'priority': 'P0', 'title': 'Bounded source recovery',
            'evidence': 'Old source is stale', 'acceptance': 'A current-source proposal'}
    raw = {'kind': 'edit_plan', 'support_item': item_id, 'title': item['title'],
           'evidence': item['evidence'], 'acceptance': item['acceptance'],
           'context': {'source_excerpts': [{'path': 'tools/stale.py', 'content': 'old'}]}}
    original_id = worker.request_id(raw)
    raw['request_id'] = original_id
    spool = tmp_path / 'spool'
    request_dir = spool / 'reasoning' / 'requests'
    response_dir = spool / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    (request_dir / (original_id + '.json')).write_text(worker.json.dumps(raw))
    (response_dir / (original_id + '.json')).write_text(worker.json.dumps({
        'status': 'succeeded', 'request_id': original_id,
        'kind': 'edit_plan', 'support_item': item_id,
        'result': {'summary': 'Source changed', 'edits': [], 'test_paths': [],
                   'blocked_reason': None,
                   'evidence_requests': [{'tool': 'search_source',
                                          'path': None, 'query': 'bounded_repair'}]},
    }))
    old_sha, main_sha = 'a' * 40, 'b' * 40
    old_branch = worker.branch_name(item_id) + '-context-' + 'e' * 12
    old_tree, fresh_tree = tmp_path / 'old', tmp_path / 'current'
    old_tree.mkdir()
    fresh_tree.mkdir()
    repo = tmp_path / 'repo'
    repo.mkdir()
    state = {'items': {item_id: {
        'phase': 'blocked',
        'reason': 'EvidenceToolError: stale worktree requires governed clean-source recovery',
        'branch': old_branch,
        'reasoning_request_id': original_id,
        'evidence_source_revision': old_sha,
        'evidence_turn_count': 2,
        'evidence_last_source_request': 'previous-read-only-turn',
    }}}
    switches = {'dirty': False, 'ancestor': True}
    calls = []

    def fake_run(args, *, cwd=None, **_kw):
        args = list(args)
        if args == ['git', 'branch', '--show-current']:
            return old_branch if cwd == old_tree else (
                worker.branch_name(item_id) + '-context-' + original_id[:12]
                if cwd == fresh_tree else '')
        if args == ['git', 'status', '--porcelain', '--untracked-files=all']:
            return ' M tools/local.py' if cwd == old_tree and switches['dirty'] else ''
        if args == ['git', 'rev-parse', 'HEAD']:
            return old_sha if cwd == old_tree else main_sha
        if args == ['git', 'rev-parse', 'origin/main']:
            return main_sha
        if args == ['git', 'fetch', '--no-tags', 'origin', 'main']:
            return ''
        if args == ['git', 'merge-base', '--is-ancestor', old_sha, main_sha]:
            if not switches['ancestor']:
                raise worker.WorkerError('old branch contains unmerged work')
            return ''
        raise AssertionError(f'unexpected git operation {args}')

    monkeypatch.setattr(worker, 'run', fake_run)
    monkeypatch.setattr(worker, 'support_worktree_path',
                        lambda _item_id, _branch: old_tree)
    monkeypatch.setattr(worker, 'ensure_worktree',
                        lambda _repo, _item_id, _branch: fresh_tree)
    monkeypatch.setattr(evidence, 'load_policy',
                        lambda _repo: {'max_tool_requests_per_turn': 2})
    monkeypatch.setattr(evidence, 'execute_tools',
                        lambda **kw: (
                            [{'path': 'tools/current.py', 'content': 'def repaired(): pass'}],
                            [{'tool': 'search_source', 'path': 'tools/current.py',
                              'sha256': 'c' * 64}],
                        ))

    def queue(spool, *, kind, item, context):
        calls.append((kind, item, context))
        return 'd' * 64
    monkeypatch.setattr(worker, 'queue_reasoning', queue)
    return (state, [item], repo, spool, old_tree, switches, calls, old_sha, main_sha, original_id)


def test_stale_clean_source_recovery_uses_current_branch_and_retains_history(tmp_path, monkeypatch):
    state, eligible, repo, spool, old_tree, switches, calls, old_sha, main_sha, old_id = (
        _stale_clean_worktree_recovery_case(tmp_path, monkeypatch))
    record = state['items']['SUPPORT-OPS-100']
    assert worker.readmit_verified_stale_clean_source(
        state, eligible, repo, spool, object(), {}, max_active=2
    ) == ['SUPPORT-OPS-100']
    assert record['phase'] == 'implementing'
    assert record['reasoning_request_id'] == 'd' * 64
    assert record['stale_source_recovery_original_request_id'] == old_id
    assert record['stale_source_recovery_previous_revision'] == old_sha
    assert record['stale_source_recovery_current_revision'] == main_sha
    assert record['evidence_source_revision'] == main_sha
    assert record['evidence_turn_count'] == 2  # The previous budget is not reset.
    assert len(calls) == 1
    assert calls[0][0] == 'edit_plan'
    new_context = calls[0][2]
    assert new_context['source_excerpts'][0]['path'] == 'tools/current.py'
    assert 'old' not in str(new_context['source_excerpts'])
    assert new_context['stale_clean_source_recovery']['retry_limit'] == 1
    assert (spool / 'reasoning/requests' / (old_id + '.json')).is_file()
    assert old_tree.is_dir()
    assert worker.readmit_verified_stale_clean_source(
        state, eligible, repo, spool, object(), {}, max_active=2
    ) == []
    assert len(calls) == 1


@pytest.mark.parametrize('denial', [
    'dirty_old_worktree', 'not_ancestor', 'already_recovered',
    'existing_pr', 'external_handoff', 'not_p0', 'changed_reason',
    'untrusted_response',
])
def test_stale_clean_source_recovery_refuses_unsafe_or_duplicate_state(
    tmp_path, monkeypatch, denial,
):
    state, eligible, repo, spool, old_tree, switches, calls, old_sha, main_sha, old_id = (
        _stale_clean_worktree_recovery_case(tmp_path, monkeypatch))
    record = state['items']['SUPPORT-OPS-100']
    if denial == 'dirty_old_worktree':
        switches['dirty'] = True
    elif denial == 'not_ancestor':
        switches['ancestor'] = False
    elif denial == 'already_recovered':
        record['stale_source_recovery_request_id'] = 'e' * 64
    elif denial == 'existing_pr':
        record['pr_number'] = 9999
    elif denial == 'external_handoff':
        record['recovery_handoff_intake'] = {'status': 'awaiting_governed_repair'}
    elif denial == 'not_p0':
        eligible[0]['priority'] = 'P1'
    elif denial == 'changed_reason':
        record['reason'] = 'Unrelated blocker'
    elif denial == 'untrusted_response':
        target = spool / 'reasoning/responses' / (old_id + '.json')
        d = worker.json.loads(target.read_text())
        d['result']['edits'] = [{'path': 'tools/unsafe.py'}]
        target.write_text(worker.json.dumps(d))
    assert worker.readmit_verified_stale_clean_source(
        state, eligible, repo, spool, object(), {}, max_active=2
    ) == []
    assert calls == []
    assert record['phase'] == 'blocked'



def test_support_reasoning_owner_action_is_preserved_for_lifecycle_notification():
    response = {
        "error": "HTTP transport failed with status 429",
        "primary_provider_error_code": "subscription_sharing_usage_limit_exceeded",
        "required_owner_action": "review_chatgpt_subscription_usage",
    }
    update = worker.blocked_reasoning_record(
        response, "reasoning request failed: "
    )
    assert update["phase"] == "blocked"
    assert update["notification_class"] == "owner_action_required"
    assert update["owner_action"] == "review_chatgpt_subscription_usage"
    assert update["provider_blocker_code"] == "subscription_sharing_usage_limit_exceeded"


def test_support_reasoning_non_owner_action_does_not_fabricate_notification():
    update = worker.blocked_reasoning_record(
        {"error": "HTTP transport failed"}, "reasoning request failed: "
    )
    assert update["phase"] == "blocked"
    assert "notification_class" not in update
    assert "owner_action" not in update
