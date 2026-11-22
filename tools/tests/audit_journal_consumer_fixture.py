import os,sys,json,sqlite3,hashlib
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from orchestrator.event_store import SQLiteOrchestrationEventStore,OrchestrationEvent,_SCHEMA
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore,META_SCHEMA,fingerprint

root=Path("/tmp/journal-smoke");root.mkdir(mode=0o700)
uid=os.geteuid();assert uid==1000
for name in ("control","archives","pending"): (root/name).mkdir(mode=0o700)
def event(identifier,kind="fixture.observer"):
 return OrchestrationEvent(event_id=identifier,event_type=kind,execution_id="execution",
 correlation_id="correlation",organization_id="fixture",principal_id="fixture",capability_name="fixture.read",
 stage="completed" if kind.endswith("completed") else "observed",payload={"fixture":True})
history=root/"archives/history.sqlite3";old=SQLiteOrchestrationEventStore(history)
old.append_event(event("before"));old.close()
db=sqlite3.connect(history);db.execute("PRAGMA journal_mode=DELETE");db.close()
os.chown(history,uid,uid);history.chmod(0o440)
active=root/"active.sqlite3";db=sqlite3.connect(active)
db.executescript(_SCHEMA+META_SCHEMA);db.execute("INSERT INTO audit_journal_meta VALUES ('fixture')")
db.execute("PRAGMA journal_mode=WAL");db.commit();db.close();active.chmod(0o600);os.chown(active,uid,uid)
gate=root/"control/handoff.lock";gate.touch();gate.chmod(0o644)
catalog=root/"control/catalog.json"
catalog.write_text(json.dumps({"schema_version":"1.0","mode":"segmented","generation":1,"epoch":"fixture",
 "segments":[{"id":"history","file":history.name,"state":"sealed","fingerprint":fingerprint(history.stat()),
 "filters":{},"proof":{"fixture_only":True}}]}));catalog.chmod(0o444)
p=JournalProfile(active=active,control=root/"control",archives=root/"archives",pending=root/"pending",
 custody_uid=uid,writer_uid=uid,fixture=True)
store=SegmentedOrchestrationEventStore(p)
store.append_event(event("received","orchestration.request.received"))
store.append_event(event("invoking","orchestration.capability.invoking"))
store.append_event(event("done","orchestration.capability.completed"))
assert store.get("before") is not None and store.get("done") is not None
assert len(store.list_by_execution("execution"))==4
store.close()
import orchestrator.event_store as module
assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()==os.environ["EXPECTED_EVENT_STORE_SHA"]
print(json.dumps({"fixture_only":True,"writer_uid":uid,"base_image_role":os.environ["FIXTURE_ROLE"],
 "module_hash_verified":True,"archived_and_current_reads":True,"outcome_promotion":True,
 "provider_contacted":False}))
