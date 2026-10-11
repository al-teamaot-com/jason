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


def test_successful_search_plan_diagnostic_creates_inert_handoff(monkeypatch, tmp_path):
    rec={'phase':'blocked','blocker_class':'internal_retry_exhausted',
         'recovery_diagnostic_request_id':'request-123','reason':'insufficient source'}
    state={'items':{'DEV-950':rec}}
    monkeypatch.setattr(module.support, 'reasoning_response',lambda spool, request_id:{
        'request_id':request_id,'status':'succeeded',
        'result':{'queries':['specific missing implementation path']}})
    module.reconcile_exhausted_recovery_diagnostics(state,{'DEV-950'},tmp_path)
    assert rec['phase']=='blocked'
    assert rec['recovery_diagnostic_result_status']=='succeeded'
    assert 'specific missing implementation path' in rec['recovery_diagnostic_summary']
    assert rec.get('recovery_handoff_id')
    handoffs=list((tmp_path/'development-recovery'/'handoffs').glob('*.json'))
    assert len(handoffs)==1
    import json
    assert json.loads(handoffs[0].read_text())['admission_authority'] is False


def test_blocked_work_next_action_categorizes_without_authority():
    cases = [
        ('Missing supplied source excerpts', 'source_context'),
        ('Blocked until prerequisite verified', 'dependency'),
        ('Provider credential unavailable', 'external_authority'),
        ('requires a changed regression test', 'verification'),
        ('unclassified error', 'unclassified'),
    ]
    for reason, category in cases:
        result = module.blocked_work_next_action(reason)
        assert result['blocker_category'] == category
        assert result['next_action']
        assert 'admission_authority' not in result


def test_blocked_record_remains_blocked_after_classification(tmp_path):
    record = {'phase': 'blocked', 'reason': 'Missing supplied source excerpts'}
    module.sync_lifecycle_notification(record, {'id': 'DEV-22', 'title': 'Test'}, event_root=tmp_path)
    assert record['phase'] == 'blocked'
    assert record['next_action'] == 'retrieve_authorized_context'


