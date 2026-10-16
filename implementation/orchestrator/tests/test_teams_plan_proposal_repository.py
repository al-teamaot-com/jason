from datetime import datetime, timedelta, timezone
import sqlite3
import pytest
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_proposal_repository import PlanProposalRepository

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)

def proposal():
    scope = ApprovedPlanScope('p','tenant','policy',frozenset({'build'}),frozenset({'c1'}),2,False,NOW+timedelta(hours=1))
    return ServerOwnedPlanProposal('approval','tenant','c1','user','build','digest',scope)

def test_persisted_proposal_is_exact_and_survives_restart(tmp_path):
    path=tmp_path/'proposals.sqlite3'
    repo=PlanProposalRepository(path)
    repo.store(proposal())
    assert PlanProposalRepository(path).require('approval') == proposal()


def test_same_approval_id_cannot_overwrite_original_scope(tmp_path):
    repo=PlanProposalRepository(tmp_path/'proposals.sqlite3')
    repo.store(proposal())
    with pytest.raises(sqlite3.IntegrityError):
        repo.store(proposal())


def test_unknown_approval_fails_closed(tmp_path):
    repo=PlanProposalRepository(tmp_path/'proposals.sqlite3')
    with pytest.raises(PermissionError):
        repo.require('unknown')


def test_stored_proposal_drives_approval_without_card_scope(tmp_path):
    from orchestrator.tests.test_teams_plan_approval_service import setup, NOW
    service, flow, approved_proposal, request = setup(tmp_path)
    repo = PlanProposalRepository(tmp_path / 'proposals.sqlite3')
    repo.store(approved_proposal)
    service.handle_stored_response(proposal_repository=repo, token='signed',
        payload={'approval_id':'approval','plan_fingerprint':'forged'},
        original_request=request, decided_at=NOW)
    assert flow.calls == 1
    assert repo.require('approval').plan_fingerprint == 'digest'

def test_unstored_callback_does_not_touch_identity_flow(tmp_path):
    from orchestrator.tests.test_teams_plan_approval_service import setup, NOW
    service, flow, _, request = setup(tmp_path)
    repo = PlanProposalRepository(tmp_path / 'proposals.sqlite3')
    with pytest.raises(PermissionError):
        service.handle_stored_response(proposal_repository=repo, token='signed',
            payload={'approval_id':'approval'}, original_request=request, decided_at=NOW)
    assert flow.calls == 0
