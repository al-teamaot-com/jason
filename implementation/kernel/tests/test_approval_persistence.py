from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from kernel.identity_authority import ApprovalRecord, SQLiteApprovalRepository, SQLiteIdentityAuthorityStore


NOW = datetime(2026, 8, 9, 17, 30, tzinfo=timezone.utc)


def approval(**overrides) -> ApprovalRecord:
    values = dict(
        approval_id="apr-immutable-1",
        request_id="execution-1",
        capability="microsoft.resource.execute",
        organization_id="org-a",
        client_id="client-a",
        requested_by="requester-1",
        status="approved",
        decided_by="approver-1",
        decided_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    values.update(overrides)
    return ApprovalRecord(**values)


def repository(tmp_path):
    store = SQLiteIdentityAuthorityStore(tmp_path / "authority.db")
    return store, SQLiteApprovalRepository(store)


def test_formal_approval_survives_reopen(tmp_path):
    store, repo = repository(tmp_path)
    record = approval()
    repo.put(record)
    store.close()

    reopened = SQLiteIdentityAuthorityStore(tmp_path / "authority.db")
    assert SQLiteApprovalRepository(reopened).get(record.approval_id) == record
    reopened.close()


def test_identical_approval_retry_is_idempotent(tmp_path):
    store, repo = repository(tmp_path)
    record = approval()
    repo.put(record)
    repo.put(record)

    assert repo.get(record.approval_id) == record
    count = store.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    assert count == 1
    store.close()


def test_conflicting_approval_id_reuse_fails_closed(tmp_path):
    store, repo = repository(tmp_path)
    original = approval()
    repo.put(original)

    with pytest.raises(ValueError, match="conflicting JKD-001 approval_id reuse"):
        repo.put(replace(original, decided_by="different-approver"))

    assert repo.get(original.approval_id) == original
    store.close()


def test_approval_id_cannot_be_reused_across_organization_scope(tmp_path):
    store, repo = repository(tmp_path)
    original = approval()
    repo.put(original)

    with pytest.raises(ValueError, match="conflicting JKD-001 approval_id reuse"):
        repo.put(replace(original, organization_id="org-b"))

    assert repo.get(original.approval_id).organization_id == "org-a"
    store.close()


def test_approval_id_cannot_be_reused_for_different_request_or_capability(tmp_path):
    store, repo = repository(tmp_path)
    original = approval()
    repo.put(original)

    for conflict in (
        replace(original, request_id="execution-2"),
        replace(original, capability="datto.resource.execute"),
        replace(original, requested_by="requester-2"),
        replace(original, status="denied"),
    ):
        with pytest.raises(ValueError, match="conflicting JKD-001 approval_id reuse"):
            repo.put(conflict)

    assert repo.get(original.approval_id) == original
    store.close()
