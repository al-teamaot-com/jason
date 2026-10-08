from datetime import datetime, timedelta, timezone

import pytest

from jason_runtime.playbook_approval_resume import (
    PlaybookActionProposal,
    SQLitePlaybookActionProposalStore,
)


NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)


def proposal(**overrides):
    values = dict(
        proposal_id="proposal-1",
        playbook_id="idle_log_off",
        playbook_version="1.1.0",
        policy_id="playbook-autonomy:idle_log_off",
        ticket_id=140001,
        client_id="507",
        target_id="device-1",
        capability="automation.component.execute",
        action_id="Set Idle Log Off AOT Ver 02042026-1",
        arguments={"variables": {}},
        disruption_classification="modifying_future_user_session",
        expected_verification="authoritative DRMM alert clears",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )
    values.update(overrides)
    return PlaybookActionProposal(**values)


def test_exact_proposal_fingerprint_is_stable_and_scope_bound():
    first = proposal()
    same = proposal()
    changed = proposal(target_id="device-2")
    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_restart_between_proposal_and_approval_resumes_same_record(tmp_path):
    path = tmp_path / "approval.sqlite3"
    store = SQLitePlaybookActionProposalStore(path)
    created = store.create(proposal())
    fingerprint = created.proposal.fingerprint
    store.close()

    store = SQLitePlaybookActionProposalStore(path)
    restored = store.get("proposal-1")
    assert restored is not None
    assert restored.status == "pending"
    assert restored.proposal.fingerprint == fingerprint
    approved = store.decide(
        proposal_id="proposal-1",
        proposal_fingerprint=fingerprint,
        approval_id="approval-1",
        decision="approved",
        decided_by="owner",
        decided_at=NOW + timedelta(minutes=5),
    )
    assert approved.status == "approved"
    store.close()


def test_mismatched_target_or_fingerprint_cannot_resume(tmp_path):
    store = SQLitePlaybookActionProposalStore(tmp_path / "approval.sqlite3")
    state = store.create(proposal())
    with pytest.raises(PermissionError):
        store.decide(
            proposal_id="proposal-1",
            proposal_fingerprint=proposal(target_id="other").fingerprint,
            approval_id="approval-1",
            decision="approved",
            decided_by="owner",
            decided_at=NOW + timedelta(minutes=5),
        )
    assert store.get("proposal-1").status == "pending"
    store.close()


def test_duplicate_approval_delivery_does_not_duplicate_decision(tmp_path):
    store = SQLitePlaybookActionProposalStore(tmp_path / "approval.sqlite3")
    state = store.create(proposal())
    fingerprint = state.proposal.fingerprint
    store.decide(
        proposal_id="proposal-1",
        proposal_fingerprint=fingerprint,
        approval_id="approval-1",
        decision="approved",
        decided_by="owner",
        decided_at=NOW + timedelta(minutes=5),
    )
    with pytest.raises(ValueError):
        store.decide(
            proposal_id="proposal-1",
            proposal_fingerprint=fingerprint,
            approval_id="approval-1",
            decision="approved",
            decided_by="owner",
            decided_at=NOW + timedelta(minutes=6),
        )
    store.close()


def test_approved_proposal_consumes_exactly_once(tmp_path):
    store = SQLitePlaybookActionProposalStore(tmp_path / "approval.sqlite3")
    state = store.create(proposal())
    fingerprint = state.proposal.fingerprint
    store.decide(
        proposal_id="proposal-1",
        proposal_fingerprint=fingerprint,
        approval_id="approval-1",
        decision="approved",
        decided_by="owner",
        decided_at=NOW + timedelta(minutes=5),
    )
    consumed = store.consume_approved(
        proposal_id="proposal-1",
        proposal_fingerprint=fingerprint,
        execution_id="exec-1",
        correlation_id="corr-1",
        now=NOW + timedelta(minutes=6),
    )
    assert consumed.status == "consumed"
    assert consumed.execution_id == "exec-1"
    with pytest.raises(ValueError):
        store.consume_approved(
            proposal_id="proposal-1",
            proposal_fingerprint=fingerprint,
            execution_id="exec-2",
            correlation_id="corr-2",
            now=NOW + timedelta(minutes=7),
        )
    store.close()


def test_denial_is_terminal_and_cannot_execute(tmp_path):
    store = SQLitePlaybookActionProposalStore(tmp_path / "approval.sqlite3")
    state = store.create(proposal())
    fingerprint = state.proposal.fingerprint
    denied = store.decide(
        proposal_id="proposal-1",
        proposal_fingerprint=fingerprint,
        approval_id="approval-1",
        decision="denied",
        decided_by="owner",
        decided_at=NOW + timedelta(minutes=5),
    )
    assert denied.status == "denied"
    with pytest.raises(PermissionError):
        store.consume_approved(
            proposal_id="proposal-1",
            proposal_fingerprint=fingerprint,
            execution_id="exec-1",
            correlation_id="corr-1",
            now=NOW + timedelta(minutes=6),
        )
    store.close()
