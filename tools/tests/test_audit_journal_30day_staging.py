import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from tools.audit_journal_30day_staging import (
    CREATE, INDEXES, COLUMNS, cutoff_iso, stage_recent,
)


def write_fixture(path, clock):
    db=sqlite3.connect(path)
    db.execute(CREATE)
    for stmt in INDEXES:
        db.execute(stmt)
    for i,delta in enumerate((60,31,30,10,0)):
        timestamp=(clock-timedelta(days=delta)).isoformat()
        db.execute("INSERT INTO orchestration_events ("+",".join(COLUMNS)+") VALUES ("+
             ",".join("?" for _ in COLUMNS)+")",
           (f"id{i}","1.0","orchestration.event",f"ex{i}","corr","org","principal","capability",
            "approved",'{"test":true}',timestamp))
    db.commit();db.close()


def test_only_recent_rows_staged_and_source_unchanged(tmp_path):
    now=datetime(2026,11,23,19,26,tzinfo=timezone.utc)
    src=tmp_path/"source.sqlite3"
    write_fixture(src,now)
    original=src.read_bytes()
    dst=tmp_path/"recent.sqlite3"
    result=stage_recent(src,dst,cutoff=cutoff_iso(now))
    assert src.read_bytes()==original
    assert result["source_snapshot_total"]==5
    assert result["source_snapshot_old_excluded"]==2
    assert result["destination_row_count"]==3
    assert result["destination_older_than_cutoff"]==0
    assert result["source_was_read_only"] is True
    assert result["production_cutover_performed"] is False
    con=sqlite3.connect(dst)
    assert {r[0] for r in con.execute("SELECT event_id FROM orchestration_events")} == {"id2","id3","id4"}
    assert con.execute("PRAGMA quick_check").fetchone()==("ok",)
    assert sorted(row[1] for row in con.execute("PRAGMA index_list(orchestration_events)"))==[
      "ix_orchestration_correlation","ix_orchestration_execution","sqlite_autoindex_orchestration_events_1"]
    con.close()


def test_existing_destination_denied(tmp_path):
    now=datetime.now(timezone.utc)
    src=tmp_path/"source.sqlite3"
    write_fixture(src,now)
    dst=tmp_path/"recent.sqlite3"
    dst.write_text("do not overwrite")
    with pytest.raises(PermissionError,match="SOURCE_OR_DESTINATION"):
        stage_recent(src,dst,cutoff=cutoff_iso(now))
    assert dst.read_text()=="do not overwrite"


def test_30day_boundary_is_utc_and_fixed():
    now=datetime(2026,11,23,14,26,tzinfo=timezone(timedelta(hours=-5)))
    assert cutoff_iso(now)=="2026-10-24T19:26:00+00:00"


def test_source_missing_denied(tmp_path):
    with pytest.raises(PermissionError,match="SOURCE_NOT_REGULAR"):
        stage_recent(tmp_path/"missing.db",tmp_path/"staged.db",cutoff=cutoff_iso(datetime.now(timezone.utc)))
