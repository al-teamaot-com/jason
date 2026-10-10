import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'owner_approved_development_worker.py'
SPEC = importlib.util.spec_from_file_location('owner_approved_development_worker', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_lifecycle_sync_suppresses_start_and_recoverable_blocker(tmp_path):
    record = {'phase': 'blocked', 'reason': 'worker can self-heal'}
    item = {'id': 'DEV-42', 'title': 'Teams lifecycle cards'}
    root = tmp_path / 'events'
    module.sync_lifecycle_notification(record, item, event_root=root)
    assert not list(root.glob('*.json'))


def test_lifecycle_sync_emits_only_one_verified_development_completion(tmp_path):
    record = {'phase': 'complete', 'pr_number': 1151}
    item = {'id': 'DEV-1134', 'title': 'NDR evidence pilot'}
    root = tmp_path / 'events'
    module.sync_lifecycle_notification(record, item, event_root=root)
    module.sync_lifecycle_notification(record, item, event_root=root)
    payloads = [module.support.json.loads(p.read_text()) for p in root.glob('*.json')]
    assert len(payloads) == 1
    assert payloads[0]['event_type'] == 'work_completed'
    assert 'production activation is separate' in payloads[0]['summary']


def test_lifecycle_sync_does_not_claim_completion_without_pr(tmp_path):
    record = {'phase': 'complete'}
    module.sync_lifecycle_notification(record, {'id': 'DEV-42', 'title': 'Work'}, event_root=tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_owner_approval_marker_is_exact():
    assert module.APPROVAL.search('- **Autonomous development:** owner-approved')
    assert not module.APPROVAL.search('- **Autonomous development:** approved')
    assert not module.APPROVAL.search('- Autonomous development: owner-approved')


def test_approved_scope_preserves_late_issue_requirements_and_stays_bounded():
    marker = 'BACKUPIQ_ACCEPTANCE_REQUIREMENT'
    body = ('a' * 7000) + marker + ('b' * 30000)
    scope = module.approved_scope({'body': body})
    assert marker in scope
    assert len(scope) == module.APPROVED_BODY_LIMIT


def test_known_development_pr_merged_reconciles_from_any_phase(tmp_path, monkeypatch):
    calls = []

    def fake_pr_view(repo, number):
        calls.append((repo, number))
        return {'mergedAt': '2026-10-07T17:00:00Z'}

    monkeypatch.setattr(module.support, 'pr_view', fake_pr_view)
    record = {'phase': 'ci_repair_needed', 'pr_number': 1070}
    assert module.known_development_pr_is_merged(tmp_path, record)
    assert calls == [(tmp_path, 1070)]
    assert not module.known_development_pr_is_merged(tmp_path, {'phase': 'diagnosing'})


def test_select_items_respects_capacity_and_terminal_state():
    state = {
        'items': {
            'DEV-10': {'phase': 'diagnosing'},
            'DEV-11': {'phase': 'pr_ready'},
        }
    }
    state['items']['DEV-13'] = {'phase': 'waiting_external_dependency'}
    eligible = [
        {'id': 'DEV-10', 'issue_number': 10},
        {'id': 'DEV-11', 'issue_number': 11},
        {'id': 'DEV-12', 'issue_number': 12},
        {'id': 'DEV-13', 'issue_number': 13},
    ]
    assert module.select_items(state, eligible, capacity=0) == ['DEV-10']
    assert module.select_items(state, eligible, capacity=1) == ['DEV-10', 'DEV-12']
def test_existing_active_development_reconciles_when_new_capacity_is_zero():
    state = {'items': {'DEV-10': {'phase': 'diagnosing'}, 'DEV-11': {'phase': 'implementing'}}}
    eligible = [
        {'id': 'DEV-10', 'issue_number': 10},
        {'id': 'DEV-11', 'issue_number': 11},
        {'id': 'DEV-12', 'issue_number': 12},
    ]
    assert module.select_items(state, eligible, capacity=0) == ['DEV-10', 'DEV-11']


def test_removed_approval_stops_nonterminal_work():
    state = {
        'items': {
            'DEV-10': {'phase': 'implementing'},
            'DEV-11': {'phase': 'pr_ready'},
        }
    }
    module.reconcile_removed_approval(state, {'DEV-11'})
    assert state['items']['DEV-10']['phase'] == 'blocked'
    assert 'marker is no longer present' in state['items']['DEV-10']['reason']
    assert state['items']['DEV-11']['phase'] == 'pr_ready'


def test_active_support_count_reduces_development_capacity(tmp_path):
    spool = tmp_path
    module.support.save_state(
        spool / 'state.json',
        {
            'items': {
                'SUPPORT-OPS-1': {'phase': 'implementing'},
                'SUPPORT-OPS-2': {'phase': 'blocked'},
                'SUPPORT-OPS-3': {'phase': 'identified'},
            }
        },
    )
    assert module.active_support_count(spool) == 1


def test_blocked_marker_excludes_issue():
    body = (
        '- **Autonomous development:** owner-approved\n'
        '- **Status:** blocked\n'
    )
    assert module.APPROVAL.search(body)
    assert module.BLOCKED.search(body)


def test_source_context_blocker_detects_missing_excerpt_context():
    assert module.source_context_blocker(
        'The supplied excerpts do not expose enough registry persistence and would require unseen code.'
    )
    assert module.source_context_blocker(
        'Cannot form a complete, exact replacement without enough surrounding file context.'
    )
    assert module.source_context_blocker(
        'The provided excerpts are insufficient to form exact replacements; the incomplete repository context would require inventing unseen API surface.'
    )
    assert module.source_context_blocker(
        'Blocked: the repository excerpts do not include the specific implementation needed for an exact change.'
    )
    assert not module.source_context_blocker('Owner approval is required for production deployment.')
    assert not module.source_context_blocker('Provider credential is unavailable.')


def test_self_recoverable_blocker_includes_invalid_internal_repair_path():
    assert module.self_recoverable_blocker(
        'WorkerError: repair path does not exist: implementation/kernel/capabilities/retirement.py'
    )
    assert not module.self_recoverable_blocker('Provider credential is unavailable.')


def test_context_only_search_plan_with_terms_is_actionable():
    result = {
        'blocked_reason': 'Additional exact repository source is still needed; the provided context is incomplete.',
        'search_terms': ['CapabilityDefinition(', 'class CapabilityDefinition'],
    }
    blocked = str(result.get('blocked_reason') or '').strip()
    terms = [str(value).strip() for value in result.get('search_terms') or [] if str(value).strip()]
    assert terms
    assert module.source_context_blocker(blocked)
    assert not (blocked and (not terms or not module.source_context_blocker(blocked)))


def test_authority_search_plan_blocker_remains_terminal_even_with_terms():
    blocked = 'Owner approval is required before protected production deployment.'
    terms = ['production gate']
    assert not module.source_context_blocker(blocked)
    assert blocked and (not terms or not module.source_context_blocker(blocked))


def test_recorded_context_expansion_consumes_useful_search_terms_despite_wording():
    record = {'context_expansion_attempts': 2}
    blocked = 'Additional exact repository source is still needed; without that surrounding code the implementation area remains ambiguous.'
    terms = ['CapabilityDefinition(', 'retirement_state']
    expansion_search = int(record.get('context_expansion_attempts', 0)) > 0
    terminal = bool(blocked) and (
        not terms or (not expansion_search and not module.source_context_blocker(blocked))
    )
    assert expansion_search
    assert not terminal


def test_initial_non_context_blocker_with_terms_stays_terminal():
    record = {'context_expansion_attempts': 0}
    blocked = 'Owner approval is required before production deployment.'
    terms = ['production gate']
    expansion_search = int(record.get('context_expansion_attempts', 0)) > 0
    terminal = bool(blocked) and (
        not terms or (not expansion_search and not module.source_context_blocker(blocked))
    )
    assert terminal


def test_source_history_is_sticky_across_context_expansion():
    record = {
        'source_paths': [
            'implementation/kernel/capabilities/repository.py',
            'implementation/kernel/capabilities/service.py',
        ]
    }
    history = [
        str(value).strip()
        for value in list(record.get('source_history') or record.get('source_paths') or [])
        if str(value).strip()
    ]
    new_paths = [
        'implementation/kernel/system_registry/contracts.py',
        'implementation/kernel/capabilities/service.py',
    ]
    for path in new_paths:
        if path not in history:
            history.append(path)
    assert history == [
        'implementation/kernel/capabilities/repository.py',
        'implementation/kernel/capabilities/service.py',
        'implementation/kernel/system_registry/contracts.py',
    ]


def test_owner_approved_pr_body_enables_unattended_source_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(module, 'integration_coordination', lambda repo, changed: [])
    monkeypatch.setattr(module.support, 'changed_files', lambda worktree: ['tools/example.py'])
    monkeypatch.setattr(module.support, 'run', lambda *args, **kwargs: 'a' * 40)
    body = module.pr_body(
        tmp_path,
        {
            'issue_number': 42,
            'title': 'Approved thing',
            'approval_source': 'https://example.invalid/issues/42',
            'approved_by': 'owner',
        },
        tmp_path,
        ['tools/tests/test_example.py'],
    )
    assert '- Integration automation: enabled' in body
    assert 'exact merged main SHA' in body
    assert 'Production deployment authority: none' in body


def test_self_recoverable_blocker_is_narrow():
    assert module.self_recoverable_blocker(
        'The supplied excerpts do not expose enough exact source context.'
    )
    assert module.self_recoverable_blocker('development reasoning failed: HTTP transport failed')
    assert not module.self_recoverable_blocker('Owner approval required for a new provider permission.')
    assert not module.self_recoverable_blocker('Microsoft admin consent is required.')


def test_recycle_self_recoverable_blockers_preserves_real_external_blockers():
    state = {
        'items': {
            'DEV-1': {
                'phase': 'blocked',
                'reason': 'The supplied excerpts are insufficient exact source context.',
            },
            'DEV-2': {
                'phase': 'blocked',
                'reason': 'Microsoft admin consent is required.',
            },
        }
    }
    module.recycle_self_recoverable_blockers(state, {'DEV-1', 'DEV-2'})
    assert state['items']['DEV-1']['phase'] == 'diagnosing'
    assert state['items']['DEV-1']['self_recovery_attempts'] == 1
    assert state['items']['DEV-2']['phase'] == 'blocked'


def test_owner_approved_issue_discovery_is_not_limited_to_newest_100(monkeypatch, tmp_path):
    calls = []

    def fake_gh_json(args, *, cwd):
        calls.append(list(args))
        if args[:2] == ['repo', 'view']:
            return {'nameWithOwner': 'example/jason'}
        if args[:3] == ['issue', 'list', '--state']:
            return [
                {
                    'number': 866,
                    'title': 'Older approved item',
                    'body': '- **Autonomous development:** owner-approved',
                    'url': 'https://example.invalid/issues/866',
                    'labels': [],
                    'updatedAt': '2026-10-03T12:13:30Z',
                }
            ]
        if args[:2] == ['api', 'repos/example/jason/issues/866']:
            return {'author_association': 'OWNER', 'user': {'login': 'owner'}}
        raise AssertionError(args)

    monkeypatch.setattr(module.support, 'gh_json', fake_gh_json)
    items = module.owner_approved_issues(tmp_path)

    issue_list_call = next(call for call in calls if call[:2] == ['issue', 'list'])
    limit_index = issue_list_call.index('--limit') + 1
    assert int(issue_list_call[limit_index]) >= 1000
    assert [item['issue_number'] for item in items] == [866]


def test_pr_preflight_rejects_missing_coordination_acknowledgement():
    body = """## Integration coordination

- Current-main reconciliation performed: yes
- Integration coordination: #123
- Integration automation: enabled
- Production deployment authority: none

## Documentation impact

- [ ] Documentation updated
- [x] No documentation impact

No-documentation-impact reason: No durable documentation contract changed.
"""
    try:
        module.validate_pr_preflight(body, [123, 456])
    except Exception as exc:
        assert "#456" in str(exc)
    else:
        raise AssertionError("preflight should reject missing overlap acknowledgement")


def test_pr_preflight_accepts_required_contract():
    body = """## Integration coordination

- Current-main reconciliation performed: yes
- Integration coordination: #123 #456
- Integration automation: enabled
- Production deployment authority: none

## Documentation impact

- [ ] Documentation updated
- [x] No documentation impact

No-documentation-impact reason: No durable documentation contract changed.
"""
    module.validate_pr_preflight(body, [123, 456])


def test_ci_failure_classifier_separates_process_from_code():
    assert module.support.classify_ci_failure(
        "DocumentationImpactError: PR body is missing required '## Documentation impact' section"
    ) == "pr_governance_metadata_defect"
    assert module.support.classify_ci_failure(
        "change-integration: FAIL\n- Active implementation overlap with PR #1022"
    ) == "integration_collision"
    assert module.support.classify_ci_failure(
        "ModuleNotFoundError: No module named 'pytest'"
    ) == "dependency_environment_defect"
    assert module.support.classify_ci_failure(
        "FAILED tests/test_example.py::test_behavior - AssertionError"
    ) == "code_or_test_defect"


def test_exhausted_self_recovery_records_action_without_restarting():
    state = {'items': {'DEV-950': {
        'phase': 'blocked',
        'reason': 'The supplied excerpts are insufficient',
        'self_recovery_attempts': 2,
    }}}
    module.recycle_self_recoverable_blockers(state, {'DEV-950'})
    record = state['items']['DEV-950']
    assert record['phase'] == 'blocked'
    assert record['self_recovery_attempts'] == 2
    assert record['blocker_class'] == 'internal_retry_exhausted'
    assert 'engineering repair' in record['recovery_next_action']
    timestamp = record['recovery_exhausted_at']
    module.recycle_self_recoverable_blockers(state, {'DEV-950'})
    assert record['recovery_exhausted_at'] == timestamp

def test_external_blocker_never_recycles_or_claims_exhaustion():
    state = {'items': {'DEV-952': {
        'phase': 'blocked', 'reason': 'Datto API credentials not available',
        'self_recovery_attempts': 2,
    }}}
    module.recycle_self_recoverable_blockers(state, {'DEV-952'})
    assert state['items']['DEV-952']['phase'] == 'blocked'
    assert 'blocker_class' not in state['items']['DEV-952']

def test_unapproved_blocker_never_recycles():
    state = {'items': {'DEV-950': {
        'phase': 'blocked', 'reason': 'The supplied excerpts are insufficient',
        'self_recovery_attempts': 1,
    }}}
    module.recycle_self_recoverable_blockers(state, set())
    assert state['items']['DEV-950']['self_recovery_attempts'] == 1
    assert state['items']['DEV-950']['phase'] == 'blocked'


def test_exhausted_recovery_queues_one_diagnostic_handoff(tmp_path):
    state = {'items': {'DEV-950': {
        'phase': 'blocked', 'blocker_class': 'internal_retry_exhausted',
        'reason': 'supplied excerpts insufficient', 'self_recovery_attempts': 2,
    }}}
    eligible = [{'id': 'DEV-950', 'issue_number': 950, 'title': 'Entra reads',
                 'evidence': 'missing registry', 'acceptance': 'synthetic regression'}]
    module.queue_exhausted_recovery_diagnostics(state, eligible, tmp_path)
    record = state['items']['DEV-950']
    rid = record['recovery_diagnostic_request_id']
    payload = module.support.json.loads((tmp_path / 'reasoning' / 'requests' / f'{rid}.json').read_text())
    assert payload['context']['work_class'] == 'development_retry_exhaustion_diagnostics'
    assert 'Do not resume' in payload['context']['instruction']
    module.queue_exhausted_recovery_diagnostics(state, eligible, tmp_path)
    assert len(list((tmp_path / 'reasoning' / 'requests').glob('*.json'))) == 1
    assert record['phase'] == 'blocked'

def test_exhausted_recovery_diagnostic_respects_approval_and_external_blockers(tmp_path):
    state = {'items': {
        'DEV-950': {'phase': 'blocked', 'blocker_class': 'internal_retry_exhausted'},
        'DEV-952': {'phase': 'blocked', 'reason': 'external credentials'},
    }}
    eligible = [{'id': 'DEV-952', 'issue_number': 952, 'title': 'Backup',
                 'evidence': '', 'acceptance': ''}]
    module.queue_exhausted_recovery_diagnostics(state, eligible, tmp_path)
    assert not (tmp_path / 'reasoning' / 'requests').exists()


def test_reconcile_exhausted_diagnostic_success_does_not_resume(tmp_path):
    state = {'items': {'DEV-950': {'phase': 'blocked',
      'blocker_class': 'internal_retry_exhausted', 'recovery_diagnostic_request_id': 'req123'}}}
    root = tmp_path / 'reasoning' / 'responses'
    root.mkdir(parents=True)
    (root / 'req123.json').write_text(module.support.json.dumps({
        'request_id': 'req123', 'status': 'succeeded',
        'result': {'diagnosis': 'missing exact registry source'}}))
    module.reconcile_exhausted_recovery_diagnostics(state, {'DEV-950'}, tmp_path)
    item = state['items']['DEV-950']
    assert item['phase'] == 'blocked'
    assert item['recovery_diagnostic_summary'] == 'missing exact registry source'
    assert item['recovery_diagnostic_result_status'] == 'succeeded'
    assert 'governed repair' in item['recovery_next_action']
    handoffs = list((tmp_path / 'development-recovery' / 'handoffs').glob('*.json'))
    assert len(handoffs) == 1
    payload = module.support.json.loads(handoffs[0].read_text())
    assert payload['admission_authority'] is False
    assert payload['diagnostic_request_id'] == 'req123'
    first_time = item['recovery_diagnostic_result_at']
    module.reconcile_exhausted_recovery_diagnostics(state, {'DEV-950'}, tmp_path)
    assert item['recovery_diagnostic_result_at'] == first_time
    assert len(list((tmp_path / 'development-recovery' / 'handoffs').glob('*.json'))) == 1

def test_reconcile_exhausted_diagnostic_mismatch_fails_closed(tmp_path):
    state = {'items': {'DEV-950': {'phase': 'blocked',
      'blocker_class': 'internal_retry_exhausted', 'recovery_diagnostic_request_id': 'req123'}}}
    root = tmp_path / 'reasoning' / 'responses'
    root.mkdir(parents=True)
    (root / 'req123.json').write_text(module.support.json.dumps({
        'request_id': 'wrong', 'status': 'succeeded', 'result': {'diagnosis': 'ok'}}))
    module.reconcile_exhausted_recovery_diagnostics(state, {'DEV-950'}, tmp_path)
    assert state['items']['DEV-950']['recovery_diagnostic_result_status'] == 'invalid_request_id'
    assert state['items']['DEV-950']['phase'] == 'blocked'


def test_handoff_intake_requires_matching_identity_and_no_authority(tmp_path):
    root = tmp_path / 'development-recovery' / 'handoffs'
    root.mkdir(parents=True)
    payload = {'schema': 'jason.development-recovery-handoff.v1',
       'source_item': 'DEV-950', 'diagnostic_request_id': 'req1',
       'admission_authority': False}
    import hashlib
    ident = hashlib.sha256(module.support.json.dumps(payload, sort_keys=True).encode()).hexdigest()
    (root / f'{ident}.json').write_text(module.support.json.dumps(payload))
    state = {'items': {'DEV-950': {'phase': 'blocked',
       'recovery_handoff_id': ident, 'recovery_diagnostic_request_id': 'req1'}}}
    module.reconcile_recovery_handoff_intake(state, {'DEV-950'}, tmp_path)
    record = state['items']['DEV-950']
    assert record['phase'] == 'blocked'
    assert record['recovery_handoff_intake']['status'] == 'awaiting_governed_repair'
    first = record['recovery_handoff_intake']['observed_at']
    module.reconcile_recovery_handoff_intake(state, {'DEV-950'}, tmp_path)
    assert record['recovery_handoff_intake']['observed_at'] == first
    del record['recovery_handoff_intake']
    payload['admission_authority'] = True
    (root / f'{ident}.json').write_text(module.support.json.dumps(payload))
    module.reconcile_recovery_handoff_intake(state, {'DEV-950'}, tmp_path)
    assert 'recovery_handoff_intake' not in record


def test_tampered_recovery_handoff_is_rejected(tmp_path):
    root = tmp_path / 'development-recovery' / 'handoffs'
    root.mkdir(parents=True)
    ident = 'c' * 64
    payload = {'schema': 'jason.development-recovery-handoff.v1',
               'source_item': 'DEV-950', 'diagnostic_request_id': 'req1',
               'admission_authority': False}
    (root / f'{ident}.json').write_text(module.support.json.dumps(payload))
    state = {'items': {'DEV-950': {'phase': 'blocked',
      'recovery_handoff_id': ident, 'recovery_diagnostic_request_id': 'req1'}}}
    module.reconcile_recovery_handoff_intake(state, {'DEV-950'}, tmp_path)
    assert 'recovery_handoff_intake' not in state['items']['DEV-950']
    assert state['items']['DEV-950']['phase'] == 'blocked'


def test_exhausted_repair_opens_deduplicated_governed_support_item(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(module.support, 'ensure_support_issue', lambda repo, item: seen.append(item))
    state = {'items': {'DEV-950': {'phase': 'blocked', 'issue_number': 950,
      'reason': 'source context missing', 'recovery_handoff_intake': {
        'status': 'awaiting_governed_repair', 'handoff_id': 'a' * 64}}}}
    module.raise_exhausted_repair_support_issues(state, {'DEV-950'}, tmp_path)
    module.raise_exhausted_repair_support_issues(state, {'DEV-950'}, tmp_path)
    assert len(seen) == 1
    assert seen[0]['id'] == 'SUPPORT-DEV-950'
    assert state['items']['DEV-950']['phase'] == 'blocked'

def test_repair_support_intake_never_bypasses_dependencies(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(module.support, 'ensure_support_issue', lambda repo, item: seen.append(item))
    state = {'items': {'DEV-866': {'phase': 'blocked', 'issue_number': 866,
       'recovery_handoff_intake': {'status': 'not_verified', 'handoff_id': 'b' * 64}}}}
    module.raise_exhausted_repair_support_issues(state, {'DEV-866'}, tmp_path)
    assert not seen
    assert state['items']['DEV-866']['phase'] == 'blocked'


def test_exhaustion_to_support_intake_end_to_end_synthetic(monkeypatch, tmp_path):
    item = {'id': 'DEV-950', 'issue_number': 950, 'title': 'Read expansion',
            'evidence': 'missing source', 'acceptance': 'tests prove completeness'}
    state = {'items': {'DEV-950': {'phase': 'blocked', 'issue_number': 950,
      'reason': 'supplied excerpts insufficient', 'self_recovery_attempts': 2}}}
    module.recycle_self_recoverable_blockers(state, {'DEV-950'})
    module.queue_exhausted_recovery_diagnostics(state, [item], tmp_path)
    record = state['items']['DEV-950']
    rid = record['recovery_diagnostic_request_id']
    response_dir = tmp_path / 'reasoning' / 'responses'
    response_dir.mkdir(parents=True)
    (response_dir / f'{rid}.json').write_text(module.support.json.dumps({
        'request_id': rid, 'status': 'succeeded', 'result': {'diagnosis': 'registry missing'}}))
    module.reconcile_exhausted_recovery_diagnostics(state, {'DEV-950'}, tmp_path)
    module.reconcile_recovery_handoff_intake(state, {'DEV-950'}, tmp_path)
    seen = []
    monkeypatch.setattr(module.support, 'ensure_support_issue', lambda repo, issue: seen.append(issue))
    module.raise_exhausted_repair_support_issues(state, {'DEV-950'}, tmp_path)
    module.raise_exhausted_repair_support_issues(state, {'DEV-950'}, tmp_path)
    assert len(seen) == 1
    assert seen[0]['id'] == 'SUPPORT-DEV-950'
    assert record['phase'] == 'blocked'
    assert record['self_recovery_attempts'] == 2
    assert record['recovery_support_issue_raised'] == 'SUPPORT-DEV-950'
    assert record['recovery_handoff_intake']['status'] == 'awaiting_governed_repair'


def test_recovery_readmission_requires_exact_production_sha(monkeypatch, tmp_path):
    sha = 'b' * 40
    state = {'items': {'DEV-950': {'phase': 'blocked', 'issue_number': 950,
        'blocker_class': 'internal_retry_exhausted',
        'recovery_support_issue_raised': 'SUPPORT-DEV-950'}}}
    module.support.save_state(tmp_path / 'state.json', {'items': {
       'SUPPORT-DEV-950': {'phase': 'complete', 'merge_sha': sha,
          'closure_pr_number': 42, 'acceptance_reason': 'verified'}}})
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
        'production': {'status': 'aligned_and_healthy', 'revision': 'a' * 40}})
    module.readmit_verified_development_recoveries(state, {'DEV-950'}, tmp_path, tmp_path)
    assert state['items']['DEV-950']['phase'] == 'blocked'
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
        'production': {'status': 'aligned_and_healthy', 'revision': sha,
         'observed_at': module.now()}})
    module.readmit_verified_development_recoveries(state, {'DEV-950'}, tmp_path, tmp_path)
    assert state['items']['DEV-950']['phase'] == 'diagnosing'
    assert state['items']['DEV-950']['recovery_readmitted_after_sha'] == sha

