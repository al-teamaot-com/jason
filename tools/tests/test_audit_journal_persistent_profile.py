from pathlib import Path
import json
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore
from tools.audit_journal_control import atomic
from tools.tests.test_audit_journal_native import native

def test_public_profile_can_be_recreated_without_losing_persistent_catalog(native,tmp_path):
 p,c,s=native
 runtime=tmp_path/"runtime";runtime.mkdir(mode=0o700)
 profile=runtime/"profile.json"
 value={"schema_version":"1.0","enabled":True,"adoption":"fixture",**c.profile_arguments()}
 atomic(profile,value,owner=p.custody_uid)
 loaded=JournalProfile.load(profile,fixture=True)
 assert loaded.control==p.control and loaded.control!=runtime
 c.transition(initial=True);c.seal_one()
 profile.unlink();runtime.rmdir()
 assert (p.control/"catalog.json").is_file()
 runtime.mkdir(mode=0o700);atomic(profile,value,owner=p.custody_uid)
 restored=SegmentedOrchestrationEventStore(JournalProfile.load(profile,fixture=True))
 try:assert restored.get("before").event_id=="before"
 finally:restored.close()
