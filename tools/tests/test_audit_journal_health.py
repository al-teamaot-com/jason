from datetime import datetime,timedelta,timezone
import pytest
from tools.tests.test_audit_journal_native import native,event
from tools.audit_journal_control import atomic
from orchestrator.journal_health import full_integrity,validate_full_evidence
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
