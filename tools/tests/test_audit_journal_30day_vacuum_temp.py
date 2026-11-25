import os
import sqlite3
from pathlib import Path

import pytest
from tools.audit_journal_30day_maintenance import prepare_incremental_maintenance


def test_strict_archive_conversion_denies_default_root_tmp(tmp_path,monkeypatch):
    archive=tmp_path/"archive"
    archive.mkdir(mode=0o700)
    candidate=archive/"candidate.sqlite3"
    con=sqlite3.connect(candidate)
    con.execute("CREATE TABLE orchestration_events(event_id TEXT, occurred_at TEXT)")
    con.commit()
    con.close()
    os.chmod(candidate,0o600)
    monkeypatch.delenv("SQLITE_TMPDIR",raising=False)
    # Rehearse path separation without changing the actual production archive.
    import tools.audit_journal_30day_maintenance as m
    monkeypatch.setattr(m,"ARCHIVE",archive)
    with pytest.raises(PermissionError,match="VACUUM_TEMP_MUST_BE_PRIVATE_SECOND_DRIVE"):
        prepare_incremental_maintenance(candidate,must_be_on_archive=True)
    assert candidate.exists()


def test_strict_archive_conversion_pins_private_same_drive_temp(tmp_path,monkeypatch):
    archive=tmp_path/"archive"
    archive.mkdir(mode=0o700)
    temp=archive/"tmp"
    temp.mkdir(mode=0o700)
    db=archive/"candidate.sqlite3"
    con=sqlite3.connect(db)
    con.execute("CREATE TABLE orchestration_events(event_id TEXT, occurred_at TEXT)")
    con.commit()
    con.close()
    os.chmod(db,0o600)
    import tools.audit_journal_30day_maintenance as m
    monkeypatch.setattr(m,"ARCHIVE",archive)
    monkeypatch.setenv("SQLITE_TMPDIR",str(temp))
    monkeypatch.setattr(m.os,"statvfs",lambda _:type("Stats",(),{"f_bavail":1000000000,"f_frsize":4096})())
    result=prepare_incremental_maintenance(db,must_be_on_archive=True)
    assert result["maintenance_auto_vacuum"]=="INCREMENTAL"