def test_governance_dependency_still_blocks_recovery_readmission(monkeypatch, tmp_path):
    sha = 'b' * 40
    state = {'items': {'DEV-866': {'phase': 'blocked', 'issue_number': 866,
        'blocker_class': 'internal_retry_exhausted',
        'recovery_support_issue_raised': 'SUPPORT-DEV-866'}}}
    module.support.save_state(tmp_path / 'state.json', {'items': {
        'SUPPORT-DEV-866': {'phase': 'complete', 'merge_sha': sha,
          'closure_pr_number': 1, 'acceptance_reason': 'verified'}}})
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
        'production': {'status': 'aligned_and_healthy', 'revision': sha}})
    module.readmit_verified_development_recoveries(state, {'DEV-866'}, tmp_path, tmp_path)
    assert state['items']['DEV-866']['phase'] == 'blocked'


def test_recovery_readmission_rejects_stale_production_proof(monkeypatch, tmp_path):
    sha = 'f' * 40
    state = {'items': {'DEV-950': {'phase': 'blocked', 'issue_number': 950,
       'blocker_class': 'internal_retry_exhausted',
       'recovery_support_issue_raised': 'SUPPORT-DEV-950'}}}
    module.support.save_state(tmp_path / 'state.json', {'items': {
       'SUPPORT-DEV-950': {'phase': 'complete', 'merge_sha': sha,
         'closure_pr_number': 42, 'acceptance_reason': 'verified'}}})
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
       'production': {'status': 'aligned_and_healthy', 'revision': sha,
       'observed_at': '2026-01-01T00:00:00+00:00'}})
    module.readmit_verified_development_recoveries(state, {'DEV-950'}, tmp_path, tmp_path)
    assert state['items']['DEV-950']['phase'] == 'blocked'


