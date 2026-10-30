from types import SimpleNamespace

import pytest

from jason_runtime.procurement_teams_flow import ApprovalInteractionDispatcher


class RecordingFlow:
    def __init__(self, result):
        self.calls = []
        self.result = result

    def handle(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_universal_approval_routes_only_to_universal_handler():
    procurement = RecordingFlow({'route': 'procurement'})
    fallback = RecordingFlow({'route': 'fallback'})
    universal = RecordingFlow({'route': 'universal'})
    dispatcher = ApprovalInteractionDispatcher(procurement, fallback, universal)
    result = dispatcher.handle(approval_id='planapproval-abc', decision='deny')
    assert result == {'route': 'universal'}
    assert universal.calls == [{'approval_id': 'planapproval-abc', 'decision': 'deny'}]
    assert not procurement.calls and not fallback.calls


def test_unconfigured_plan_cannot_be_reinterpreted_as_playbook_approval():
    fallback = RecordingFlow({'status': 'approved'})
    dispatcher = ApprovalInteractionDispatcher(None, fallback)
    with pytest.raises(PermissionError, match='universal plan approval flow is not configured'):
        dispatcher.handle(approval_id='planapproval-abc', decision='approve')
    assert fallback.calls == []


def test_existing_approval_routes_remain_unchanged():
    procurement = RecordingFlow({'route': 'procurement'})
    fallback = RecordingFlow({'route': 'fallback'})
    universal = RecordingFlow({'route': 'universal'})
    dispatcher = ApprovalInteractionDispatcher(procurement, fallback, universal)
    assert dispatcher.handle(approval_id='procapproval-abc') == {'route': 'procurement'}
    assert dispatcher.handle(approval_id='playbook-abc') == {'route': 'fallback'}
    assert not universal.calls


def test_runtime_composition_has_explicit_universal_handler_boundary():
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / 'src/jason_runtime/composition.py'
    module = ast.parse(src.read_text())
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'build_runtime_application')
    assert 'universal_approval_handler' in [arg.arg for arg in function.args.kwonlyargs]
    assert any(isinstance(v, ast.Constant) and v.value is None
               for v in function.args.kw_defaults)
    assert 'universal=universal_approval_handler' in src.read_text()


def test_unconfigured_universal_plan_denial_also_fails_closed():
    fallback = RecordingFlow({'status': 'denied'})
    dispatcher = ApprovalInteractionDispatcher(None, fallback)
    with pytest.raises(PermissionError, match='universal plan approval flow is not configured'):
        dispatcher.handle(approval_id='planapproval-abc', decision='deny')
    assert fallback.calls == []
