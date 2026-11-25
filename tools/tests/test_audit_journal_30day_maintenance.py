import sqlite3
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path

import pytest
from tools.audit_journal_30day_staging import stage_recent,cutoff_iso
from tools.audit_journal_30day_maintenance import (
    exact_cutoff, prepare_incremental_maintenance,expire_offline,
    permitted_nonproduction_database
)
from tools.tests.test_audit_journal_30day_staging import write_fixture


def test_offline_conversion_rolling_reclaim_and_source_immutable(tmp_path):
    now=datetime(2026,11,23,19,26,tzinfo=timezone.utc)
    src=tmp_path/"source.db"
    write_fixture(src,now)
    original=src.read_bytes()
    dest=tmp_path/"stage.db"
    stage_recent(src,dest,cutoff=cutoff_iso(now))
    converted=prepare_incremental_maintenance(dest)
    assert converted["maintenance_auto_vacuum"]=="INCREMENTAL"
    first=expire_offline(dest,now=now+timedelta(hours=3))
    assert first["deleted_expired_events"]==1
    assert first["remaining_old_events"]==0
    assert first["retained_events"]==2
    second=expire_offline(dest,now=now+timedelta(hours=3))
    assert second["deleted_expired_events"]==0
    assert second["retained_events"]==2
    assert src.read_bytes()==original
    with sqlite3.connect(dest) as db:
        assert db.execute("PRAGMA auto_vacuum").fetchone()==(2,)
        assert db.execute("PRAGMA quick_check").fetchone()==("ok",)
        assert {r[0] for r in db.execute("SELECT event_id FROM orchestration_events")}=={"id3","id4"}


def test_reject_unknown_schema_and_missing_autovacuum(tmp_path):
    p=tmp_path/"unsupported.sqlite3"
    db=sqlite3.connect(p)
    db.execute("CREATE TABLE orchestration_events(event_id TEXT)")
    db.close()
    os.chmod(p,0o600)
    with pytest.raises(PermissionError,match="INCREMENTAL_VACUUM_REQUIRED"):
        expire_offline(p,now=datetime.now(timezone.utc))


def test_reject_unbounded_calls(tmp_path):
    p=tmp_path/"recent.sqlite3"
    write_fixture(p,datetime.now(timezone.utc))
    os.chmod(p,0o600)
    with pytest.raises(PermissionError,match="BOUNDED_BATCH"):
        expire_offline(p,now=datetime.now(timezone.utc),limit=1000000)


def test_timezone_aware_retention():
    with pytest.raises(PermissionError,match="TZ_AWARE_CLOCK"):
        exact_cutoff(datetime(2026,11,23,14,26))
    assert exact_cutoff(datetime(2026,11,23,14,26,tzinfo=timezone(timedelta(hours=-5))))=="2026-10-24T19:26:00+00:00"


def test_reject_world_readable_file(tmp_path):
    p=tmp_path/"test.db"
    p.write_bytes(b"x")
    os.chmod(p,0o644)
    with pytest.raises(PermissionError,match="PRIVATE_WRITABLE_STAGING_CUSTODY"):
        permitted_nonproduction_database(p)
