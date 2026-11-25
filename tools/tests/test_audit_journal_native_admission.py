"""Native authority and cache freshness are checked without touching live files."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from tools import audit_journal_release_scope as scope
from tools import audit_journal_release_executor as release
from orchestrator.segmented_journal import JournalUnavailable


def report(seconds):
 return {"status":"pass","problems":[],"observed_at":(datetime.now(timezone.utc)-timedelta(seconds=seconds)).isoformat()}


def test_native_bootstrap_refresh_is_root_only(monkeypatch):
 monkeypatch.setattr(scope.os,"geteuid",lambda:1000)
 with pytest.raises(PermissionError,match="ROOT_REQUIRED"):scope.refresh_native_drift()


@pytest.mark.parametrize("age,wait",[(0,181),(179,2),(181,0),(3600,0),(-5,186)])
def test_native_validity_contract_preserves_actual_elapsed_time(age,wait):
 assert abs(release.native_refresh_delay(report(age))-wait)<.1


@pytest.mark.parametrize("fault",["future","failed","problems"])
def test_no_initial_clean_native_observation_denies(fault):
 row=report(190)
 if fault=="future":row=report(-11)
 elif fault=="failed":row["status"]="drift_detected"
 else:row["problems"]=[{"kind":"unexpected_container"}]
 with pytest.raises(JournalUnavailable):release.native_refresh_delay(row)


@pytest.mark.parametrize("fault",[None,"native_denial","no_fresh_report"])
def test_worker_uses_native_root_service_and_requires_new_observation(monkeypatch,capsys,fault):
 executor=object.__new__(release.ExactRelease)
 executor.c=SimpleNamespace(writer_identity=lambda:{"user":1000,"group":1000,"extra_groups":(),"env":{"PATH":"/usr/bin:/bin"}})
 executor.status=lambda *args,**kwargs:None
 before=report(3600);after=before if fault=="no_fresh_report" else report(0)
 reads=iter((before,after));seen=[]
 monkeypatch.setattr(release,"read_control",lambda *args:next(reads))
 def invoke(argv,**kwargs):
  seen.append(argv)
  assert argv[:4]==["/usr/bin/python3","-I","-B","-c"]
  compile(argv[-1],"native_request","exec")
  assert kwargs["user"]==kwargs["group"]==1000 and kwargs["extra_groups"]==()
  return SimpleNamespace(returncode=int(fault=="native_denial"),stdout='{"native_revalidation":"denied","detail":"immutable last-known-good mismatch: runtime_image_id"}')
 monkeypatch.setattr(release.subprocess,"run",invoke)
 if fault:
  with pytest.raises(JournalUnavailable):executor.revalidate()
  if fault=="native_denial":assert "immutable last-known-good mismatch: runtime_image_id" in capsys.readouterr().out
 else:executor.revalidate()
 assert len(seen)==1
