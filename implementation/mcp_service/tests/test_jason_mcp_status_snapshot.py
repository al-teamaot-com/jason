from __future__ import annotations

import json
import sqlite3

from jason_mcp import server


def test_autonomy_work_snapshot_bounds_items_but_counts_full_state(tmp_path, monkeypatch):
    db = tmp_path / "work.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute(
        """
        CREATE TABLE autonomy_operational_work(
            ticket_id INTEGER PRIMARY KEY,
            ticket_number TEXT,
            title TEXT,
            playbook_id TEXT,
            phase TEXT,
            updated_at TEXT,
            last_reason TEXT
        )
        """
    )
    rows = []
    for index in range(25):
        rows.append(
            (
                1000 + index,
                f"T{index}",
                f"blocked {index}",
                "test",
                "blocked",
                f"2026-09-30T00:{index:02d}:00+00:00",
                "blocked",
            )
        )
    rows.extend(
        [
            (2001, "TW1", "waiting", "test", "waiting_device_access:check", "2026-09-30T02:00:00+00:00", "waiting"),
            (2002, "TW2", "approval", "test", "approval_pending", "2026-09-30T02:01:00+00:00", "waiting"),
            (2003, "TW3", "patch approval", "test", "waiting_patch_approval", "2026-09-30T02:02:00+00:00", "waiting"),
            (2004, "TW4", "patch window", "test", "waiting_patch_window", "2026-09-30T02:03:00+00:00", "waiting"),
            (2005, "TW5", "authority", "test", "waiting_client_notification_authority", "2026-09-30T02:04:00+00:00", "waiting"),
            (2006, "TW6", "recheck", "test", "waiting_recheck:provider", "2026-09-30T02:05:00+00:00", "waiting"),
            (3001, "TA1", "active", "test", "diagnosing", "2026-09-30T03:00:00+00:00", "active"),
        ]
    )
    connection.executemany(
        "INSERT INTO autonomy_operational_work VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    connection.execute(
        """
        CREATE TABLE autonomy_ticket_scan_cycle(
            cycle_id TEXT PRIMARY KEY,
            scanned_at TEXT NOT NULL,
            evaluated INTEGER,
            eligible INTEGER,
            active_slots INTEGER,
            selected INTEGER,
            waiting_device INTEGER,
            human_review INTEGER
        )
        """
    )
    connection.execute(
        "INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?,?,?,?,?)",
        (
            "cycle-1",
            "2026-09-30T03:01:00+00:00",
            32,
            1,
            2,
            1,
            6,
            0,
        ),
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(db))
    snapshot = server._autonomous_ticket_work_snapshot()

    assert snapshot["status"] == "succeeded"
    assert snapshot["items_bounded"] is True
    assert snapshot["item_limit"] == 5
    assert len(snapshot["items"]) == 5
    assert snapshot["active_count"] == 1
    assert snapshot["waiting_count"] == 6
    assert snapshot["blocked_count"] == 25
    assert snapshot["eligible_now"] == 1
    assert snapshot["processing_state"] == "DEGRADED"
    assert snapshot["scan_evidence_present"] is True
    assert snapshot["items"][0]["state"] == "ACTIVE"
    assert all("title" not in item for item in snapshot["items"])
    assert all("reason" not in item for item in snapshot["items"])
    assert len(json.dumps(snapshot, separators=(",", ":"))) < 2500


def _create_status_db(tmp_path, *, phase_rows, eligible, active_slots, selected):
    db = tmp_path / "status.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute(
        """
        CREATE TABLE autonomy_operational_work(
            ticket_id INTEGER PRIMARY KEY,
            ticket_number TEXT,
            title TEXT,
            playbook_id TEXT,
            phase TEXT,
            updated_at TEXT,
            last_reason TEXT
        )
        """
    )
    if phase_rows:
        connection.executemany(
            "INSERT INTO autonomy_operational_work VALUES (?,?,?,?,?,?,?)",
            phase_rows,
        )
    connection.execute(
        """
        CREATE TABLE autonomy_ticket_scan_cycle(
            cycle_id TEXT PRIMARY KEY,
            scanned_at TEXT NOT NULL,
            evaluated INTEGER,
            eligible INTEGER,
            active_slots INTEGER,
            selected INTEGER
        )
        """
    )
    connection.execute(
        "INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?,?,?)",
        ("cycle-1", "2026-11-03T09:45:00+00:00", len(phase_rows), eligible, active_slots, selected),
    )
    connection.commit()
    connection.close()
    return db


def test_autonomy_work_snapshot_reports_caught_up_only_with_complete_zero_eligible_scan(tmp_path, monkeypatch):
    db = _create_status_db(
        tmp_path,
        phase_rows=[],
        eligible=0,
        active_slots=2,
        selected=0,
    )
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(db))

    snapshot = server._autonomous_ticket_work_snapshot()

    assert snapshot["processing_state"] == "CAUGHT_UP"
    assert snapshot["eligible_now"] == 0
    assert snapshot["active_count"] == 0
    assert snapshot["last_successful_scan_at"] == "2026-11-03T09:45:00+00:00"


def test_autonomy_work_snapshot_reports_stalled_for_eligible_idle_capacity(tmp_path, monkeypatch):
    db = _create_status_db(
        tmp_path,
        phase_rows=[
            (
                3001,
                "TSTALL",
                "stalled",
                "test",
                "waiting_device_access:claim",
                "2026-11-03T09:44:00+00:00",
                "waiting",
            )
        ],
        eligible=1,
        active_slots=2,
        selected=0,
    )
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(db))

    snapshot = server._autonomous_ticket_work_snapshot()

    assert snapshot["processing_state"] == "STALLED"
    assert snapshot["eligible_now"] == 1
    assert snapshot["active_count"] == 0
    assert snapshot["active_slots"] == 2


def test_autonomy_work_snapshot_reports_unknown_without_scan_evidence(tmp_path, monkeypatch):
    db = tmp_path / "unknown.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute(
        """
        CREATE TABLE autonomy_operational_work(
            ticket_id INTEGER PRIMARY KEY,
            ticket_number TEXT,
            title TEXT,
            playbook_id TEXT,
            phase TEXT,
            updated_at TEXT,
            last_reason TEXT
        )
        """
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(db))

    snapshot = server._autonomous_ticket_work_snapshot()

    assert snapshot["processing_state"] == "UNKNOWN"
    assert snapshot["scan_evidence_present"] is False
    assert snapshot["eligible_now"] is None
