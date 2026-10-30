from pathlib import Path
from types import SimpleNamespace
import pytest
from connectors.microsoft_graph.teams_approval_response_runtime import build_universal_teams_plan_approval_service
from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService


def test_universal_runtime_factory_reuses_existing_microsoft_jkd_composition(tmp_path):
    dependencies = SimpleNamespace(token_verifier=object(),tenant_bindings=object(),
        identity_bindings=object(),approval_service=object(),resume_bridge=object(),
        audit=object(),attention_sink=None)
    service = build_universal_teams_plan_approval_service(
        dependencies=dependencies,ledger_path=str(tmp_path / 'plans.sqlite3'))
    assert isinstance(service, UniversalTeamsPlanApprovalService)
    assert service.teams_flow.token_verifier is dependencies.token_verifier
    assert service.teams_flow.resume_bridge is dependencies.resume_bridge
    assert service.teams_flow.audit is dependencies.audit
    assert Path(service.ledger.path).exists()


def test_runtime_factory_rejects_unpersisted_ledger_path():
    with pytest.raises(ValueError):
        build_universal_teams_plan_approval_service(dependencies=object(),ledger_path='')
