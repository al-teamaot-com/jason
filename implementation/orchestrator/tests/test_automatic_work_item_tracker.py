from pathlib import Path

from orchestrator.automatic_work_item_tracker import AutomaticWorkItemTracker


def _tracker(tmp_path: Path) -> AutomaticWorkItemTracker:
    support = tmp_path / "SUPPORT.md"
    todo = tmp_path / "TODO.md"
    support.write_text("# Support\n\n| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |\n| --- | --- | --- | --- | --- | --- |\n", encoding="utf-8")
    todo.write_text("# TODO\n", encoding="utf-8")
    return AutomaticWorkItemTracker(support, todo)


def test_support_item_created_then_deduplicated(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    first = tracker.record_support(
        title="Datto component output retrieval failed",
        summary="Expected governed output retrieval failed.",
        evidence="Job completed but output retrieval failed.",
    )
    second = tracker.record_support(
        title="Datto component output retrieval failed",
        summary="Same failure on another request.",
    )
    assert first.created is True
    assert second.created is False
    assert second.item_id == first.item_id
    text = tracker.support_path.read_text(encoding="utf-8")
    assert text.count(first.item_id) == 1


def test_todo_item_created_then_deduplicated(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    first = tracker.record_todo(
        title="Read Datto RMM site variables",
        summary="Allow Jason to determine whether required site variables exist.",
    )
    second = tracker.record_todo(
        title="Read Datto RMM site variables",
        summary="Requested again.",
    )
    assert first.created is True
    assert second.created is False
    assert second.item_id == first.item_id
    assert "already tracked" in second.user_notice.lower()


def test_cross_list_duplicate_prefers_existing_item(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    support = tracker.record_support(title="Example capability", summary="Failed.")
    todo_attempt = tracker.record_todo(title="Example capability", summary="New request.")
    assert support.list_name == "Support"
    assert todo_attempt.created is False
    assert todo_attempt.item_id == support.item_id
    assert todo_attempt.list_name == "Support"

def test_cross_list_duplicate_is_reported_instead_of_recreated(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    todo = tracker.record_todo(
        title="Read Datto RMM site variables",
        summary="Allow Jason to determine whether required site variables exist.",
    )
    support_attempt = tracker.record_support(
        title="Read Datto RMM site variables",
        summary="User asked again during troubleshooting.",
    )
    assert support_attempt.created is False
    assert support_attempt.item_id == todo.item_id
    assert support_attempt.list_name == "To Do"
    assert todo.item_id not in tracker.support_path.read_text(encoding="utf-8")
