from datetime import datetime,timedelta,timezone
import pytest
from tools.tests.test_audit_journal_native import native,event
from tools.audit_journal_control import atomic
from audit_journal_health_private_reader import full_integrity,validate_full_evidence
from orchestrator.segmented_journal import JournalUnavailable


def test_legacy_health_compatible(native):
 p,c,s=native
 result=full_integrity(p.active,profile=p,temp_root=p.archives)
 assert result["integrity"]=="ok" and result["mode"]=="legacy"
 assert validate_full_evidence({},profile=p)


def test_pending_history_cannot_pass_health(native):
 p,c,s=native;c.transition(initial=True)
 with pytest.raises(JournalUnavailable,match="UNSEALED_HISTORY"):
  full_integrity(p.active,profile=p,temp_root=p.archives)


def test_consistent_active_snapshot_restore_and_history_coverage(native):
 p,c,s=native;c.transition(initial=True);c.seal_one();s.append_event(event("new"))
 proof=full_integrity(p.active,profile=p,temp_root=p.archives)
 assert proof["active_snapshot"]==proof["active_restore"]
 assert proof["active_snapshot"]["events"]==1 and proof["closed_segments"]==1
 assert validate_full_evidence({"orchestration_journal":proof},profile=p)
 c.transition()
 with pytest.raises(JournalUnavailable):
  validate_full_evidence({"orchestration_journal":proof},profile=p)


def test_old_archive_proof_expires_until_actual_scrub(native):
 p,c,s=native;c.transition(initial=True);c.seal_one()
 catalog=p.catalog();old=datetime.now(timezone.utc)-timedelta(days=32)
 catalog["segments"][0]["proof"]["full_verified_at"]=old.isoformat()
 atomic(p.control/"catalog.json",catalog,owner=p.custody_uid)
 with pytest.raises(JournalUnavailable,match="SCRUB_DUE"):
  full_integrity(p.active,profile=p,temp_root=p.archives)
 assert c.scrub_one()["status"]=="scrubbed"
 assert full_integrity(p.active,profile=p,temp_root=p.archives)["integrity"]=="ok"


def test_corrupt_history_invalidates_full_proof(native):
 p,c,s=native;c.transition(initial=True);c.seal_one()
 proof=full_integrity(p.active,profile=p,temp_root=p.archives)
 archive=p.artifact(p.catalog()["segments"][0])
 archive.chmod(0o600)
 with pytest.raises(JournalUnavailable,match="CUSTODY"):
  validate_full_evidence({"orchestration_journal":proof},profile=p)


@pytest.mark.parametrize("date",["2026-03-08","2026-11-01"])
def test_daily_boundary_uses_new_york_calendar_across_dst(native,date):
 from zoneinfo import ZoneInfo
 p,c,s=native;c.transition(initial=True);c.seal_one()
 c.prepare_rollback();c.recovery().accept_recipe();c.reclaim(p.catalog()["segments"][0]["id"])
 c.recovery().discard_prepared()
 zone=ZoneInfo("America/New_York")
 current=datetime.fromisoformat(date+"T00:14:00").replace(tzinfo=zone)
 catalog=p.catalog();catalog["opened_at"]=(current-timedelta(hours=1)).isoformat()
 atomic(p.control/"catalog.json",catalog,owner=p.custody_uid)
 # Scrub isn't due in this fixture's actual proof; only the calendar is injected.
 assert c.maintain(now=current)["status"]=="scrub_not_due"
 assert c.maintain(now=current+timedelta(minutes=1))["mode"]=="segmented"


def test_scheduled_maintenance_cannot_authorize_initial_cutover(native):
 p,c,s=native
 with pytest.raises(JournalUnavailable,match="EXACT_RELEASE"):c.maintain()