def test_development_owner_action_notifies_once(tmp_path):
    record = {'phase': 'blocked', 'notification_class': 'owner_action_required',
              'owner_action': 'Approve protected core promotion', 'reason': 'Approval needed'}
    item = {'id': 'DEV-950', 'title': 'Test'}
    module.sync_lifecycle_notification(record, item, event_root=tmp_path)
    module.sync_lifecycle_notification(record, item, event_root=tmp_path)
    assert len(list(tmp_path.glob('*.json'))) == 1
    assert record.get('lifecycle_blocked_fingerprint')


def test_authoritative_issue_hold_blocks_dev_admission():
    held = {'id': 'DEV-866', 'body': (
        '## Production-health gate hold\n\n'
        '**State: Blocked by Dependency / production-health gate.**\n'
        'Do not begin development until upstream production verification.')}
    clear = {'id': 'DEV-950', 'body': 'Approved engineering work.'}
    assert module.issue_has_closed_dependency_gate(held) is True
    assert module.issue_has_closed_dependency_gate(clear) is False
    admitted = [item for item in (held, clear) if not module.issue_has_closed_dependency_gate(item)]
    assert [item['id'] for item in admitted] == ['DEV-950']


def test_dependency_hold_replaces_stale_worker_error_and_resumes_when_authoritatively_lifted(monkeypatch, tmp_path):
    state = {'items': {'DEV-866': {'phase': 'blocked',
       'reason': 'autonomous support repair requires a changed regression test',
       'blocker_class': 'internal_retry_exhausted', 'self_recovery_attempts': 2}}}
    issue = {'id': 'DEV-866', 'body': (
       '## Production-health gate hold\nState: Blocked by Dependency\n')}
    module.reconcile_issue_dependency_holds(state, [issue], tmp_path)
    item = state['items']['DEV-866']
    assert item['blocker_class'] == 'blocked_by_dependency'
    assert 'production-health' in item['reason']
    assert 'changed regression test' in item['prior_worker_error']
    assert item['phase'] == 'blocked'
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
        'production': {'status': 'aligned_and_healthy', 'observed_at': '2026-01-01T00:00:00+00:00'}})
    module.reconcile_issue_dependency_holds(state, [{'id': 'DEV-866', 'body': 'Gate cleared by owner'}], tmp_path)
    assert item['phase'] == 'blocked'
    monkeypatch.setattr(module.support, 'production_state_from_main', lambda repo: {
        'production': {'status': 'aligned_and_healthy', 'observed_at': module.now()}})
    module.reconcile_issue_dependency_holds(state, [{'id': 'DEV-866', 'body': 'Gate cleared by owner'}], tmp_path)
    assert item['phase'] == 'diagnosing'
    assert item['reasoning_request_id'] == ''


