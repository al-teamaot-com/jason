from datetime import datetime, timezone

import pytest

from .attention_scheduler import WorkItem, WorkLedger, WorkState
from .work_resume import LedgerWorkResumePort


def fixed_now():
    return datetime(2026, 9, 25, 12, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("state", [WorkState.WAITING, WorkState.APPROVAL_PENDING])
def test_resumable_work_becomes_available_and_clears_wake_state(state):
    ledger = WorkLedger([
        WorkItem(
            "T1",
            state,
            next_check_at=fixed_now(),
            wake_on="device_online",
            queue_reconciliation_required=True,
            reason="waiting",
        )
    ])
    resume = LedgerWorkResumePort(ledger, now=fixed_now)

    assert resume.resume("T1", reason="targeted read complete") is True

    item = ledger.get("T1")
    assert item.state is WorkState.AVAILABLE
    assert item.next_check_at is None
    assert item.wake_on is None
    assert item.queue_reconciliation_required is False
    assert item.reason == "targeted read complete"
    assert item.updated_at == fixed_now()


@pytest.mark.parametrize(
    "state",
    [
        WorkState.AVAILABLE,
        WorkState.CANDIDATE,
        WorkState.ACTIVE,
        WorkState.BLOCKED,
        WorkState.VERIFYING,
        WorkState.COMPLETE,
        WorkState.ESCALATED,
    ],
)
def test_stale_wake_never_resurrects_non_waiting_work(state):
    ledger = WorkLedger([WorkItem("T1", state, reason="existing")])
    resume = LedgerWorkResumePort(ledger, now=fixed_now)

    assert resume.resume("T1", reason="stale wake") is False
    assert ledger.get("T1").state is state
    assert ledger.get("T1").reason == "existing"


def test_unknown_work_item_fails_closed():
    resume = LedgerWorkResumePort(WorkLedger(), now=fixed_now)
    with pytest.raises(KeyError):
        resume.resume("missing", reason="targeted read complete")
