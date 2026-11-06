from types import SimpleNamespace
import pytest
from connectors.microsoft_graph.teams_approval_response_runtime import build_universal_teams_plan_dispatch
from orchestrator.teams_plan_response_dispatch import UniversalPlanResponseDispatch

class Port:
    def __getattr__(self, name):
        return lambda *a, **k: None

def deps():
    return SimpleNamespace(token_verifier=Port(), tenant_bindings=Port(),
        identity_bindings=Port(), approval_service=Port(), resume_bridge=Port(),
        audit=Port(), attention_sink=None)

def test_complete_trusted_ports_compose_durable_dispatch(tmp_path):
    handler = build_universal_teams_plan_dispatch(
        dependencies=deps(), ledger_path=str(tmp_path/'grants.sqlite3'),
        proposal_repository=Port(), request_repository=Port(), verified_token_source=Port())
    assert isinstance(handler, UniversalPlanResponseDispatch)
    assert (tmp_path/'grants.sqlite3').exists()

@pytest.mark.parametrize('missing', ['proposal_repository','request_repository','verified_token_source'])
def test_missing_trusted_dependency_fails_before_install(tmp_path, missing):
    inputs=dict(dependencies=deps(), ledger_path=str(tmp_path/'grants.sqlite3'),
        proposal_repository=Port(),request_repository=Port(),verified_token_source=Port())
    inputs[missing]=None
    with pytest.raises(ValueError, match=missing):
        build_universal_teams_plan_dispatch(**inputs)
    assert not (tmp_path/'grants.sqlite3').exists()

def test_missing_real_identity_verifier_fails_before_install(tmp_path):
    d=deps(); d.token_verifier=object()
    with pytest.raises(ValueError, match='token_verifier'):
        build_universal_teams_plan_dispatch(
            dependencies=d, ledger_path=str(tmp_path/'grants.sqlite3'),
            proposal_repository=Port(), request_repository=Port(), verified_token_source=Port())
