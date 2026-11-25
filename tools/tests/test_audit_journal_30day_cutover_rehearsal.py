from datetime import datetime,timezone,timedelta
from pathlib import Path
import os
import sqlite3

import pytest
from tools.audit_journal_30day_staging import stage_recent,cutoff_iso
from tools.audit_journal_30day_cutover_rehearsal import in_place_rehearsal
from tools.tests.test_audit_journal_30day_staging import write_fixture


def setup(tmp_path):
    now=datetime(2026,11,23,19,26,tzinfo=timezone.utc)
    old=tmp_path/"old.db"
    write_fixture(old,now)
    os.chmod(old,0o600)
    new=tmp_path/"new.db"
    stage_recent(old,new,cutoff=cutoff_iso(now))
    return now,old,new,tmp_path/"rollback.db"


def test_synthetic_inplace_retains_identity_reclaims_bytes_and_proves_rows(tmp_path):
    now,old,new,backup=setup(tmp_path)
    inode=old.stat().st_ino
    result=in_place_rehearsal(source=old,replacement=new,backup=backup,now=now)
    assert result["source_inode_preserved"]
    assert result["post_check"]=="ok"
    assert old.stat().st_ino==inode
    assert result["remaining_recent_rows"]==3
    with sqlite3.connect(old) as db:
        assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()==(3,)
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()==(5,)


def test_failed_postwrite_reverts_old_bytes_without_changing_inode(tmp_path):
    now,old,new,backup=setup(tmp_path)
    original=old.read_bytes()
    inode=old.stat().st_ino
    def fail(_):raise RuntimeError("synthetic outage")
    with pytest.raises(RuntimeError,match="synthetic outage"):
        in_place_rehearsal(source=old,replacement=new,backup=backup,now=now,fault=fail)
    assert old.read_bytes()==original and old.stat().st_ino==inode
    with sqlite3.connect(old) as db:
        assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()==(5,)


def test_expired_replacement_denied_before_mutation(tmp_path):
    now,old,new,backup=setup(tmp_path)
    previous=old.read_bytes()
    with pytest.raises(PermissionError,match="OLD_EVENT_IN_REPLACEMENT"):
        in_place_rehearsal(source=old,replacement=new,backup=backup,
            now=now+timedelta(days=2))
    assert old.read_bytes()==previous
    assert not backup.exists()


def test_existing_backup_denied_before_mutation(tmp_path):
    now,old,new,backup=setup(tmp_path)
    previous=old.read_bytes()
    backup.write_text("existing")
    with pytest.raises(PermissionError,match="CLEAN_BACKUP_REQUIRED"):
        in_place_rehearsal(source=old,replacement=new,backup=backup,now=now)
    assert backup.read_text()=="existing"
    assert old.read_bytes()==previous
