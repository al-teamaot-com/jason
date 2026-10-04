import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'owner_approved_development_worker.py'
SPEC = importlib.util.spec_from_file_location('owner_approved_development_worker', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_lifecycle_sync_writes_start_and_blocker(tmp_path):
    record = {'phase': 'blocked', 'reason': 'controlled acceptance blocker'}
    item = {'id': 'DEV-42', 'title': 'Teams lifecycle cards'}
    root = tmp_path / 'events'
    module.sync_lifecycle_notification(record, item, event_root=root)
    assert record['lifecycle_started_fingerprint']
    assert record['lifecycle_blocked_fingerprint']
    payloads = [module.support.json.loads(p.read_text()) for p in root.glob('*.json')]
    assert {p['event_type'] for p in payloads} == {'work_started', 'work_blocked'}


def test_owner_approval_marker_is_exact():
    assert module.APPROVAL.search('- **Autonomous development:** owner-approved')
    assert not module.APPROVAL.search('- **Autonomous development:** approved')
    assert not module.APPROVAL.search('- Autonomous development: owner-approved')


def test_select_items_respects_capacity_and_terminal_state():
    state = {
        'items': {
            'DEV-10': {'phase': 'diagnosing'},
            'DEV-11': {'phase': 'pr_ready'},
        }
    }
    eligible = [
        {'id': 'DEV-10', 'issue_number': 10},
        {'id': 'DEV-11', 'issue_number': 11},
        {'id': 'DEV-12', 'issue_number': 12},
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
    assert not module.source_context_blocker('Owner approval is required for production deployment.')
    assert not module.source_context_blocker('Provider credential is unavailable.')


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
