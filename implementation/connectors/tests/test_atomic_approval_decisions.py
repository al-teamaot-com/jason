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
