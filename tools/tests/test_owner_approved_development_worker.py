import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'owner_approved_development_worker.py'
SPEC = importlib.util.spec_from_file_location('owner_approved_development_worker', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


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
    assert module.select_items(state, eligible, capacity=1) == ['DEV-10']
    assert module.select_items(state, eligible, capacity=2) == ['DEV-10', 'DEV-12']
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
