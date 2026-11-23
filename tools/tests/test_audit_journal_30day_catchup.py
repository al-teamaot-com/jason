from datetime import datetime,timezone,timedelta
import sqlite3

from tools.audit_journal_30day_staging import stage_recent,cutoff_iso
from tools.audit_journal_30day_catchup import update_candidate
from tools.tests.test_audit_journal_30day_staging import write_fixture


def test_live_recent_events_are_merged_without_touching_source(tmp_path):
    now=datetime(2026,11,23,19,26,tzinfo=timezone.utc)
    src=tmp_path/"source.sqlite3"
    write_fixture(src,now)
    dst=tmp_path/"copy.sqlite3"
    base=stage_recent(src,dst,cutoff=cutoff_iso(now))
    source_count_before=5
    db=sqlite3.connect(src)
    db.execute(
        "INSERT INTO orchestration_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("new","1.0","orchestration.event","execution","correlation","org","principal",
         "capability","approved","{}",(now+timedelta(seconds=1)).isoformat()))
    db.execute(
        "INSERT INTO orchestration_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("oldnew","1.0","orchestration.event","execution","correlation","org","principal",
         "capability","approved","{}",(now-timedelta(days=60)).isoformat()))
    db.commit()
    db.close()
    result=update_candidate(src,dst,min_source_rowid=base["source_snapshot_max_rowid"],
        cutoff=cutoff_iso(now))
    assert result["rows_added"]==1
    assert result["destination_count"]==4
    assert result["source_snapshot_max_rowid"]==7
    assert result["production_cutover_performed"] is False
    reader=sqlite3.connect(dst)
    assert {x[0] for x in reader.execute("SELECT event_id FROM orchestration_events")}=={
        "id2","id3","id4","new"}
    assert reader.execute("PRAGMA quick_check").fetchone()==("ok",)
    reader.close()
    source=sqlite3.connect(src)
    assert source.execute("SELECT COUNT(*) FROM orchestration_events").fetchone()[0]==7
    source.close()


def test_cutoff_removes_newly_expired_stage_rows(tmp_path):
    now=datetime(2026,11,23,19,26,tzinfo=timezone.utc)
    src=tmp_path/"source.sqlite3"
    write_fixture(src,now)
    dst=tmp_path/"copy.sqlite3"
    base=stage_recent(src,dst,cutoff=cutoff_iso(now))
    result=update_candidate(src,dst,min_source_rowid=base["source_snapshot_max_rowid"],
        cutoff=cutoff_iso(now+timedelta(hours=1)))
    assert result["rows_added"]==0
    assert result["expired_rows_removed_from_staging"]==1
    assert result["destination_count"]==2
    src_db=sqlite3.connect(src)
    assert src_db.execute("SELECT COUNT(*) FROM orchestration_events").fetchone()[0]==5
    src_db.close()
