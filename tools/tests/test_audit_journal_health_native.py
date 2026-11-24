from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import pytest
import audit_journal_operational_health as full
import audit_journal_fast_health as fast
import audit_journal_full_health_snapshot as wrapper
from orchestrator import journal_health
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
 monkeypatch.setattr(journal_health,"full_integrity",verify)
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
 monkeypatch.setattr(journal_health,"validate_full_evidence",reject)
 assert fast.full_proof(path,fast.DATABASES,datetime.now(timezone.utc)) is None
 assert not wrapper.full_pass(evidence(),0)

def test_invalid_activation_path_cannot_enable_journal_health(monkeypatch):
 monkeypatch.setenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE","/tmp/unreviewed.json")
 with pytest.raises(JournalUnavailable,match="FIXED_PROFILE"):
  journal_health.enabled()


def test_native_health_sandbox_allows_only_journal_wal_shm():
    from tools.audit_journal_install import health_dropins
    from tools import audit_journal_release_scope as scope

    raw = health_dropins(scope)
    fast = raw["jason-openclaw-authority-health.service"].decode()
    full = raw["jason-openclaw-authority-full-integrity.service"].decode()
    auxiliary = "-" + str(scope.ACTIVE) + "-shm"
    assert "ReadWritePaths=" + auxiliary + "\n" in fast
    assert ("ReadWritePaths=/var/lib/jason/openclaw "
            "/srv/jason/archive/authority-health-scratch " + auxiliary + "\n") in full
    for unit in (fast, full):
        assert "ReadOnlyPaths=" + str(scope.BASE) + "\n" in unit
        assert "Environment=JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE=" + str(scope.PROFILE) in unit
        assert "ReadWritePaths=" + str(scope.ACTIVE.parent) + "\n" not in unit
        assert "-" + str(scope.ACTIVE) + "-shm" in unit
        assert "-" + str(scope.ACTIVE) + "-wal" not in unit
        assert "ReadWritePaths=/var/lib/jason " not in unit


def test_native_health_sandbox_auxiliary_paths_are_optional_and_not_wildcards():
    from tools.audit_journal_install import health_dropins
    from tools import audit_journal_release_scope as scope

    for name, raw in health_dropins(scope).items():
        directives = [line.removeprefix("ReadWritePaths=").split()
                      for line in raw.decode().splitlines()
                      if line.startswith("ReadWritePaths=") and line != "ReadWritePaths="]
        assert len(directives) == 1, name
        paths = directives[0]
        optional = {"-" + str(scope.ACTIVE) + "-shm"}
        assert optional.issubset(paths), name
        assert "-" + str(scope.ACTIVE) + "-wal" not in paths, name
        assert not any(p == str(scope.ACTIVE.parent) or p == str(scope.ACTIVE)
                       for p in paths), name
        assert all("*" not in p and "?" not in p for p in paths), name
