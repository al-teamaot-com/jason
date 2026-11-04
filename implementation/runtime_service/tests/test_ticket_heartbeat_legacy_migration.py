"""Non-destructive migration for the real pre-supervisor ticket heartbeat schema."""
from __future__ import annotations

import sqlite3

import pytest

from jason_runtime.autonomy_worker_runtime import SQLiteOperationalWorkStore, OperationalAutonomyError
from jason_runtime.autonomy_worker_supervisor import read_worker_heartbeat


def legacy(path):
    c = sqlite3.connect(path)
    c.execute(
        "CREATE TABLE autonomy_ticket_worker_heartbeat ("
        "singleton_id INTEGER PRIMARY KEY, "
        "heartbeat_at TEXT NOT NULL, phase TEXT NOT NULL, cycle_id TEXT)"
    )
    row = (1, "2026-11-02T17:49:53.488787+00:00",
           "reconcile_complete", "scan-historical")
    c.execute("INSERT INTO autonomy_ticket_worker_heartbeat VALUES (?,?,?,?)", row)
    c.commit()
    c.close()
    return row


def test_migrates_actual_legacy_schema_and_keeps_all_evidence(tmp_path):
    path = tmp_path / "operational.sqlite3"
    original = legacy(path)
    store = SQLiteOperationalWorkStore(path)
    connection = sqlite3.connect(path)
    assert connection.execute(
        "SELECT * FROM autonomy_ticket_worker_heartbeat_legacy_v1"
    ).fetchone() == original
    assert connection.execute(
        "SELECT * FROM autonomy_ticket_worker_heartbeat"
    ).fetchall() == []
    store.mark_scan_started(started_at="2026-11-04T23:30:00+00:00")
    assert read_worker_heartbeat(path) == {
        "last_started_at": "2026-11-04T23:30:00+00:00",
        "last_completed_at": None,
        "scan_in_progress": True,
    }
    store.mark_scan_failed(finished_at="2026-11-04T23:31:00+00:00")
    assert read_worker_heartbeat(path)["last_completed_at"] == "2026-11-04T23:31:00+00:00"
    assert connection.execute(
        "SELECT * FROM autonomy_ticket_worker_heartbeat_legacy_v1"
    ).fetchone() == original
    connection.close()


def test_idempotent_reopen_retains_new_heartbeat_and_legacy_archive(tmp_path):
    path = tmp_path / "operational.sqlite3"
    original = legacy(path)
    s1 = SQLiteOperationalWorkStore(path)
    s1.mark_scan_started(started_at="2026-11-04T23:30:00+00:00")
    s2 = SQLiteOperationalWorkStore(path)
    assert read_worker_heartbeat(path)["scan_in_progress"] is True
    with sqlite3.connect(path) as c:
        assert c.execute(
            "SELECT * FROM autonomy_ticket_worker_heartbeat_legacy_v1"
        ).fetchone() == original
        assert c.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='autonomy_ticket_worker_heartbeat_legacy_v1'"
        ).fetchone() == (1,)


def test_native_new_schema_remains_unmodified(tmp_path):
    path = tmp_path / "operational.sqlite3"
    store = SQLiteOperationalWorkStore(path)
    store.mark_scan_started(started_at="2026-11-04T23:30:00+00:00")
    SQLiteOperationalWorkStore(path)
    with sqlite3.connect(path) as c:
        assert c.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='autonomy_ticket_worker_heartbeat_legacy_v1'"
        ).fetchone() == (0,)
    assert read_worker_heartbeat(path)["scan_in_progress"] is True


def test_unknown_schema_fails_closed_without_renaming(tmp_path):
    path = tmp_path / "operational.sqlite3"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE autonomy_ticket_worker_heartbeat (singleton_id INTEGER, arbitrary TEXT)")
        c.execute("INSERT INTO autonomy_ticket_worker_heartbeat VALUES (1,'preserve')")
    with pytest.raises(OperationalAutonomyError, match="unrecognized"):
        SQLiteOperationalWorkStore(path)
    with sqlite3.connect(path) as c:
        assert c.execute(
            "SELECT * FROM autonomy_ticket_worker_heartbeat"
        ).fetchone() == (1, "preserve")


def test_legacy_archive_conflict_fails_closed_without_modifying_history(tmp_path):
    path = tmp_path / "operational.sqlite3"
    original = legacy(path)
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE autonomy_ticket_worker_heartbeat_legacy_v1 (proof TEXT)")
        c.execute("INSERT INTO autonomy_ticket_worker_heartbeat_legacy_v1 VALUES ('untouched')")
    with pytest.raises(OperationalAutonomyError, match="refusing overwrite"):
        SQLiteOperationalWorkStore(path)
    with sqlite3.connect(path) as c:
        assert c.execute(
            "SELECT * FROM autonomy_ticket_worker_heartbeat"
        ).fetchone() == original
        assert c.execute(
            "SELECT * FROM autonomy_ticket_worker_heartbeat_legacy_v1"
        ).fetchone() == ("untouched",)
