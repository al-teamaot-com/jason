"""Bounded durable receipts for already-invoked outcomes, in the active DB.

A receipt is data evidence, never approval or permission to retry a provider.
Canonical promotion reuses the original event ID and bytes after historical
uniqueness checks. Keeping the receipt first also survives a failing archive mmap.
"""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json,time
from .segmented_journal import need,JournalCapacityExceeded

POST_INVOCATION=frozenset(("orchestration.information_release.decided",
                          "orchestration.capability.completed","orchestration.capability.failed"))
TERMINAL=frozenset(("orchestration.capability.completed","orchestration.capability.failed"))
PENDING_GRACE_SECONDS=60

def encoded(values):return json.dumps(list(values),separators=(",",":"),allow_nan=False)
def receipt_id(values):return sha256(encoded(values).encode()).hexdigest()

class OutcomeReceipts:
 def __init__(self,store):self.store=store

 def stage(self,catalog,event,values,charge):
  if catalog["mode"]=="legacy" or event.event_type not in POST_INVOCATION:return False
  with self.store._active(catalog,write=True) as db:
   db.execute("BEGIN IMMEDIATE")
   pending=db.execute("SELECT remaining_bytes,provider_started FROM audit_journal_inflight "
                      "WHERE execution_id=?",(event.execution_id,)).fetchone()
   if pending is None or pending["provider_started"]!=1:return False
   key=receipt_id(values)
   if db.execute("SELECT 1 FROM audit_journal_pending_outcomes WHERE receipt_id=?",(key,)).fetchone():
    return True
   if pending["remaining_bytes"]<charge:
    raise JournalCapacityExceeded("JOURNAL_OUTCOME_RESERVE_EXHAUSTED")
   db.execute("INSERT INTO audit_journal_pending_outcomes VALUES (?,?,?,?,?)",
              (key,event.event_id,event.execution_id,encoded(values),time.time()))
   db.execute("UPDATE audit_journal_inflight SET remaining_bytes=remaining_bytes-? WHERE execution_id=?",
              (charge,event.execution_id))
  return True

 def reconcile(self,maximum=100):
  need(1<=maximum<=1000,"JOURNAL_RECONCILE_BATCH_BOUND")
  store=self.store;done=0
  with store._mutex,store.profile.gate():
   catalog=store.profile.catalog();store._refresh(catalog)
   with store._active(catalog) as db:
    rows=list(db.execute("SELECT receipt_id,values_json FROM audit_journal_pending_outcomes "
                         "ORDER BY rowid LIMIT ?",(maximum,)))
  from .event_store import OrchestrationEvent
  for row in rows:
   values=json.loads(row["values_json"])
   event=OrchestrationEvent(event_id=values[0],schema_version=values[1],event_type=values[2],
     execution_id=values[3],correlation_id=values[4],organization_id=values[5],principal_id=values[6],
     capability_name=values[7],stage=values[8],payload=json.loads(values[9]),
     occurred_at=datetime.fromisoformat(values[10]))
   existing=store.get(event.event_id)
   if existing is not None:
    need(existing==event,"JOURNAL_PENDING_OUTCOME_IDENTITY_CONFLICT")
    with store._mutex,store.profile.gate():
     catalog=store.profile.catalog()
     with store._active(catalog,write=True) as db:
      db.execute("DELETE FROM audit_journal_pending_outcomes WHERE receipt_id=?",(row["receipt_id"],))
      if event.event_type in TERMINAL or event.stage.casefold()=="denied":
       db.execute("DELETE FROM audit_journal_inflight WHERE execution_id=?",(event.execution_id,))
   else:store.append_event(event)
   with store._mutex,store.profile.gate():
    catalog=store.profile.catalog()
    with store._active(catalog) as db:
     remains=db.execute("SELECT 1 FROM audit_journal_pending_outcomes WHERE receipt_id=?",
                        (row["receipt_id"],)).fetchone()
   if remains is not None:break
   done+=1
  return {"reconciled":done,"provider_invocations":0}
