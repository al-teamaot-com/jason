from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from jason_runtime.ticket_worker_health import status

NOW=datetime(2026,11,17,14,0,0,tzinfo=timezone.utc)

def db(tmp_path:Path)->Path:
    p=tmp_path/"work.sqlite3"
    con=sqlite3.connect(p)
    con.execute(
        "CREATE TABLE autonomy_ticket_worker_heartbeat("
        "singleton_id INTEGER PRIMARY KEY,last_started_at TEXT,"
        "last_completed_at TEXT,state TEXT)"
    )
    con.execute(
        "CREATE TABLE autonomy_ticket_scan_cycle(scanned_at TEXT)"
    )
    con.commit();con.close()
    return p

def set_heartbeat(path:Path,*,started=None,completed=None,state="idle"):
    con=sqlite3.connect(path)
    con.execute(
        "INSERT OR REPLACE INTO autonomy_ticket_worker_heartbeat "
        "(singleton_id,last_started_at,last_completed_at,state) VALUES(1,?,?,?)",
        (started,completed,state))
    con.commit();con.close()

def test_recent_completed_scan_is_healthy(tmp_path):
    p=db(tmp_path)
    set_heartbeat(p,completed=(NOW-timedelta(seconds=75)).isoformat())
    out=status(db=p,interval_seconds=60,now=NOW)
    assert out["status"]=="ok"
    assert out["reason"]=="recent_completed_scan"

def test_stale_completed_scan_is_unhealthy(tmp_path):
    p=db(tmp_path)
    set_heartbeat(p,completed=(NOW-timedelta(seconds=181)).isoformat())
    out=status(db=p,interval_seconds=60,now=NOW)
    assert out["status"]=="degraded"
    assert out["reason"]=="completion_stale"

def test_active_scan_within_bounded_window_is_healthy(tmp_path):
    p=db(tmp_path)
    set_heartbeat(p,started=(NOW-timedelta(seconds=240)).isoformat(),
                  completed=(NOW-timedelta(seconds=280)).isoformat(),
                  state="running")
    assert status(db=p,interval_seconds=60,now=NOW)["status"]=="ok"

def test_stalled_or_invalid_running_scan_is_unhealthy(tmp_path):
    p=db(tmp_path)
    set_heartbeat(p,started=(NOW-timedelta(seconds=301)).isoformat(),
                  state="running")
    assert status(db=p,interval_seconds=60,now=NOW)["reason"]=="scan_stalled"
    set_heartbeat(p,started="not-a-time",state="running")
    assert status(db=p,interval_seconds=60,now=NOW)["reason"]=="scan_started_at_invalid"

def test_missing_database_is_unhealthy(tmp_path):
    out=status(db=tmp_path/"missing.sqlite3",interval_seconds=60,now=NOW)
    assert out=={"status":"degraded","reason":"heartbeat_missing"}
