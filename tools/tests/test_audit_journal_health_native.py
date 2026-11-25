from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import pytest
import audit_journal_operational_health as full
import audit_journal_fast_health as fast
import audit_journal_full_health_snapshot as wrapper
from orchestrator import journal_health
import audit_journal_health_private_reader as native_reader
from orchestrator.segmented_journal import JournalUnavailable,PROFILE

def evidence():
 return {"status":"pass","failures":[],"snapshot_source_exit_code":0,
 "provider_contacted":False,"provider_credentials_used":False,
 "files":{key:{"path":str(path),"present":True,"mode":"0o600","integrity":"ok"}
          for key,path in fast.DATABASES.items()},
 "backup_restore_proof":{"backup_integrity":"ok","restore_integrity":"ok",
 "backup_mode":"0o600","restore_mode":"0o600","counts_match":True},
 "trusted_key_registry":{"present":True,"mode":"0o600","active_records":1},
 "delegations":{"expired_active_records":0}}

def test_explicit_full_adapter_keeps_legacy_default(tmp_path,monkeypatch):
 monkeypatch.delenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE",raising=False)
 path=tmp_path/"data.sqlite3"
 with sqlite3.connect(path) as db:db.execute("CREATE TABLE test(value)")
 assert full.orchestration_integrity(path,tmp_path)=={"integrity":"ok"}

def test_new_full_adapter_routes_to_real_journal_verifier(tmp_path,monkeypatch):
 monkeypatch.setenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE",str(PROFILE))
 called=[]
 def verify(path,**kwargs):
  called.append((path,kwargs));return {"integrity":"ok","catalog_sha256":"fixture"}
 monkeypatch.setattr(native_reader,"full_integrity",verify)
 result=full.orchestration_integrity(tmp_path/"active",tmp_path)
 assert result["catalog_sha256"]=="fixture"
 assert called==[(tmp_path/"active",{"temp_root":tmp_path})]

def test_new_fast_and_wrapper_require_coverage_when_adopted(tmp_path,monkeypatch):
 path=tmp_path/"full.json";path.write_text(json.dumps(evidence()));path.chmod(0o600)
 monkeypatch.delenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE",raising=False)
 assert fast.full_proof(path,fast.DATABASES,datetime.now(timezone.utc)) is not None
 assert wrapper.full_pass(evidence(),0)
 monkeypatch.setenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE",str(PROFILE))
 def reject(value):raise JournalUnavailable("JOURNAL_HISTORY_NOT_COVERED")
 monkeypatch.setattr(native_reader,"validate_full_evidence",reject)
 assert fast.full_proof(path,fast.DATABASES,datetime.now(timezone.utc)) is None
 assert not wrapper.full_pass(evidence(),0)

def test_invalid_activation_path_cannot_enable_journal_health(monkeypatch):
 monkeypatch.setenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE","/tmp/unreviewed.json")
 with pytest.raises(JournalUnavailable,match="FIXED_PROFILE"):
  journal_health.enabled()
