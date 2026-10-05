import importlib.util
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


def test_sync_support_lifecycle_writes_start_and_blocker(tmp_path):
    record = {'phase': 'blocked', 'reason': 'controlled blocker'}
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




def test_safe_search_centers_long_file_excerpt_on_match(tmp_path, monkeypatch):
    target = tmp_path / 'implementation' / 'runtime_service' / 'src' / 'jason_runtime' / 'long_module.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('A' * 16000 + '\nself_heal_escalation = True\n' + 'B' * 16000, encoding='utf-8')
    def fake_run(args, **kwargs):
        if args[-1] in {'self_heal_escalation', 'self', 'heal', 'escalation'}:
            return target.relative_to(tmp_path).as_posix()
        return ''
    monkeypatch.setattr(worker, 'run', fake_run)
    excerpts = worker.safe_search(tmp_path, ['self_heal_escalation'], Gate(), {'max_changed_lines': 800, 'max_changed_files': 25})
    assert excerpts
    assert 'self_heal_escalation = True' in excerpts[0]['content']
    assert len(excerpts[0]['content']) <= 14000


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
