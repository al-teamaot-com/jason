from __future__ import annotations

import unittest

import pytest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from implementation.connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalEvidenceReference,
    ApprovalRequest,
    ApprovalRequestService,
    ApprovalResponse,
    InMemoryApprovalRequestRepository,
)
from implementation.connectors.microsoft_graph.teams_approval_channel import parse_teams_response, render_approval_card


NOW = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)


class Authority:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def can_approve(self, **_: object) -> bool:
        return self.allowed


def request() -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="apr-1", request_id="req-1", correlation_id="corr-1",
        organization_id="org-a", client_id="client-a", requested_by="user-requester",
        capability="microsoft.resource.execute", requested_mode="execute",
        requested_at=NOW, expires_at=NOW + timedelta(minutes=10),
        authorized_approver_ids=("user-approver",),
        evidence_references=(ApprovalEvidenceReference("artifact-1", "org-a", "a" * 64),),
    )


class ApprovalRequestTests(unittest.TestCase):
    def test_teams_is_transport_not_authority(self) -> None:
        repo = InMemoryApprovalRequestRepository()
        service = ApprovalRequestService(repo, Authority(False))
        service.create(request(), now=NOW)
        response = parse_teams_response(
            {"approval_id": "apr-1", "organization_id": "org-a", "decision": "approve", "channel_response_id": "teams-1"},
            authenticated_identity_id="user-approver", decided_at=NOW + timedelta(minutes=1),
        )
        with self.assertRaises(PermissionError):
            service.accept_response(response, now=NOW + timedelta(minutes=1))

    def test_authorized_approval_is_accepted(self) -> None:
        repo = InMemoryApprovalRequestRepository()
        service = ApprovalRequestService(repo, Authority(True))
        service.create(request(), now=NOW)
        accepted = service.accept_response(ApprovalResponse(
            approval_id="apr-1", organization_id="org-a", approver_identity_id="user-approver",
            decision=ApprovalDecision.APPROVE, decided_at=NOW + timedelta(minutes=1),
            channel="microsoft_teams", channel_response_id="teams-1",
        ), now=NOW + timedelta(minutes=1))
        self.assertEqual(accepted.status, "approved")
        self.assertEqual(accepted.capability, "microsoft.resource.execute")

    def test_cross_organization_response_fails_closed(self) -> None:
        repo = InMemoryApprovalRequestRepository()
        service = ApprovalRequestService(repo, Authority(True))
        service.create(request(), now=NOW)
        with self.assertRaises(PermissionError):
            service.accept_response(ApprovalResponse(
                approval_id="apr-1", organization_id="org-b", approver_identity_id="user-approver",
                decision=ApprovalDecision.APPROVE, decided_at=NOW + timedelta(minutes=1),
                channel="microsoft_teams", channel_response_id="teams-1",
            ), now=NOW + timedelta(minutes=1))

    def test_expired_response_fails_closed(self) -> None:
        repo = InMemoryApprovalRequestRepository()
        service = ApprovalRequestService(repo, Authority(True))
        service.create(request(), now=NOW)
        with self.assertRaises(PermissionError):
            service.accept_response(ApprovalResponse(
                approval_id="apr-1", organization_id="org-a", approver_identity_id="user-approver",
                decision=ApprovalDecision.APPROVE, decided_at=NOW + timedelta(minutes=11),
                channel="microsoft_teams", channel_response_id="teams-1",
            ), now=NOW + timedelta(minutes=11))

    def test_evidence_cannot_cross_organization(self) -> None:
        bad = replace(request(), evidence_references=(ApprovalEvidenceReference("artifact-1", "org-b", "b" * 64),))
        with self.assertRaises(ValueError):
            bad.validate()

    def test_card_contains_reference_not_artifact_content(self) -> None:
        card = render_approval_card(request())
        self.assertEqual(card.evidence_artifact_ids, ("artifact-1",))
        self.assertNotIn("a" * 64, card.summary)


if __name__ == "__main__":
    unittest.main()


def test_request_changes_is_terminal_without_approval():
    repo = InMemoryApprovalRequestRepository()
    service = ApprovalRequestService(repo, Authority(True))
    service.create(request(), now=NOW)
    accepted = service.accept_response(ApprovalResponse(
        approval_id="apr-1", organization_id="org-a", approver_identity_id="user-approver",
        decision=ApprovalDecision.REQUEST_CHANGES, decided_at=NOW + timedelta(minutes=1),
        channel="microsoft_teams", channel_response_id="teams-1",
    ), now=NOW + timedelta(minutes=1))
    assert accepted.status == "changes_requested"
    assert repo.get("apr-1").status.value == "changes_requested"


def test_sqlite_approval_request_round_trips_presentation_and_metadata(tmp_path):
    from implementation.connectors.src.jason_connectors.approval_requests import (
        ApprovalPresentation,
        SQLiteApprovalRequestRepository,
    )
    original = replace(
        request(),
        presentation=ApprovalPresentation(
            title="Approve playbook",
            summary="Exact autonomy scope",
            facts=(("Version", "1.2.3"), ("Capabilities", "a.b,c.d")),
        ),
        metadata={"playbook_id": "pb", "entry_sha256": "c" * 64},
    )
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    repo.put(original)
    loaded = repo.get(original.approval_id)
    assert loaded == original
    assert repo.list_all() == (original,)
    repo.close()


def test_playbook_presentation_is_rendered_into_teams_card():
    from implementation.connectors.src.jason_connectors.approval_requests import ApprovalPresentation
    card = render_approval_card(replace(
        request(),
        presentation=ApprovalPresentation(
            title="Approve Jason autonomy",
            summary="Owner review required",
            facts=(("Playbook", "low_disk_space"), ("Version", "1.1.0")),
        ),
    ))
    assert card.title == "Approve Jason autonomy"
    assert card.summary == "Owner review required"
    assert ("Playbook", "low_disk_space") in card.facts


def test_sqlite_repository_rejects_changed_scope_for_same_approval_id(tmp_path):
    from implementation.connectors.src.jason_connectors.approval_requests import SQLiteApprovalRequestRepository
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    original = request()
    repo.put(original)
    with pytest.raises(ValueError, match="changed immutable scope"):
        repo.put(replace(original, requested_mode="administer"))
    repo.close()
