from pathlib import Path

import pytest

from jason_runtime.ticket_split_runtime import (
    SQLiteTicketSplitStore,
    TicketSplitError,
    TicketSplitExecutor,
    TicketSplitRequest,
    TicketSplitTarget,
)


class Actions:
    def __init__(self):
        self.calls = []
        self.next_id = 1000

    def execute(self, scope, capability, arguments):
        self.calls.append((scope, capability, arguments))
        self.next_id += 1
        return {
            "data": {
                "itemId": self.next_id,
                "jasonVerification": {
                    "readbackVerified": True,
                    "ticketId": self.next_id,
                    "verifiedFields": ["companyID", "title"],
                },
            }
        }


class Scope:
    pass


def request():
    return TicketSplitRequest(
        source_ticket_id=123,
        source_ticket_number="T20261003.0001",
        company_id=208,
        queue_id=29683489,
        priority=1,
        status=1,
        issue_type=23,
        sub_issue_type=497,
        ticket_type=3,
        targets=(
            TicketSplitTarget(
                target_key="uid-a",
                title="KB5129195 - PC-A",
                description="Missing KB5129195 on PC-A",
                configuration_item_id=10,
            ),
            TicketSplitTarget(
                target_key="uid-b",
                title="KB5129195 - PC-B",
                description="Missing KB5129195 on PC-B",
                configuration_item_id=11,
            ),
        ),
    )


def test_split_creates_one_verified_child_per_target(tmp_path: Path):
    actions = Actions()
    store = SQLiteTicketSplitStore(tmp_path / "split.sqlite3")
    executor = TicketSplitExecutor(actions=actions, store=store)

    result = executor.execute(scope=Scope(), request=request())

    assert result.created_count == 2
    assert result.reused_count == 0
    assert len(result.children) == 2
    assert [capability for _, capability, _ in actions.calls] == [
        "service.ticket.create",
        "service.ticket.create",
    ]
    first = actions.calls[0][2]["payload"]
    assert first["configurationItemID"] == 10
    assert first["queueID"] == 29683489
    assert "Source ticket: T20261003.0001" in first["description"]
    assert "Split marker: JASON-SPLIT:T20261003.0001:" in first["description"]
    store.close()


def test_split_retry_reuses_persisted_children_without_duplicate_creates(tmp_path: Path):
    actions = Actions()
    store = SQLiteTicketSplitStore(tmp_path / "split.sqlite3")
    executor = TicketSplitExecutor(actions=actions, store=store)

    first = executor.execute(scope=Scope(), request=request())
    second = executor.execute(scope=Scope(), request=request())

    assert first.created_count == 2
    assert second.created_count == 0
    assert second.reused_count == 2
    assert [child.child_ticket_id for child in second.children] == [
        child.child_ticket_id for child in first.children
    ]
    assert len(actions.calls) == 2
    store.close()


def test_split_fails_closed_without_provider_readback(tmp_path: Path):
    class Unverified:
        def execute(self, scope, capability, arguments):
            return {"data": {"itemId": 1001}}

    store = SQLiteTicketSplitStore(tmp_path / "split.sqlite3")
    executor = TicketSplitExecutor(actions=Unverified(), store=store)

    with pytest.raises(TicketSplitError, match="readback"):
        executor.execute(scope=Scope(), request=request())

    assert store.list_for_source(123) == ()
    store.close()


def test_split_requires_at_least_two_unique_targets():
    with pytest.raises(ValueError, match="at least two"):
        TicketSplitRequest(
            source_ticket_id=123,
            source_ticket_number="T20261003.0001",
            company_id=208,
            queue_id=29683489,
            priority=1,
            targets=(
                TicketSplitTarget(
                    target_key="uid-a",
                    title="one",
                    description="one",
                    configuration_item_id=10,
                ),
            ),
        )