def test_exhaustion_diagnostic_uses_supported_reasoning_kind(monkeypatch, tmp_path):
    observed = []
    def fake_queue(spool, *, kind, item, context):
        observed.append(kind)
        return 'request-id'
    monkeypatch.setattr(module, 'queue_reasoning', fake_queue)
    state={'items':{'DEV-950':{'phase':'blocked','blocker_class':'internal_retry_exhausted'}}}
    module.queue_exhausted_recovery_diagnostics(state,[{'id':'DEV-950','issue_number':950,
        'title':'Context repair','evidence':'test','acceptance':'test'}],tmp_path)
    assert observed == ['search_plan']


def test_failed_unsupported_diagnostic_is_requeued_once(monkeypatch, tmp_path):
    import json
    rid='legacy-request'
    root=tmp_path/'reasoning'/'requests';root.mkdir(parents=True)
    (root/(rid+'.json')).write_text(json.dumps({'kind':'diagnosis','request_id':rid}))
    monkeypatch.setattr(module.support,'reasoning_response',lambda spool, request_id: {
        'status':'failed','error':'unsupported support/development reasoning kind'})
    kinds=[]
    monkeypatch.setattr(module,'queue_reasoning',lambda spool,*,kind,item,context: (kinds.append(kind),'new-request')[1])
    rec={'phase':'blocked','blocker_class':'internal_retry_exhausted',
         'recovery_diagnostic_request_id':rid, 'recovery_diagnostic_result_status':'failed'}
    state={'items':{'DEV-950':rec}}
    item={'id':'DEV-950','issue_number':950,'title':'Fix','evidence':'data','acceptance':'test'}
    module.queue_exhausted_recovery_diagnostics(state,[item],tmp_path)
    assert rec['recovery_diagnostic_request_id']=='new-request'
    assert rec['recovery_diagnostic_prior_request_id']==rid
    assert 'recovery_diagnostic_result_status' not in rec
    module.queue_exhausted_recovery_diagnostics(state,[item],tmp_path)
    assert kinds==['search_plan']
