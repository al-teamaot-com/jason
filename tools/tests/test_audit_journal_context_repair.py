"""The existing failed Owner grant is never a forward-migration authorization."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from tools import audit_journal_pre_cutover_repair as repair


def state():
 return ({"steps":{},"scope_sha256":repair.OLD_SCOPE,"recovery_started_at":"2026-11-23T14:18:07+00:00"},
  {"mode":"legacy","generation":0,"epoch":None,"segments":[]})


def test_exact_pre_cutover_state_is_read_only():
 journal,catalog=state();before=deepcopy((journal,catalog))
 repair.validate_pre_cutover(journal,catalog)
 assert (journal,catalog)==before


@pytest.mark.parametrize("target,key,value",[
 ("journal","steps",{"install:jason-runtime":{}}),("journal","outcome","accepted"),
 ("journal","outcome","rolled_back"),("journal","scope_sha256","a"*64),
 ("catalog","mode","segmented"),("catalog","generation",1),("catalog","epoch","new"),
 ("catalog","segments",[{"id":"history"}])])
def test_any_cutover_or_other_execution_denies_repair(target,key,value):
 journal,catalog=state();(journal if target=="journal" else catalog)[key]=value
 with pytest.raises(PermissionError):repair.validate_pre_cutover(journal,catalog)


def test_unexplained_failure_denies_repair():
 journal,catalog=state();del journal["recovery_started_at"]
 with pytest.raises(PermissionError):repair.validate_pre_cutover(journal,catalog)


def drift():
 return ({"status":"drift_detected","observed_at":datetime.now(timezone.utc).isoformat(),
  "problems":[{"kind":"required_system_unit_not_active","unit":"jason-audit-journal-maintenance.timer","state":"inactive"},
   {"kind":"failed_system_unit","unit":"jason-audit-journal-release.service","state":"failed"}]},
  {"circuit_breaker":{"state":"open","reason":"continuous_production_drift_detected"}})


def test_known_installation_fault_keeps_breaker_guarded():
 report,control=drift();before=deepcopy((report,control));repair.validate_known_drift(report,control)
 assert (report,control)==before and control["circuit_breaker"]["state"]=="open"


@pytest.mark.parametrize("fault",["extra","missing","different_unit","different_state","stale","future","closed","reason"])
def test_unrelated_or_unknown_drift_denies_repair(fault):
 report,control=drift()
 if fault=="extra":report["problems"].append({"kind":"failed_system_unit","unit":"jason-core.service","state":"failed"})
 elif fault=="missing":report["problems"].pop()
 elif fault=="different_unit":report["problems"][0]["unit"]="jason-core.service"
 elif fault=="different_state":report["problems"][0]["state"]="failed"
 elif fault=="stale":report["observed_at"]=(datetime.now(timezone.utc)-timedelta(seconds=181)).isoformat()
 elif fault=="future":report["observed_at"]=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
 elif fault=="closed":control["circuit_breaker"]["state"]="closed"
 else:control["circuit_breaker"]["reason"]="other"
 with pytest.raises(PermissionError):repair.validate_known_drift(report,control)


def test_declared_initial_timer_is_not_falsely_reported_ready():
 from tools import audit_journal_release_scope as scope
 before={"required_system_units":[],"allowed_system_units":[],"rollback_container_prefixes":[],
  "max_stopped_rollback_containers":21}
 initial=scope.desired_initial(before);final=scope.desired_after(before)
 assert "jason-audit-journal-maintenance.timer" in initial["allowed_system_units"]
 assert "jason-audit-journal-maintenance.timer" not in initial["required_system_units"]
 assert "jason-audit-journal-maintenance.timer" in final["required_system_units"]
 assert initial["max_stopped_rollback_containers"]==final["max_stopped_rollback_containers"]==27
 assert scope.desired_rollback(before)==initial


@pytest.mark.parametrize("fault",[None,"native_failure","still_open","drift","policy_changed"])
def test_native_revalidation_is_required_before_repaired_worker_queue(monkeypatch,fault):
 from types import SimpleNamespace
 from pathlib import Path
 from tools import audit_journal_release_scope as release_scope
 s=SimpleNamespace(STATE=Path("/fixture/state"),DESIRED=Path("/fixture/desired"),ROLLBACK=release_scope.ROLLBACK,
  refresh_native_drift=lambda:None,native_revalidation_code=release_scope.native_revalidation_code)
 initial=b'{"stage":"initial"}';scope={"desired_state_initial_sha256":repair.digest(initial)}
 control={"circuit_breaker":{"state":"open" if fault=="still_open" else "closed"}}
 report={"status":"pass","problems":[],"observed_at":datetime.now(timezone.utc).isoformat()}
 if fault=="drift":report={"status":"drift_detected","problems":[{"kind":"unexpected"}],"observed_at":datetime.now(timezone.utc).isoformat()}
 def read(path):return repair.canon(control if path.name=="production-control-state.json" else report)
 seen=[];I=SimpleNamespace(command=lambda argv,**kwargs:seen.append((argv,kwargs)),read=read)
 def invoke(argv,**kwargs):
  assert kwargs["user"]==kwargs["group"]==1000 and kwargs["extra_groups"]==()
  assert "request_root_control_transition" in argv[-1] and "action='revalidate'" in argv[-1]
  return SimpleNamespace(returncode=1 if fault=="native_failure" else 0,stdout='{}')
 monkeypatch.setattr(repair.subprocess,"run",invoke)
 def raw(path,mode):
  assert mode==0o600
  if path.name=="production-control-state.json":return repair.canon(control)
  if path.name=="production-drift.json":return repair.canon(report)
  return initial if fault!="policy_changed" else b"unknown-policy"
 monkeypatch.setattr(repair,"raw_file",raw)
 if fault is None:repair.revalidate_before_queue(I,s,scope)
 else:
  with pytest.raises(PermissionError):repair.revalidate_before_queue(I,s,scope)
 assert len(seen)==(0 if fault=="policy_changed" else 1) and all(argv[1]=="start" for argv,_ in seen)
 assert not any("reset-failed" in argv for argv,_ in seen)


def test_only_attested_rolled_back_context_accepts_inactive_failed_worker():
 report,control=drift();report["problems"].pop()
 with pytest.raises(PermissionError):repair.validate_known_drift(report,control)
 repair.validate_known_drift(report,control,rolled_back_context=True)
 report["problems"].append({"kind":"failed_system_unit","unit":"jason-core.service","state":"failed"})
 with pytest.raises(PermissionError):repair.validate_known_drift(report,control,rolled_back_context=True)
