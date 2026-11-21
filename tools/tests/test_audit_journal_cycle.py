"""A real disposable database completes dependent maintenance in one invocation."""
from tools.tests.test_audit_journal_native import native,event
from tools.audit_journal_control import read_control


def test_scheduled_cycle_rotates_seals_reconstructs_and_reclaims_in_order(native):
 p,c,s=native
 c.transition(initial=True);s.append_event(event("post-cutover"));c.seal_one()
 c.prepare_rollback();c.recovery().accept_recipe();c.recovery().discard_prepared()
 epoch=p.catalog()["epoch"]
 c._json(c.private/"first-scheduled-rollover.json",{"before_epoch":epoch,"completed":False},0o400)
 result=c.maintenance_cycle()
 assert result["initial_scheduled_rollover_verified"] is True
 assert p.catalog()["epoch"]!=epoch and c.status()["pending"]==0
 assert len(list(p.pending.iterdir()))==0
 assert {row.event_id for row in s.list_by_execution("one")}=={"before","post-cutover"}
 record=read_control(c.private/"first-scheduled-rollover.json",p.custody_uid,0o400)
 assert record["after_epoch"]==p.catalog()["epoch"] and record["completed"]
 again=c.maintenance_cycle()
 assert p.catalog()["epoch"]==record["after_epoch"]
 assert again["initial_scheduled_rollover_verified"]


def test_initial_operational_barriers_do_not_contaminate_sealed_schema(native):
 from orchestrator import journal_sql
 p,c,s=native
 journal_sql.admission_barrier(p.active,True,block_invoking=True)
 c.transition(initial=True);s.append_event(event("after-drain"))
 c.seal_one();c.prepare_rollback();c.recovery().accept_recipe()
 assert c.recovery().extend_recipe()["status"]=="verified_reconstruction_recipe_extended"
 assert s.get("after-drain").event_id=="after-drain"


def test_legacy_publication_stays_paused_until_consumers_are_restored(native):
 import sqlite3,pytest
 from orchestrator import journal_sql
 from orchestrator.event_store import SQLiteOrchestrationEventStore
 p,c,s=native
 c.transition(initial=True);s.append_event(event("new"));c.seal_one()
 c._json(c.private/"release-plan.json",{"fixture_only":True},0o400)
 c.prepare_rollback();c.finish_rollback()
 old=SQLiteOrchestrationEventStore(p.active)
 try:
  with pytest.raises(ValueError,match="already exists") as blocked:
   old.append_event(event("blocked",kind="orchestration.request.received"))
  assert isinstance(blocked.value.__cause__,sqlite3.IntegrityError)
  assert "MAINTENANCE" in str(blocked.value.__cause__) and old.get("blocked") is None
  journal_sql.admission_barrier(p.active,False)
  old.append_event(event("restored",kind="orchestration.request.received"))
  assert old.get("new").event_id=="new" and old.get("restored").event_id=="restored"
 finally:old.close()