def test_development_defers_transient_pr_listing_without_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv',
        ['owner_approved_development_worker.py', '--repo', str(tmp_path),
         '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(module.support, 'run', lambda *a, **kw: '')
    monkeypatch.setattr(module, 'owner_approved_issues', lambda _: [])
    for fn in (
        'reconcile_issue_dependency_holds', 'reconcile_removed_approval',
        'recycle_self_recoverable_blockers', 'queue_exhausted_recovery_diagnostics',
        'reconcile_exhausted_recovery_diagnostics', 'reconcile_recovery_handoff_intake',
        'raise_exhausted_repair_support_issues', 'readmit_verified_development_recoveries',
    ):
        monkeypatch.setattr(module, fn, lambda *a, **kw: None)
    monkeypatch.setattr(module, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(module.support, 'open_prs', lambda _: (_ for _ in ()).throw(
        module.support.WorkerError('GitHub JSON command failed: unexpected end of JSON input')))
    assert module.main() == 0
    state = module.support.load_state(tmp_path / 'spool' / 'development-state.json')
    assert state['upstream_deferred']['reason'] == 'transient_pr_listing_error'
    assert state['items'] == {}


def test_development_does_not_defer_permission_denial(monkeypatch, tmp_path):
    import pytest

    monkeypatch.setattr(sys, 'argv',
        ['owner_approved_development_worker.py', '--repo', str(tmp_path),
         '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(module.support, 'run', lambda *a, **kw: '')
    monkeypatch.setattr(module, 'owner_approved_issues', lambda _: [])
    for fn in (
        'reconcile_issue_dependency_holds', 'reconcile_removed_approval',
        'recycle_self_recoverable_blockers', 'queue_exhausted_recovery_diagnostics',
        'reconcile_exhausted_recovery_diagnostics', 'reconcile_recovery_handoff_intake',
        'raise_exhausted_repair_support_issues', 'readmit_verified_development_recoveries',
    ):
        monkeypatch.setattr(module, fn, lambda *a, **kw: None)
    monkeypatch.setattr(module, 'active_support_count', lambda _: 0)
    monkeypatch.setattr(module.support, 'open_prs', lambda _: (_ for _ in ()).throw(
        module.support.WorkerError('HTTP 403: forbidden')))
    with pytest.raises(module.support.WorkerError, match='403'):
        module.main()


def test_verified_ccc_owner_review_readmits_once(tmp_path):
    import json
    from datetime import datetime, timezone
    sha = 'e' * 40
    review = tmp_path / 'review.json'
    drift = tmp_path / 'drift.json'
    reports = tmp_path / 'reports'
    folder = reports / 'run1'
    folder.mkdir(parents=True)
    review.write_text(json.dumps({'status': 'approved', 'source_revision': sha}))
    drift.write_text(json.dumps({'status': 'pass', 'problems': [], 'observed_at': datetime.now(timezone.utc).isoformat()}))
    (folder / 'ccc-report.json').write_text(json.dumps({'status': 'PASS', 'source_revision': sha, 'runtime_revision': sha, 'checks': [{'status': 'PASS'}]}))
    original = 'Exact owner-approved CCC material-change review for the current production SHA is required and not yet authorized.'
    state = {'items': {'DEV-1237': {'phase': 'blocked', 'reason': original}}}
    kwargs = dict(review_path=review, report_root=reports, drift_path=drift)
    assert module.readmit_verified_ccc_owner_review(state, {'DEV-1237'}, **kwargs) == 1
    assert state['items']['DEV-1237']['phase'] == 'diagnosing'
    state['items']['DEV-1237'].update(phase='blocked', reason=original)
    assert module.readmit_verified_ccc_owner_review(state, {'DEV-1237'}, **kwargs) == 0
    state['items']['DEV-1237'].pop('verified_ccc_readmission_sha')
    drift.write_text(json.dumps({'status': 'drift_detected', 'problems': ['failed'], 'observed_at': datetime.now(timezone.utc).isoformat()}))
    assert module.readmit_verified_ccc_owner_review(state, {'DEV-1237'}, **kwargs) == 0


def test_ccc_readmission_rejects_empty_certification_checks(tmp_path):
    import json
    from datetime import datetime, timezone
    sha = 'e' * 40
    review = tmp_path / 'review.json'
    drift = tmp_path / 'drift.json'
    reports = tmp_path / 'reports'
    folder = reports / 'run1'
    folder.mkdir(parents=True)
    review.write_text(json.dumps({'status': 'approved', 'source_revision': sha}))
    drift.write_text(json.dumps({'status': 'pass', 'problems': [], 'observed_at': datetime.now(timezone.utc).isoformat()}))
    (folder / 'ccc-report.json').write_text(json.dumps({'status': 'PASS', 'source_revision': sha, 'runtime_revision': sha, 'checks': []}))
    state = {'items': {'DEV-1237': {'phase': 'blocked', 'reason': 'Exact CCC material-change review required.'}}}
    assert module.readmit_verified_ccc_owner_review(state, {'DEV-1237'}, review_path=review, drift_path=drift, report_root=reports) == 0
    assert state['items']['DEV-1237']['phase'] == 'blocked'


def test_explicit_approved_paths_prioritize_exact_targets(monkeypatch, tmp_path):
    scope = ('Only edit `tools/owner_approved_development_worker.py` and '
             '`tools/tests/test_owner_approved_development_worker.py`; '
             'ignore `tools/../secret.py`.')
    assert module.explicit_approved_source_paths(scope) == [
        'tools/owner_approved_development_worker.py',
        'tools/tests/test_owner_approved_development_worker.py',
    ]
    (tmp_path / 'tools/tests').mkdir(parents=True)
    (tmp_path / 'tools/owner_approved_development_worker.py').write_text('def target(): pass')
    (tmp_path / 'tools/tests/test_owner_approved_development_worker.py').write_text('def test_target(): pass')
    monkeypatch.setattr(module.support, 'source_excerpts_for_paths',
                        lambda tree, paths, gate, policy, **kw: [
                            {'path': p, 'content': (tree / p).read_text()} for p in paths
                            if (tree / p).is_file()])
    targets = module.support.source_excerpts_for_paths(
        tmp_path, module.explicit_approved_source_paths(scope), None, {}, limit=6)
    merged = module.support.merge_source_excerpts(targets, [
        {'path': 'implementation/unrelated.py', 'content': 'unrelated'}], max_total=14)
    assert [x['path'] for x in merged[:2]] == module.explicit_approved_source_paths(scope)


def test_long_file_target_symbol_is_complete_and_prioritized():
    source = 'import json\n' + ('x = 1\n' * 6000) + (
        'def readmit_verified_ccc_owner_review(state):\n'
        '    check = True\n'
        '    return check\n') + ('y = 2\n' * 6000)
    result = module.support.bounded_symbol_excerpt(
        source, ['readmit_verified_ccc_owner_review'], content_limit=4000)
    assert 'def readmit_verified_ccc_owner_review(state):' in result
    assert '    return check' in result
    assert len(result) <= 4000


def test_symbol_extraction_fails_closed_on_incomplete_definition():
    assert module.support.bounded_symbol_excerpt('def unfinished(:', ['unfinished'], content_limit=3000) is None


def test_verified_worker_upgrade_fails_closed_without_release(tmp_path):
    spool = tmp_path / 'support-repair'
    spool.mkdir()
    link = tmp_path / ('a' * 40)
    link.mkdir()
    record = {'phase': 'blocked', 'blocker_class': 'source_context', 'reason': 'missing source excerpts'}
    state = {'items': {'DEV-1245': record}}
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=link) == 0
    assert record['phase'] == 'blocked'


def test_production_identity_api_context_keeps_complete_contract(tmp_path):
    from pathlib import Path
    import types
    worktree = tmp_path
    path = worktree / 'tools/release_manager_host_runner.py'
    path.parent.mkdir()
    path.write_text('import json\n' + ('padding=1\n' * 8000)
                    + 'def live_runtime():\n    return {"revision": "sha"}\n'
                    + 'def live_mcp():\n    return {"revision": "sha"}\n'
                    + 'def live_production_alignment(candidate_sha):\n'
                    + '    return {"runtime_revision": candidate_sha}\n')
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    result = module.support.source_excerpts_for_paths(
        worktree, ['tools/release_manager_host_runner.py'], gate, {},
        terms=['live_runtime', 'live_mcp', 'live_production_alignment'],
        content_limit=18000)
    assert len(result) == 1
    assert 'return {"revision": "sha"}' in result[0]['content']
    assert 'return {"runtime_revision": candidate_sha}' in result[0]['content']
    chosen = module.support.merge_source_excerpts(result, [
        {'path': 'implementation/unrelated.py', 'content': 'other'}], max_total=1)
    assert chosen[0]['path'] == 'tools/release_manager_host_runner.py'


def test_approved_test_file_full_context_with_bounded_56k_limit(tmp_path):
    import types
    test_path = tmp_path / 'tools/tests/test_owner_approved_development_worker.py'
    test_path.parent.mkdir(parents=True)
    expected = 'def test_reject_missing_production_identity():\n    assert True\n'
    body = '# preexisting regression context\n' * 1100 + expected
    assert 24000 < len(body) < 56000
    test_path.write_text(body)
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    context = module.support.source_excerpts_for_paths(
        tmp_path, ['tools/tests/test_owner_approved_development_worker.py'],
        gate, {}, terms=['CCC production SHA'], content_limit=56000, limit=1)
    assert context[0]['content'] == body
    assert expected in context[0]['content']


def test_verified_upgrade_readmits_truncated_approved_test_once(tmp_path):
    import json
    from datetime import datetime, timezone
    spool = tmp_path / 'support-repair'
    spool.mkdir()
    root = tmp_path / 'release-manager'
    (root / 'protected-readback').mkdir(parents=True)
    (root / 'records').mkdir()
    sha = 'a' * 40
    live = tmp_path / sha
    live.mkdir()
    (root / 'protected-readback/production-control-state.json').write_text(json.dumps(
        {'last_known_good': {'manifest': {'revision': sha}}}))
    (root / 'protected-readback/production-drift.json').write_text(json.dumps(
        {'status': 'pass', 'problems': [], 'observed_at': datetime.now(timezone.utc).isoformat()}))
    (root / 'records/release-test.json').write_text(json.dumps({
        'state': 'closed', 'release_candidate': {'candidate_sha': sha},
        'changed_files': ['tools/owner_approved_development_worker.py']}))
    reason = ('The required test file excerpt is truncated, so I cannot safely produce '
              'an exact-text regression test patch without inventing unseen surrounding code.')
    record = {'phase': 'blocked', 'blocker_class': 'internal_retry_exhausted',
              'reason': reason, 'self_recovery_attempts': 2}
    state = {'items': {'DEV-1245': record}}
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 1
    assert record['phase'] == 'diagnosing'
    assert record['self_recovery_attempts'] == 0
    record['phase'] = 'blocked'
    record['reason'] = reason
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 0
    assert record['phase'] == 'blocked'



def test_verified_upgrade_readmits_exact_anchor_failure_once(tmp_path):
    import json
    from datetime import datetime, timezone
    spool = tmp_path / 'support-repair'
    spool.mkdir()
    root = tmp_path / 'release-manager'
    (root / 'protected-readback').mkdir(parents=True)
    (root / 'records').mkdir()
    sha = 'b' * 40
    live = tmp_path / sha
    live.mkdir()
    (root / 'protected-readback/production-control-state.json').write_text(json.dumps(
        {'last_known_good': {'manifest': {'revision': sha}}}))
    (root / 'protected-readback/production-drift.json').write_text(json.dumps(
        {'status': 'pass', 'problems': [], 'observed_at': datetime.now(timezone.utc).isoformat()}))
    (root / 'records/release-test.json').write_text(json.dumps({
        'state': 'closed', 'release_candidate': {'candidate_sha': sha},
        'changed_files': ['tools/owner_approved_development_worker.py']}))
    reason = ('WorkerError: exact repair anchor must occur once in '
              'tools/owner_approved_development_worker.py; found 0')
    record = {'phase': 'blocked', 'blocker_class': 'internal_retry_exhausted',
              'reason': reason, 'self_recovery_attempts': 2, 'anchor_refresh_attempts': 2}
    state = {'items': {'DEV-1245': record}}
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, set(), spool, current_link=live) == 0
    assert record['phase'] == 'blocked'
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 1
    assert record['phase'] == 'diagnosing'
    assert record['self_recovery_attempts'] == 0
    assert record['anchor_refresh_attempts'] == 0
    record['phase'] = 'blocked'
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 0
    assert record['phase'] == 'blocked'



def test_exact_anchor_readmission_requires_verified_release(tmp_path):
    spool = tmp_path / 'support-repair'
    spool.mkdir()
    live = tmp_path / ('d' * 40)
    live.mkdir()
    record = {'phase': 'blocked', 'blocker_class': 'internal_retry_exhausted',
              'reason': 'WorkerError: exact repair anchor must occur once in tools/a.py; found 0'}
    state = {'items': {'DEV-1245': record}}
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 0
    assert record['phase'] == 'blocked'

def test_exact_anchor_readmission_rejects_unrelated_error(tmp_path):
    spool = tmp_path / 'support-repair'
    spool.mkdir()
    live = tmp_path / ('c' * 40)
    live.mkdir()
    record = {'phase': 'blocked', 'blocker_class': 'external_authority',
              'reason': 'WorkerError: exact repair anchor must occur once in file; found 0'}
    state = {'items': {'DEV-1245': record}}
    assert module.readmit_source_context_after_verified_worker_upgrade(
        state, {'DEV-1245'}, spool, current_link=live) == 0
    assert record['phase'] == 'blocked'

def test_stale_anchor_preflight_is_read_only_and_detects_later_edit_conflict(tmp_path):
    import types
    path = tmp_path / 'tools/owner_approved_development_worker.py'
    path.parent.mkdir()
    path.write_text('value = 1\n')
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    edits = [
        {'path': 'tools/owner_approved_development_worker.py', 'old_text': 'value = 1', 'new_text': 'value = 2'},
        {'path': 'tools/owner_approved_development_worker.py', 'old_text': 'value = 1', 'new_text': 'value = 3'},
    ]
    assert module.mismatched_exact_anchors(tmp_path, edits, gate, {}) == ['tools/owner_approved_development_worker.py']
    assert path.read_text() == 'value = 1\n'
    assert module.mismatched_exact_anchors(tmp_path, edits[:1], gate, {}) == []



def test_shared_anchor_preflight_queues_fresh_edit_plan_without_mutation(monkeypatch, tmp_path):
    import types
    source = tmp_path / 'tools/example.py'
    source.parent.mkdir()
    source.write_text('value = 1\n')
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    monkeypatch.setattr(module.support, 'source_excerpts_for_paths',
                        lambda *args, **kwargs: [{'path': 'tools/example.py', 'content': source.read_text()}])
    requests = []
    monkeypatch.setattr(module, 'queue_reasoning', lambda *args, **kwargs: requests.append(kwargs) or 'refreshed-id')
    monkeypatch.setattr(module, 'approved_scope', lambda item: 'tools/example.py')
    record = {'phase': 'implementing'}
    edits = [{'path': 'tools/example.py', 'old_text': 'value = 0', 'new_text': 'value = 2'}]
    assert module.preflight_or_refresh_exact_anchors(
        tmp_path, edits, gate, {}, record, {'issue_number': 42}, tmp_path)
    assert record['phase'] == 'implementing'
    assert record['reasoning_request_id'] == 'refreshed-id'
    assert record['anchor_refresh_attempts'] == 1
    assert requests[0]['context']['prior_anchor_failures'] == ['tools/example.py']
    assert source.read_text() == 'value = 1\n'
    assert not module.preflight_or_refresh_exact_anchors(
        tmp_path, [{'path': 'tools/example.py', 'old_text': 'value = 1',
                    'new_text': 'value = 2'}], gate, {}, record, {'issue_number': 42}, tmp_path)
    record['anchor_refresh_attempts'] = 2
    import pytest
    with pytest.raises(module.support.WorkerError, match='exact anchor refresh exhausted'):
        module.preflight_or_refresh_exact_anchors(
            tmp_path, edits, gate, {}, record, {'issue_number': 42}, tmp_path)
    assert len(requests) == 1
    assert source.read_text() == 'value = 1\n'


def test_both_worker_branches_invoke_shared_anchor_preflight():
    import inspect
    source = inspect.getsource(module.main)
    assert source.count('if preflight_or_refresh_exact_anchors(') == 2


def test_anchor_regeneration_carries_full_approved_test_context(monkeypatch, tmp_path):
    import types
    worker = tmp_path / 'tools/worker.py'
    test = tmp_path / 'tools/tests/test_worker.py'
    test.parent.mkdir(parents=True)
    worker.write_text('value = 1\n')
    test.write_text('def test_value():\n    assert True\n')
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    scope = 'Only edit `tools/worker.py` and `tools/tests/test_worker.py`.'
    monkeypatch.setattr(module, 'approved_scope', lambda item: scope)
    observed = []
    def excerpts(root, paths, gate_arg, policy, **kwargs):
        observed.extend(paths)
        return [{'path': path, 'content': (root / path).read_text()}
                for path in paths if (root / path).is_file()]
    monkeypatch.setattr(module.support, 'source_excerpts_for_paths', excerpts)
    queued = []
    monkeypatch.setattr(module, 'queue_reasoning',
                        lambda spool, **kwargs: queued.append(kwargs) or 'fresh-plan')
    record = {'phase': 'implementing'}
    stale = [{'path': 'tools/worker.py', 'old_text': 'value = 0', 'new_text': 'value = 2'}]
    assert module.preflight_or_refresh_exact_anchors(
        tmp_path, stale, gate, {}, record, {'issue_number': 42}, tmp_path)
    assert observed == ['tools/worker.py', 'tools/tests/test_worker.py']
    context = queued[0]['context']
    assert context['required_test_paths'] == ['tools/tests/test_worker.py']
    assert [part['path'] for part in context['source_excerpts']] == observed
    assert context['source_excerpts'][1]['content'] == test.read_text()
    assert record['reasoning_request_id'] == 'fresh-plan'
    assert record['anchor_refresh_attempts'] == 1
    assert worker.read_text() == 'value = 1\n'
    assert test.read_text() == 'def test_value():\n    assert True\n'


def test_anchor_regeneration_fails_closed_when_approved_tests_unavailable(monkeypatch, tmp_path):
    import types
    worker = tmp_path / 'tools/worker.py'
    worker.parent.mkdir(parents=True)
    worker.write_text('value = 1\n')
    gate = types.SimpleNamespace(path_denial_reason=lambda path, policy: '')
    monkeypatch.setattr(module, 'approved_scope',
                        lambda item: '`tools/worker.py` `tools/tests/test_worker.py`')
    monkeypatch.setattr(module.support, 'source_excerpts_for_paths',
                        lambda root, paths, *args, **kwargs: [
                            {'path': 'tools/worker.py', 'content': worker.read_text()}])
    queued = []
    monkeypatch.setattr(module, 'queue_reasoning',
                        lambda *args, **kwargs: queued.append(kwargs))
    import pytest
    with pytest.raises(module.support.WorkerError, match='approved tests unavailable'):
        module.preflight_or_refresh_exact_anchors(
            tmp_path, [{'path': 'tools/worker.py', 'old_text': 'absent',
                        'new_text': 'value = 2'}],
            gate, {}, {'phase': 'implementing'}, {'issue_number': 42}, tmp_path)
    assert not queued
    assert worker.read_text() == 'value = 1\n'


def test_real_implementing_worker_regenerates_full_patch_and_reaches_pr(monkeypatch, tmp_path):
    """Drive two ordinary main() cycles, not just the anchor helper."""
    import types
    source = tmp_path / 'tools/worker.py'
    regression = tmp_path / 'tools/tests/test_worker.py'
    regression.parent.mkdir(parents=True)
    source.write_text('value = 1\n')
    regression.write_text('def test_value():\n    assert True\n')
    item = {'id': 'DEV-42', 'issue_number': 42, 'title': 'Canary',
            'approval_source': 'owner-approved', 'approved_by': 'owner',
            'body': 'Only edit `tools/worker.py` and `tools/tests/test_worker.py`.'}
    record = {'phase': 'implementing', 'reasoning_request_id': 'stale-rid',
              'issue_number': 42, 'branch': 'develop/42'}
    state = {'items': {'DEV-42': record}}
    gate = types.SimpleNamespace(load_json=lambda path: {},
                                 path_denial_reason=lambda path, policy: '')
    monkeypatch.setattr(sys, 'argv',
                        ['owner_approved_development_worker.py', '--repo', str(tmp_path),
                         '--spool', str(tmp_path / 'spool')])
    monkeypatch.setattr(module.support, 'load_state', lambda path: state)
    monkeypatch.setattr(module.support, 'save_state', lambda path, obj: None)
    monkeypatch.setattr(module.support, 'run', lambda args, **kw: 'develop/42')
    monkeypatch.setattr(module, 'owner_approved_issues', lambda repo: [item])
    monkeypatch.setattr(module, 'issue_has_closed_dependency_gate', lambda item: False)
    for name in ('reconcile_issue_dependency_holds', 'reconcile_removed_approval',
                 'readmit_verified_ccc_owner_review', 'recycle_self_recoverable_blockers',
                 'queue_exhausted_recovery_diagnostics',
                 'reconcile_exhausted_recovery_diagnostics',
                 'reconcile_recovery_handoff_intake',
                 'raise_exhausted_repair_support_issues',
                 'readmit_verified_development_recoveries',
                 'readmit_source_context_after_verified_worker_upgrade',
                 'readmit_explicit_verified_dependencies'):
        monkeypatch.setattr(module, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'active_support_count', lambda spool: 0)
    monkeypatch.setattr(module, 'select_items', lambda state, admitted, capacity: ['DEV-42'])
    monkeypatch.setattr(module.support, 'open_prs', lambda repo: [])
    monkeypatch.setattr(module.support, 'load_gate', lambda repo: gate)
    monkeypatch.setattr(module, 'development_pr_for', lambda issue_number, prs: None)
    monkeypatch.setattr(module, 'known_development_pr_is_merged', lambda repo, rec: False)
    monkeypatch.setattr(module, 'ensure_worktree', lambda *args: tmp_path)
    monkeypatch.setattr(module, 'sync_lifecycle_notification', lambda *args, **kw: None)
    monkeypatch.setattr(module.support, 'source_excerpts_for_paths',
                        lambda root, paths, *args, **kw: [
                            {'path': p, 'content': (root / p).read_text()} for p in paths])
    queued = []
    monkeypatch.setattr(module, 'queue_reasoning',
                        lambda spool, **kw: queued.append(kw) or 'fresh-rid')
    def response(spool, rid):
        if rid == 'stale-rid':
            return {'status': 'succeeded', 'result': {
                'edits': [{'path': 'tools/worker.py', 'old_text': 'not present',
                           'new_text': 'value = 2'}]}}
        assert rid == 'fresh-rid'
        return {'status': 'succeeded', 'result': {
            'edits': [
                {'path': 'tools/worker.py', 'old_text': 'value = 1',
                 'new_text': 'value = 2'},
                {'path': 'tools/tests/test_worker.py', 'old_text': 'assert True',
                 'new_text': 'assert 2 == 2'},
            ],
            'test_paths': ['tools/tests/test_worker.py'],
        }}
    monkeypatch.setattr(module.support, 'reasoning_response', response)
    applied = []
    def apply_edits(root, edits, gate, policy):
        applied.append(list(edits))
        for edit in edits:
            path = root / edit['path']
            old = path.read_text()
            assert old.count(edit['old_text']) == 1
            path.write_text(old.replace(edit['old_text'], edit['new_text'], 1))
    monkeypatch.setattr(module.support, 'apply_edits', apply_edits)
    monkeypatch.setattr(module.support, 'validate_patch',
                        lambda root, paths, gate, policy: {'passed': True, 'paths': paths})
    def fake_pr(repo, worktree, item, tests):
        assert source.read_text() == 'value = 2\n'
        assert 'assert 2 == 2' in regression.read_text()
        assert tests['passed']
        return 4242
    monkeypatch.setattr(module, 'commit_and_pr', fake_pr)
    assert module.main() == 0
    assert record['phase'] == 'implementing'
    assert record['reasoning_request_id'] == 'fresh-rid'
    assert record['anchor_refresh_attempts'] == 1
    assert not applied
    assert [x['path'] for x in queued[0]['context']['source_excerpts']] == [
        'tools/worker.py', 'tools/tests/test_worker.py']
    assert module.main() == 0
    assert record['phase'] == 'pr_validating'
    assert record['pr_number'] == 4242
    assert len(applied) == 1


def test_negated_test_excerpt_is_source_context():
    reason = 'No dedicated test excerpt was supplied to safely patch regression tests.'
    assert module.source_context_blocker(reason)
    assert module.self_recoverable_blocker(reason)
    assert not module.source_context_blocker('All regression tests passed.')
