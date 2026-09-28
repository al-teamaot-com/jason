from __future__ import annotations

import stat
from datetime import datetime, timezone

import pytest

from orchestrator import OrchestrationEvent, SQLiteOrchestrationEventStore


def event(*, event_id: str, execution_id: str = "exec-1", correlation_id: str = "corr-1", second: int = 0) -> OrchestrationEvent:
    return OrchestrationEvent(
        event_id=event_id,
        event_type="orchestration.test",
        execution_id=execution_id,
        correlation_id=correlation_id,
        organization_id="aot",
        principal_id="operator-al",
        capability_name="autotask.ticket.search",
        stage="received",
        payload={"sequence": second},
        occurred_at=datetime(2026, 8, 6, 17, 0, second, tzinfo=timezone.utc),
    )


def test_event_payload_is_immutable_and_detached() -> None:
    source = {"nested": {"value": 1}}
    stored = OrchestrationEvent(
        event_type="orchestration.test",
        execution_id="exec-1",
        correlation_id="corr-1",
        organization_id="aot",
        principal_id="operator-al",
        capability_name="autotask.ticket.search",
        stage="received",
        payload=source,
    )

    source["nested"]["value"] = 2

    assert stored.payload["nested"]["value"] == 1
    with pytest.raises(TypeError):
        stored.payload["new"] = "value"  # type: ignore[index]


def test_append_and_query_in_chronological_order(tmp_path) -> None:
    path = tmp_path / "events.sqlite3"
    store = SQLiteOrchestrationEventStore(path)
    try:
        store.append_event(event(event_id="event-2", second=2))
        store.append_event(event(event_id="event-1", second=1))

        events = store.list_by_execution("exec-1")

        assert tuple(item.event_id for item in events) == ("event-1", "event-2")
        assert store.get("event-1") == events[0]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        store.close()


def test_events_survive_store_restart(tmp_path) -> None:
    path = tmp_path / "events.sqlite3"
    first = SQLiteOrchestrationEventStore(path)
    first.append_event(event(event_id="event-1"))
    first.close()

    second = SQLiteOrchestrationEventStore(path)
    try:
        restored = second.get("event-1")
        assert restored is not None
        assert restored.execution_id == "exec-1"
        assert restored.payload["sequence"] == 0
    finally:
        second.close()


def test_duplicate_event_id_fails_closed() -> None:
    store = SQLiteOrchestrationEventStore()
    item = event(event_id="event-1")
    try:
        store.append_event(item)
        with pytest.raises(ValueError, match="already exists"):
            store.append_event(item)
    finally:
        store.close()


def test_query_boundaries_do_not_cross_execution_or_correlation() -> None:
    store = SQLiteOrchestrationEventStore()
    try:
        store.append_event(event(event_id="event-1"))
        store.append_event(
            event(
                event_id="event-2",
                execution_id="exec-2",
                correlation_id="corr-2",
            )
        )

        assert tuple(item.event_id for item in store.list_by_execution("exec-1")) == ("event-1",)
        assert tuple(item.event_id for item in store.list_by_correlation("corr-2")) == ("event-2",)
    finally:
        store.close()


def test_audit_sink_adapter_requires_canonical_context() -> None:
    store = SQLiteOrchestrationEventStore()
    try:
        store.append(
            "orchestration.request.received",
            {
                "execution_id": "exec-1",
                "correlation_id": "corr-1",
                "organization_id": "aot",
                "principal_id": "operator-al",
                "capability_name": "autotask.ticket.search",
                "stage": "received",
            },
        )

        events = store.list_by_execution("exec-1")
        assert len(events) == 1
        assert events[0].event_type == "orchestration.request.received"
    finally:
        store.close()


def test_file_store_uses_wal_and_extended_busy_timeout(tmp_path) -> None:
    path = tmp_path / "events.sqlite3"
    store = SQLiteOrchestrationEventStore(path)
    try:
        journal_mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = store._connection.execute("PRAGMA busy_timeout").fetchone()[0]
        assert str(journal_mode).casefold() == "wal"
        assert int(busy_timeout) >= 30_000
    finally:
        store.close()


def test_memory_store_preserves_memory_journal_mode() -> None:
    store = SQLiteOrchestrationEventStore()
    try:
        journal_mode = store._connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal_mode).casefold() == "memory"
    finally:
        store.close()


def test_two_file_store_connections_wait_through_short_write_contention(tmp_path) -> None:
    import threading
    import time

    path = tmp_path / "events.sqlite3"
    first = SQLiteOrchestrationEventStore(path)
    second = SQLiteOrchestrationEventStore(path)
    errors = []

    try:
        first._connection.execute("BEGIN IMMEDIATE")
        first._connection.execute(
            """
            INSERT INTO orchestration_events(
                event_id, schema_version, event_type, execution_id,
                correlation_id, organization_id, principal_id,
                capability_name, stage, payload, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "held-event", "1.0", "orchestration.test", "exec-held",
                "corr-held", "aot", "operator-al", "autotask.ticket.search",
                "received", '{"sequence":0}',
                datetime(2026, 8, 6, 17, 0, 0, tzinfo=timezone.utc).isoformat(),
            ),
        )

        def append_second() -> None:
            try:
                second.append_event(event(event_id="event-after-lock", execution_id="exec-2"))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        worker = threading.Thread(target=append_second)
        worker.start()
        time.sleep(0.25)
        first._connection.commit()
        worker.join(timeout=5)

        assert not worker.is_alive()
        assert errors == []
        assert second.get("event-after-lock") is not None
    finally:
        first.close()
        second.close()
