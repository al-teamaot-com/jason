"""Regression coverage for the read-only autonomy status projection."""
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from jason_mcp import server


@pytest.mark.parametrize(
    "eligible,occupancy,selected,activity_age,scan_age,heartbeat,expected,cycles",
    [
        (8, 0, 1, 5, 5, "running", "BACKLOGGED", 0),
        (8, 0, 0, 10, 5, "running", "BACKLOGGED", 0),
        (8, 3, 0, 10, 5, "running", "BACKLOGGED", 0),
        (8, 0, 0, 75, 5, "running", "BACKLOGGED", 1),
        (8, 0, 0, 180, 5, "running", "STALLED", 2),
        (8, 3, 0, 180, 5, "running", "STALLED", 2),
        (8, 0, 0, 5, 180, "running", "UNKNOWN", 0),
        (8, 0, 0, 10, 5, "failed", "DEGRADED", 0),
        (0, 0, 0, 180, 5, "idle", "CAUGHT_UP", 0),
    ],
)
def test_scan_status(tmp_path, monkeypatch, eligible, occupancy, selected,
                     activity_age, scan_age, heartbeat, expected, cycles):
    now = datetime.now(timezone.utc)
    def stamp(age):
        return (now - timedelta(seconds=age)).isoformat()

    path = tmp_path / "status.sqlite3"
    with sqlite3.connect(path) as c:
        c.execute("""CREATE TABLE autonomy_operational_work(
            ticket_id INTEGER PRIMARY KEY,ticket_number TEXT,playbook_id TEXT,
            phase TEXT,updated_at TEXT)""")
        c.execute("""CREATE TABLE autonomy_ticket_scan_cycle(
            scanned_at TEXT,eligible INTEGER,active_slots INTEGER,selected INTEGER)""")
        for i in range(3):
            c.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES(?,?,?,?)",
                      (stamp(scan_age + i * 60), eligible, occupancy,
                       selected if i == 0 else 0))
        c.execute("CREATE TABLE autonomy_ticket_activity(occurred_at TEXT)")
        c.execute("INSERT INTO autonomy_ticket_activity VALUES(?)", (stamp(activity_age),))
        c.execute("""CREATE TABLE autonomy_ticket_worker_heartbeat(
            singleton_id INTEGER,last_started_at TEXT,last_completed_at TEXT,state TEXT)""")
        c.execute("INSERT INTO autonomy_ticket_worker_heartbeat VALUES(1,?,?,?)",
                  (stamp(scan_age), stamp(scan_age), heartbeat))
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(path))
    monkeypatch.setenv("JASON_AUTONOMY_STATUS_MAX_SCAN_AGE_SECONDS", "120")
    status = server._autonomous_ticket_work_snapshot()
    assert status["processing_state"] == expected
    assert status["consecutive_no_progress_cycles"] == cycles
    assert status["active_count"] == 0
    assert status["eligible_now"] == eligible
    assert status["active_slots"] == occupancy
    assert status["selected_last_scan"] == selected
