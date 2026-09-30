from __future__ import annotations

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
            (3001, "TA1", "active", "test", "diagnosing", "2026-09-30T03:00:00+00:00", "active"),
        ]
    )
    connection.executemany(
        "INSERT INTO autonomy_operational_work VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(db))
    snapshot = server._autonomous_ticket_work_snapshot()

    assert snapshot["status"] == "succeeded"
    assert snapshot["items_bounded"] is True
    assert snapshot["item_limit"] == 20
    assert len(snapshot["items"]) == 20
    assert snapshot["active_count"] == 1
    assert snapshot["waiting_count"] == 2
    assert snapshot["blocked_count"] == 25
    assert snapshot["items"][0]["state"] == "ACTIVE"
