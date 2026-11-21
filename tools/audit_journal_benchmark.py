#!/usr/bin/env python3
"""Bounded disposable fan-out benchmark; never accepts a production database."""
from __future__ import annotations
import argparse,json,math,os,resource,time
from datetime import datetime,timezone
from pathlib import Path
from orchestrator.event_store import OrchestrationEvent,SQLiteOrchestrationEventStore
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore,fingerprint
from orchestrator import journal_sql
from tools.audit_journal_control import atomic

def event(identifier,execution,correlation):
 return OrchestrationEvent(event_id=identifier,event_type="fixture.observer",execution_id=execution,
 correlation_id=correlation,organization_id="fixture",principal_id="fixture",capability_name="fixture.read",
 stage="observed",payload={"fixture":"x"*512})
def elapsed(operation):
 start=time.monotonic();value=operation();return (time.monotonic()-start)*1000,value
def p99(values):return sorted(values)[max(0,math.ceil(len(values)*0.99)-1)]
def scenario(base,segments,samples):
 uid=os.geteuid();base.mkdir(mode=0o700)
 for name in ("control","archives","pending"): (base/name).mkdir(mode=0o700)
 p=JournalProfile(active=base/"active.sqlite3",control=base/"control",archives=base/"archives",
 pending=base/"pending",custody_uid=uid,writer_uid=uid,fixture=True)
 lock=p.control/"handoff.lock";lock.touch();lock.chmod(0o644);os.chown(lock,uid,uid)
 records=[]
 for index in range(segments):
  identifier=f"{index:032x}";path=p.archives/(identifier+".sqlite3")
  store=SQLiteOrchestrationEventStore(path)
  for row in range(16):store.append_event(event(f"{index}-{row}",f"execution-{index}","fanout"))
  store.close();journal_sql.checkpoint(path);proof=journal_sql.proof(path)
  filters=journal_sql.filters(path,p.archives,identifier,16)
  journal_sql.validate_filters(path,p.archives,filters)
  for item in filters.values():
   file=p.archives/item["file"];os.chown(file,uid,uid);file.chmod(0o440)
   item["fingerprint"]=fingerprint(file.stat())
  os.chown(path,uid,uid);path.chmod(0o440)
  records.append({"id":identifier,"file":path.name,"state":"sealed","fingerprint":fingerprint(path.stat()),
   "filters":filters,"proof":{**proof,"restore_verified":False,"benchmark_fixture_only":True}})
 journal_sql.create_active(p.active,"benchmark");os.chown(p.active,uid,uid)
 atomic(p.control/"catalog.json",{"schema_version":"1.0","generation":1,"epoch":"benchmark",
  "mode":"segmented","segments":records},owner=uid)
 store=SegmentedOrchestrationEventStore(p);writes=[];reads=[]
 for index in range(samples):
  ms,_=elapsed(lambda:store.append_event(event(f"new-{index}","live","live")));writes.append(ms)
  ms,found=elapsed(lambda:store.get(f"{index%segments}-0"));reads.append(ms);assert found is not None
 wide,events=elapsed(lambda:store.list_by_correlation("fanout"))
 assert len(events)==segments*16 and len(store._cache)<=p.cached_archives
 store.close()
 return {"segments":segments,"samples":samples,"append_p99_ms":round(p99(writes),3),
  "get_p99_ms":round(p99(reads),3),"wide_history_ms":round(wide,3),"wide_history_events":len(events)}
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--workspace",type=Path,required=True)
 parser.add_argument("--samples",type=int,default=30);args=parser.parse_args()
 path=args.workspace.absolute()
 if path.exists() or not str(path).startswith(("/tmp/","/srv/jason/archive/engineering-artifacts/")):
  raise SystemExit("DISPOSABLE_NEW_BENCHMARK_WORKSPACE_REQUIRED")
 if not 10<=args.samples<=100:raise SystemExit("BOUNDED_SAMPLE_COUNT_REQUIRED")
 path.mkdir(mode=0o700)
 out={"fixture_only":True,"production_ready":False,"production_data_used":False,
      "observed_at":datetime.now(timezone.utc).isoformat(),"results":[]}
 for count in (1,32,128,365):out["results"].append(scenario(path/str(count),count,args.samples))
 out["maximum_rss_kib"]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
 (path/"result.json").write_text(json.dumps(out,indent=2)+"\n")
 print(json.dumps(out,indent=2))
if __name__=="__main__":main()
