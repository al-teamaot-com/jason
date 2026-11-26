"""Recovery of derived work never deletes a live source or a published archive."""
import json,sqlite3
import pytest
from pathlib import Path
from tools.tests.test_audit_journal_native import native,event
from orchestrator import journal_sql
from orchestrator.segmented_journal import JournalUnavailable
from orchestrator.event_store import SQLiteOrchestrationEventStore

def test_unreferenced_prepared_copy_is_recovered_but_current_plan_is_retained(native):
 p,c,s=native;c.transition(initial=True);s.append_event(event("after"));c.seal_one();c.prepare_rollback()
 plan=json.loads(c.rollback.read_bytes());target=Path(plan["target"])
 c.cleanup_abandoned_work();assert target.exists()
 c.rollback.unlink()  # models power loss before the plan pointer was published
 recovered=c.cleanup_abandoned_work()
 assert recovered["prepared_temporary_copies_cleaned"]==1 and not target.exists()
 assert {r.event_id for r in s.list_by_execution("one")}=={"before","after"}
 assert all(p.artifact(r).exists() for r in p.catalog()["segments"])


def test_temporary_work_with_an_open_sqlite_handle_is_never_unlinked(native):
 p,c,s=native;job=c._job();target=job/"work.sqlite3"
 held=sqlite3.connect(target);held.execute("CREATE TABLE fixture(n INTEGER)");held.commit()
 try:
  with pytest.raises(JournalUnavailable,match="HANDLE_STILL_OPEN"):c.cleanup_abandoned_work()
  assert target.exists()
 finally:held.close()
 c.cleanup_abandoned_work();assert not job.exists() and s.get("before")


def test_pending_handoff_work_is_not_garbage_collected(native):
 p,c,s=native
 def fault(at):
  if at=="transition_intent":raise RuntimeError("power-loss")
 c.fault=fault
 with pytest.raises(RuntimeError):c.transition(initial=True)
 intent=json.loads(c.intent.read_bytes());new=Path(intent["target"])
 c.cleanup_abandoned_work();assert new.exists()
 c.fault=lambda _:None;c.recover()
 assert s.get("before").event_id=="before"


def test_seeded_reconstruction_checks_each_supplied_source_content_hash(native,tmp_path):
 p,c,s=native;c.transition(initial=True);c.seal_one()
 path=p.artifact(p.catalog()["segments"][0]);actual=journal_sql.proof(path)
 invalid={**actual,"content_sha256":"0"*64}
 with pytest.raises(JournalUnavailable,match="CONTENT_PARITY"):
  journal_sql.rebuild([path],tmp_path/"wrong.sqlite3",[invalid])
 built=journal_sql.rebuild([path],tmp_path/"correct.sqlite3",[actual])
 assert built["content_sha256"]==actual["content_sha256"] and built["events"]==1