def test_segmented_health_readers_only_use_private_scratch_when_wal_aux_absent(native):
    import os
    from pathlib import Path
    from audit_journal_fast_health import read_only_probe
    from audit_journal_health_private_reader import readonly_active_copy
    p,c,s=native
    c.transition(initial=True)
    c.seal_one()
    s.append_event(event("private-reader"))
    s.close()
    for suffix in ("-shm","-wal"):
        # The synthetic writer has closed; only the canonical active DB
        # remains before sandboxed health inspection.
        assert not os.path.lexists(str(p.active)+suffix)
    original_mode=p.active.parent.stat().st_mode & 0o777
    os.chmod(p.active.parent,0o500)
    try:
        with readonly_active_copy(p,temp_root=p.archives) as (copy,cat,digest):
            assert copy!=p.active and copy.exists()
            assert (copy.parent.stat().st_mode & 0o777)==0o700
            assert cat["mode"]=="segmented"
            assert len(digest)==64
        assert read_only_probe(p.active,profile=p) is True
        assert not os.path.lexists(str(p.active)+"-shm")
        assert not os.path.lexists(str(p.active)+"-wal")
    finally:
        os.chmod(p.active.parent,original_mode)


def test_private_reader_rejects_untrusted_live_wal_symlink(native):
    import os
    from pathlib import Path
    from audit_journal_health_private_reader import readonly_active_copy
    p,c,s=native
    c.transition(initial=True)
    c.seal_one()
    s.close()
    auxiliary=Path(str(p.active)+"-wal")
    assert not os.path.lexists(auxiliary)
    auxiliary.symlink_to(p.active)
    try:
        with pytest.raises(JournalUnavailable,match="COPY_SOURCE_IDENTITY"):
            with readonly_active_copy(p,temp_root=p.archives):
                pass
    finally:
        auxiliary.unlink()


def test_private_copy_reads_committed_wal_without_live_writer_mutation(native):
    import hashlib
    import os
    import sqlite3
    from pathlib import Path
    from audit_journal_health_private_reader import readonly_active_copy
    p,c,s=native
    c.transition(initial=True)
    c.seal_one()
    s.close()
    connection=sqlite3.connect(str(p.active),timeout=1)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal"
        connection.execute("CREATE TABLE private_health_wal_probe(i INTEGER)")
        connection.execute("INSERT INTO private_health_wal_probe VALUES(7)")
        connection.commit()
        wal=Path(str(p.active)+"-wal")
        assert wal.is_file() and wal.stat().st_size>32
        before={
            name:hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (str(p.active),str(wal))
        }
        with readonly_active_copy(p,temp_root=p.archives) as (private,_,_):
            with sqlite3.connect("file:"+str(private)+"?mode=ro",uri=True) as db:
                assert db.execute("SELECT i FROM private_health_wal_probe").fetchone()==(7,)
        after={
            name:hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (str(p.active),str(wal))
        }
        assert after==before,"Health copy must not modify live journal or WAL"
    finally:
        connection.close()


def test_private_copy_budget_failure_releases_gate_and_cleans_scratch(native,monkeypatch):
    import audit_journal_health_private_reader as mod
    p,c,s=native
    c.transition(initial=True);c.seal_one();s.close()
    original=set(p.archives.iterdir())
    monkeypatch.setattr(mod,'COPY_SECONDS',0)
    with pytest.raises(JournalUnavailable,match='COPY_BUDGET_EXCEEDED'):
        with mod.readonly_active_copy(p,temp_root=p.archives):
            pass
    assert set(p.archives.iterdir())==original
    with p.gate(exclusive=True,timeout=0.1):
        assert p.active.exists()


def test_native_full_and_both_validators_route_through_private_reader(native,monkeypatch):
    import audit_journal_health_private_reader as mod
    import audit_journal_fast_health as fast
    import audit_journal_full_health_snapshot as wrapper
    p,c,s=native
    c.transition(initial=True);c.seal_one();s.close()
    proof=mod.full_integrity(p.active,profile=p,temp_root=p.archives)
    assert proof['active_snapshot']==proof['active_restore']
    assert mod.validate_full_evidence({'orchestration_journal':proof},profile=p,temp_root=p.archives)
    assert fast.read_only_probe(p.active,profile=p)
    # A source-level import contract guards against silently returning one
    # native entry to the frozen reader with the original WAL sandbox defect.
    from pathlib import Path
    for name in ['audit_journal_fast_health.py','audit_journal_operational_health.py','audit_journal_full_health_snapshot.py']:
        content=(Path('tools')/name).read_text()
        assert 'from audit_journal_health_private_reader import' in content
        assert 'from orchestrator.journal_health import' not in content
