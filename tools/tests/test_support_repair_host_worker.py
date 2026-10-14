import importlib.util
import json
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


def _stage_current_self_heal_incident(root: Path, fp: str, family: str, details: dict) -> Path:
    directory = root / 'incidents'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (fp + '.json')
    payload = {
        'schema_version': '2.0',
        'state': 'repair_required',
        'fingerprint': fp,
        'family': family,
        'support_item': 'SUPPORT-AUTO-' + fp[:12].upper(),
        **details,
    }
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _publish_current_self_heal_state(root: Path, specs: list[tuple[str, str]]) -> None:
    directory = root / 'incidents'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'state.json').write_text(json.dumps({
        'schema_version': '2.0',
        'state': 'repair_required',
        'incidents': [
            {'fingerprint': fingerprint, 'family': family}
            for fingerprint, family in specs
        ],
        'incident_paths': [
            str(directory / (fingerprint + '.json'))
            for fingerprint, _ in specs
        ],
    }), encoding='utf-8')


def test_load_self_heal_incidents_returns_repair_required_items(tmp_path):
    root = tmp_path / 'self-heal'
    fp = 'abcdef123456000000000000'
    _stage_current_self_heal_incident(root, fp, 'runtime_health', {
        'priority': 'P1', 'title': 'degraded',
        'evidence': 'failed', 'acceptance': 'restore',
    })
    _publish_current_self_heal_state(root, [(fp, 'runtime_health')])
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
    fp = '123456abcdef000000000000'
    _stage_current_self_heal_incident(root, fp, 'production_convergence', payload)
    _publish_current_self_heal_state(root, [(fp, 'production_convergence')])
    items = worker.load_self_heal_incidents(root)
    assert len(items) == 1
    assert items[0]['priority'] == 'P0'
    assert 'root invariant: runtime = mcp = host = workers' in items[0]['evidence']
    assert 'repair level: L2 bounded_autonomous_repair' in items[0]['evidence']
    assert 'occurrence: 2' in items[0]['evidence']
    assert 'rerun production convergence detector' in items[0]['acceptance']


def test_recovered_github_does_not_admit_legacy_incident_spool(tmp_path):
    root = tmp_path / 'self-heal'
    directory = root / 'incidents'
    directory.mkdir(parents=True)
    for i in range(125):
        (directory / f'legacy-{i}.json').write_text(json.dumps({
            'state': 'repair_required',
            'support_item': f'SUPPORT-AUTO-{i:012X}',
            'priority': 'P1', 'title': 'legacy scan incident',
        }), encoding='utf-8')
    fp1 = 'abc123abc123000000000000'
    fp2 = 'def456def456000000000000'
    _stage_current_self_heal_incident(root, fp1, 'provider_health', {'priority': 'P0'})
    _stage_current_self_heal_incident(root, fp2, 'ticket_admission', {'priority': 'P1'})
    _publish_current_self_heal_state(root, [(fp1, 'provider_health'), (fp2, 'ticket_admission')])
    items = worker.load_self_heal_incidents(root)
    assert {item['id'] for item in items} == {
        'SUPPORT-AUTO-ABC123ABC123', 'SUPPORT-AUTO-DEF456DEF456',
    }
    assert len(list(directory.glob('*.json'))) == 127  # evidence is retained


def test_healthy_watchdog_never_reopens_stale_incidents(tmp_path):
    root = tmp_path / 'self-heal'
    fp = 'aaaabbbbcccc000000000000'
    _stage_current_self_heal_incident(root, fp, 'provider_health', {})
    _publish_current_self_heal_state(root, [(fp, 'provider_health')])
    state = json.loads((root / 'state.json').read_text(encoding='utf-8'))
    state['state'] = 'healthy'
    (root / 'state.json').write_text(json.dumps(state), encoding='utf-8')
    assert worker.load_self_heal_incidents(root) == []


def test_legacy_watchdog_manifest_requires_explicit_migration(tmp_path):
    root = tmp_path / 'self-heal'
    directory = root / 'incidents'
    directory.mkdir(parents=True)
    (directory / 'legacy.json').write_text(
        json.dumps({'state': 'repair_required', 'support_item': 'SUPPORT-AUTO-AAAAAAAAAAAA'}),
        encoding='utf-8',
    )
    (root / 'state.json').write_text(json.dumps({'schema_version': '1.0', 'state': 'repair_required'}))
    assert worker.load_self_heal_incidents(root) == []


def test_self_heal_live_manifest_blocks_untrusted_paths_and_identity_mismatch(tmp_path):
    root = tmp_path / 'self-heal'
    fp = 'abc123abc123000000000000'
    path = _stage_current_self_heal_incident(root, fp, 'provider_health', {})
    _publish_current_self_heal_state(root, [(fp, 'provider_health')])
    state_path = root / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    state['incident_paths'] = [str(tmp_path / 'outside.json')]
    state_path.write_text(json.dumps(state), encoding='utf-8')
    import pytest
    with pytest.raises(worker.WorkerError, match='Unsafe self-heal incident locator'):
        worker.load_self_heal_incidents(root)
    state['incident_paths'] = [str(path)]
    state_path.write_text(json.dumps(state), encoding='utf-8')
    data = json.loads(path.read_text(encoding='utf-8'))
    data['fingerprint'] = 'f' * 24
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(worker.WorkerError, match='evidence mismatch'):
        worker.load_self_heal_incidents(root)


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
    monkeypatch.setattr(worker, 'open_support_issue_ids', lambda _: set())
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
    monkeypatch.setattr(worker, 'open_support_issue_ids', lambda _: set())
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
    monkeypatch.setattr(worker, 'open_support_issue_ids', lambda _: set())
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
