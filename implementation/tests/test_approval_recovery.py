from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.approval_recovery import (
    ApprovalRecoveryDisposition,
    ApprovalRecoveryRecord,
    InMemoryApprovalRecoveryLedger,
    SQLiteApprovalRecoveryLedger,
)


def record(**changes) -> ApprovalRecoveryRecord:
    values = dict(
        recovery_id="recovery-1",
        approval_id="approval-1",
        organization_id="org-a",
        request_id="request-1",
        correlation_id="corr-1",
        capability="autotask.ticket.update",
        decided_by="identity-admin",
        disposition=ApprovalRecoveryDisposition.CONFIRMED_NOT_EXECUTED,
        reason="Provider evidence confirms no mutation occurred.",
        decided_at=datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc),
        evidence_references=("artifact://org-a/evidence-1",),
        fresh_authority_context_id=None,
    )
    values.update(changes)
    return ApprovalRecoveryRecord(**values)


def test_retry_requires_fresh_authority_context() -> None:
    with pytest.raises(PermissionError, match="fresh JKD-001"):
        record(disposition=ApprovalRecoveryDisposition.RETRY_AUTHORIZED).validate()


def test_non_retry_cannot_smuggle_authority_context() -> None:
    with pytest.raises(ValueError, match="only valid for retry"):
        record(fresh_authority_context_id="ctx-1").validate()


def test_in_memory_ledger_is_append_once_and_idempotent() -> None:
    ledger = InMemoryApprovalRecoveryLedger()
    original = record()
    ledger.record(original)
    ledger.record(original)
    assert ledger.get(original.recovery_id) == original

    with pytest.raises(ValueError, match="conflicting"):
        ledger.record(record(reason="different decision"))


def test_sqlite_recovery_survives_restart(tmp_path) -> None:
    path = str(tmp_path / "recovery.db")
    first = SQLiteApprovalRecoveryLedger(path)
    first.initialize()
    original = record()
    first.record(original)

    second = SQLiteApprovalRecoveryLedger(path)
    second.initialize()
    assert second.get(original.recovery_id) == original
    second.record(original)


def test_sqlite_rejects_conflicting_recovery_id(tmp_path) -> None:
    ledger = SQLiteApprovalRecoveryLedger(str(tmp_path / "recovery.db"))
    ledger.initialize()
    ledger.record(record())
    with pytest.raises(ValueError, match="conflicting"):
        ledger.record(record(organization_id="org-b"))


def test_retry_record_persists_fresh_authority(tmp_path) -> None:
    ledger = SQLiteApprovalRecoveryLedger(str(tmp_path / "recovery.db"))
    ledger.initialize()
    retry = record(
        recovery_id="recovery-retry-1",
        disposition=ApprovalRecoveryDisposition.RETRY_AUTHORIZED,
        reason="Evidence confirms prior execution did not occur; retry approved.",
        fresh_authority_context_id="ctx-fresh-2",
    )
    ledger.record(retry)
    assert ledger.get(retry.recovery_id) == retry
