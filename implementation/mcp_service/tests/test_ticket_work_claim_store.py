from pathlib import Path

import pytest

from jason_mcp.ticket_work_claim_store import TicketWorkClaimStore


def test_claim_store_preserves_original_state_and_marks_returned(tmp_path: Path) -> None:
    store = TicketWorkClaimStore(tmp_path / "claims.json")
    staged = store.stage({"id": 123, "queueID": 8, "status": 1})
    assert staged.state == "pending"

    claimed = store.mark_claimed(123)
    assert claimed.state == "claimed"
    assert claimed.original_queue_id == 8
    assert claimed.original_status_id == 1

    returned = store.mark_returned(
        123,
        reason_class="human_review",
        blocker_fingerprint="needs-onsite-usb",
    )
    assert returned.state == "returned"
    assert returned.original_queue_id == 8
    assert returned.original_status_id == 1
    assert returned.handoff_reason_class == "human_review"
    assert returned.blocker_fingerprint == "needs-onsite-usb"


def test_claim_store_blocks_reclaim_when_blocker_is_unchanged(tmp_path: Path) -> None:
    store = TicketWorkClaimStore(tmp_path / "claims.json")
    store.stage({"id": 123, "queueID": 8, "status": 1})
    store.mark_claimed(123)
    store.mark_returned(
        123,
        reason_class="provider_blocked",
        blocker_fingerprint="provider-403",
    )

    with pytest.raises(ValueError, match="BLOCKER_UNCHANGED"):
        store.stage(
            {"id": 123, "queueID": 8, "status": 1},
            blocker_fingerprint="provider-403",
        )


def test_claim_store_allows_reclaim_when_blocker_changes(tmp_path: Path) -> None:
    store = TicketWorkClaimStore(tmp_path / "claims.json")
    store.stage({"id": 123, "queueID": 8, "status": 1})
    store.mark_claimed(123)
    store.mark_returned(
        123,
        reason_class="provider_blocked",
        blocker_fingerprint="provider-403",
    )

    next_claim = store.stage(
        {"id": 123, "queueID": 8, "status": 1},
        blocker_fingerprint="provider-restored",
    )
    assert next_claim.state == "pending"


def test_claim_store_blocks_reclaim_after_human_review_until_blocker_changes(tmp_path: Path) -> None:
    store = TicketWorkClaimStore(tmp_path / "claims.json")
    store.stage({"id": 321, "queueID": 8, "status": 1})
    store.mark_claimed(321)
    store.mark_returned(
        321,
        reason_class="human_review",
        blocker_fingerprint="security-review-required",
    )

    with pytest.raises(ValueError, match="BLOCKER_UNCHANGED"):
        store.stage(
            {"id": 321, "queueID": 29682833, "status": 8},
            blocker_fingerprint="security-review-required",
        )

    next_claim = store.stage(
        {"id": 321, "queueID": 29682833, "status": 8},
        blocker_fingerprint="technician-returned-to-jason",
    )
    assert next_claim.state == "pending"


def test_claim_store_marks_completion_idempotently(tmp_path: Path) -> None:
    store = TicketWorkClaimStore(tmp_path / "claims.json")
    store.stage({"id": 777, "queueID": 8, "status": 1})
    store.mark_claimed(777)

    completed = store.mark_completed(
        777,
        resolution_case_id="autotask-ticket-777-resolution-v1",
    )
    assert completed.state == "completed"
    assert completed.resolution_case_id == "autotask-ticket-777-resolution-v1"
    assert completed.completed_at

    repeated = store.mark_completed(
        777,
        resolution_case_id="autotask-ticket-777-resolution-v1",
    )
    assert repeated == completed

    with pytest.raises(ValueError, match="COMPLETION_CONFLICT"):
        store.mark_completed(
            777,
            resolution_case_id="different-resolution-case",
        )
