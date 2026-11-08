from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision, ApprovalRequest, ApprovalRequestService, ApprovalRequestStatus,
    ApprovalResponse, InMemoryApprovalRequestRepository, SQLiteApprovalRequestRepository,
)

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


def request():
    return ApprovalRequest('planapproval-test', 'execution', 'correlation', 'org', 'client',
        'requester', 'service.ticket.update', 'execute', NOW, NOW + timedelta(minutes=10),
        ('approver-a', 'approver-b'))


class Authority:
    def can_approve(self, **kwargs):
        return True


def response(actor='approver-a', decision=ApprovalDecision.APPROVE):
    return ApprovalResponse('planapproval-test', 'org', actor, decision, NOW,
        'microsoft_teams', 'receipt-' + actor)


@pytest.mark.parametrize('decisions', [
    (ApprovalDecision.APPROVE, ApprovalDecision.APPROVE),
    (ApprovalDecision.APPROVE, ApprovalDecision.DENY),
])
def test_two_process_connections_cannot_accept_same_pending_request(tmp_path, decisions):
    path = tmp_path / 'approval.db'
    initial = SQLiteApprovalRequestRepository(path)
    initial.put(request())
    initial.close()
    barrier = Barrier(2)

    class ConcurrentAuthority:
        def can_approve(self, **kwargs):
            barrier.wait(timeout=5)
            return True

    def decide(index):
        repository = SQLiteApprovalRequestRepository(path)
        try:
            service = ApprovalRequestService(repository, ConcurrentAuthority())
            result = service.accept_response(response('approver-' + ('a' if index == 0 else 'b'),
                decisions[index]), now=NOW)
            return ('accepted', result.status)
        except ValueError as exc:
            assert 'no longer pending' in str(exc)
            return ('rejected', None)
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, (0, 1)))
    assert [r[0] for r in results].count('accepted') == 1
    assert [r[0] for r in results].count('rejected') == 1
    final = SQLiteApprovalRequestRepository(path)
    assert final.get('planapproval-test').status.value == next(r[1] for r in results if r[0] == 'accepted')
    final.close()


@pytest.mark.parametrize('durable', [False, True])
def test_changed_request_cannot_be_consumed_using_stale_copy(tmp_path, durable):
    repository = SQLiteApprovalRequestRepository(tmp_path/'changed.db') if durable else InMemoryApprovalRequestRepository()
    original = request()
    repository.put(original)
    repository.put(replace(original, status=ApprovalRequestStatus.DENIED))
    with pytest.raises(ValueError, match='no longer pending'):
        repository.transition_pending(original, status=ApprovalRequestStatus.APPROVED)
    assert repository.get(original.approval_id).status is ApprovalRequestStatus.DENIED
    if durable:
        repository.close()


def test_unauthorized_click_does_not_consume_legitimate_request(tmp_path):
    repository = SQLiteApprovalRequestRepository(tmp_path/'unauthorized.db')
    repository.put(request())
    service = ApprovalRequestService(repository, Authority())
    with pytest.raises(PermissionError):
        service.accept_response(response(actor='outsider'), now=NOW)
    assert repository.get('planapproval-test').status is ApprovalRequestStatus.PENDING
    assert service.accept_response(response(), now=NOW).status == 'approved'
    repository.close()


def test_repository_without_atomic_decision_primitive_fails_closed():
    class UnsafeRepository:
        def get(self, approval_id):
            return request()
        def put(self, value):
            raise AssertionError('non-atomic write must not occur')
    with pytest.raises(TypeError, match='atomic'):
        ApprovalRequestService(UnsafeRepository(), Authority()).accept_response(response(), now=NOW)


@pytest.mark.parametrize("durable", [False, True])
def test_overdue_pending_request_expires_without_signed_decision(tmp_path, durable):
    repo = (SQLiteApprovalRequestRepository(tmp_path / "expired.db")
            if durable else InMemoryApprovalRequestRepository())
    item = request()
    service = ApprovalRequestService(repo, Authority())
    service.create(item, now=NOW)
    assert service.expire_if_due(item.approval_id, now=NOW + timedelta(minutes=9)) is False
    assert repo.get(item.approval_id).status is ApprovalRequestStatus.PENDING
    assert service.expire_if_due(item.approval_id, now=NOW + timedelta(minutes=10)) is True
    assert repo.get(item.approval_id).status is ApprovalRequestStatus.EXPIRED
    assert repo.accepted_decision(item.approval_id) is None
    assert service.expire_if_due(item.approval_id, now=NOW + timedelta(minutes=20)) is False
    with pytest.raises(ValueError, match="no longer pending"):
        service.accept_response(response(), now=NOW + timedelta(minutes=20))
    if durable:
        repo.close()


@pytest.mark.parametrize("durable", [False, True])
def test_expiry_reconciliation_cannot_replace_a_signed_owner_decision(tmp_path, durable):
    repo = (SQLiteApprovalRequestRepository(tmp_path / "approved.db")
            if durable else InMemoryApprovalRequestRepository())
    item = request()
    service = ApprovalRequestService(repo, Authority())
    service.create(item, now=NOW)
    assert service.accept_response(response(), now=NOW).status == "approved"
    assert service.expire_if_due(item.approval_id, now=NOW + timedelta(days=1)) is False
    assert repo.get(item.approval_id).status is ApprovalRequestStatus.APPROVED
    assert repo.accepted_decision(item.approval_id).status == "approved"
    if durable:
        repo.close()


def test_expiry_reconciliation_rejects_stale_expected_and_missing_atomic_repository(tmp_path):
    repo = SQLiteApprovalRequestRepository(tmp_path / "raced.db")
    item = request()
    repo.put(item)
    service = ApprovalRequestService(repo, Authority())
    old_get = repo.get
    repo.get = lambda approval_id: item
    # Simulate a concurrent signed decision after the first read, before CAS.
    repo.put(replace(item, status=ApprovalRequestStatus.DENIED))
    with pytest.raises(ValueError, match="no longer pending"):
        service.expire_if_due(item.approval_id, now=NOW + timedelta(days=1))
    repo.get = old_get
    assert repo.get(item.approval_id).status is ApprovalRequestStatus.DENIED
    repo.close()

    class UnsafeRepository:
        def get(self, approval_id):
            return item
        def put(self, value):
            raise AssertionError("non-atomic put is forbidden")
    with pytest.raises(TypeError, match="atomic"):
        ApprovalRequestService(UnsafeRepository(), Authority()).expire_if_due(
            item.approval_id, now=NOW + timedelta(days=1),
        )


def test_sqlite_expiry_denies_inconsistent_pending_row_with_existing_receipt(tmp_path):
    from dataclasses import asdict
    import json
    repo = SQLiteApprovalRequestRepository(tmp_path / "receipt.db")
    item = request()
    repo.put(item)
    signed = asdict(response())
    signed["decision"] = signed["decision"].value
    signed["decided_at"] = signed["decided_at"].isoformat()
    repo._connection.execute(
        "INSERT INTO approval_decision_receipts VALUES (?, ?)",
        (item.approval_id, json.dumps(signed)),
    )
    with pytest.raises(ValueError, match="signed decision evidence"):
        ApprovalRequestService(repo, Authority()).expire_if_due(
            item.approval_id, now=NOW + timedelta(days=1),
        )
    assert repo.get(item.approval_id).status is ApprovalRequestStatus.PENDING
    repo.close()
